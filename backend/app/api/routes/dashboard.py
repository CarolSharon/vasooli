import asyncio
import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from app.database import SessionLocal, get_db
from app.models import (
    AuditEvent,
    Customer,
    PromiseToPay,
    ProviderEvent,
    RecoveryCase,
    VoiceSession,
)

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])
Db = Annotated[Session, Depends(get_db)]


@router.get("/overview")
def overview(db: Db):
    total = db.scalar(select(func.count()).select_from(RecoveryCase)) or 0

    def recovered(provenance: str) -> int:
        return (
            db.scalar(
                select(
                    func.coalesce(func.sum(RecoveryCase.recovered_amount_paise), 0)
                ).where(
                    RecoveryCase.status == "RECOVERED",
                    RecoveryCase.outcome_provenance == provenance,
                )
            )
            or 0
        )

    return {
        "total_cases": total,
        "razorpay_test_confirmed_recovery": recovered("RAZORPAY_TEST") / 100,
        "simulated_confirmed_recovery": recovered("SIMULATED_OUTCOME") / 100,
        "pending_promises": db.scalar(
            select(func.count())
            .select_from(PromiseToPay)
            .where(PromiseToPay.status == "PENDING")
        )
        or 0,
        "blocked_actions": db.scalar(
            select(func.count())
            .select_from(RecoveryCase)
            .where(RecoveryCase.status == "BLOCKED")
        )
        or 0,
        "unresolved_cases": db.scalar(
            select(func.count())
            .select_from(RecoveryCase)
            .where(RecoveryCase.status.in_(["NEW", "RECOVERY_REQUIRED", "IN_PROGRESS"]))
        )
        or 0,
        "human_escalations": db.scalar(
            select(func.count())
            .select_from(RecoveryCase)
            .where(RecoveryCase.status == "HUMAN_ESCALATION")
        )
        or 0,
    }


@router.get("/funnel")
def funnel(db: Db):
    return [
        {
            "stage": stage,
            "count": db.scalar(
                select(func.count())
                .select_from(RecoveryCase)
                .where(RecoveryCase.funnel_stage == stage)
            )
            or 0,
        }
        for stage in (
            "DETECTED",
            "DIAGNOSED",
            "ACTION_AUTHORIZED",
            "CONTACTED",
            "ENGAGED",
            "RECOVERED",
        )
    ]


@router.get("/evaluation")
def evaluation(db: Db):
    result = []
    for split in ("development", "held_out"):
        total = (
            db.scalar(
                select(func.count())
                .select_from(RecoveryCase)
                .where(RecoveryCase.dataset_split == split)
            )
            or 0
        )
        count = (
            db.scalar(
                select(func.count())
                .select_from(RecoveryCase)
                .where(
                    RecoveryCase.dataset_split == split,
                    RecoveryCase.status == "RECOVERED",
                )
            )
            or 0
        )
        paise = (
            db.scalar(
                select(
                    func.coalesce(func.sum(RecoveryCase.recovered_amount_paise), 0)
                ).where(RecoveryCase.dataset_split == split)
            )
            or 0
        )
        result.append(
            {
                "split": split,
                "total": total,
                "recovered": count,
                "recovery_rate": count / total if total else 0,
                "amount_recovered": paise / 100,
            }
        )
    return result


def _case_row(db: Session, row: RecoveryCase) -> dict:
    customer = db.get(Customer, row.customer_id)
    return {
        "id": row.id,
        "case_reference": row.case_reference,
        "customer_name": customer.name if customer else "Unknown",
        "amount": row.amount_paise / 100,
        "status": row.status,
        "workflow": row.workflow_type,
        "root_cause": row.root_cause,
        "recommended_action": row.recommended_action,
        "dataset_split": row.dataset_split,
        "outcome_provenance": row.outcome_provenance,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


@router.get("/cases")
def cases(
    db: Db,
    status: str | None = None,
    workflow: str | None = None,
    limit: Annotated[int, Query(le=500)] = 100,
):
    statement = select(RecoveryCase)
    if status:
        statement = statement.where(RecoveryCase.status == status)
    if workflow:
        statement = statement.where(RecoveryCase.workflow_type == workflow)
    return [
        _case_row(db, row)
        for row in db.scalars(
            statement.order_by(RecoveryCase.updated_at.desc()).limit(limit)
        )
    ]


@router.get("/cases/{case_id}")
def case_detail(case_id: int, db: Db):
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    promises = db.scalars(
        select(PromiseToPay)
        .where(PromiseToPay.case_id == case_id)
        .order_by(PromiseToPay.created_at)
    ).all()
    voice = db.scalar(
        select(VoiceSession)
        .where(VoiceSession.case_id == case_id)
        .order_by(VoiceSession.started_at.desc())
    )
    events = db.scalars(
        select(ProviderEvent)
        .where(ProviderEvent.case_id == case_id)
        .order_by(ProviderEvent.received_at)
    ).all()
    audit = db.scalars(
        select(AuditEvent)
        .where(AuditEvent.case_id == case_id)
        .order_by(AuditEvent.created_at)
    ).all()
    return {
        "case": _case_row(db, case),
        "promises": [
            {
                "id": p.id,
                "amount": p.promised_amount_paise / 100,
                "due_at": p.promised_date.isoformat(),
                "status": p.status,
                "source": p.source,
            }
            for p in promises
        ],
        "voice": None
        if not voice
        else {
            "status": voice.status,
            "intent": voice.final_intent,
            "transcript": voice.transcript,
        },
        "provider_events": [
            {
                "type": e.event_type,
                "status": e.processing_status,
                "received_at": e.received_at.isoformat(),
                "provenance": "RAZORPAY_TEST",
            }
            for e in events
        ],
        "audit": [
            {
                "id": a.id,
                "event_type": a.event_type,
                "actor": a.actor,
                "payload": a.metadata_json,
                "created_at": a.created_at.isoformat(),
            }
            for a in audit
        ],
    }


@router.get("/promises")
def promises(db: Db):
    return [
        {
            "id": p.id,
            "case_id": p.case_id,
            "amount": p.promised_amount_paise / 100,
            "due_at": p.promised_date.isoformat(),
            "status": p.status,
            "source": p.source,
        }
        for p in db.scalars(select(PromiseToPay).order_by(PromiseToPay.promised_date))
    ]


@router.get("/audit/stream")
async def audit_stream():
    async def events():
        last_id = 0
        while True:
            with SessionLocal() as db:
                rows = db.scalars(
                    select(AuditEvent)
                    .where(AuditEvent.id > last_id)
                    .order_by(AuditEvent.id)
                    .limit(50)
                ).all()
                for row in rows:
                    last_id = row.id
                    yield {
                        "event": "audit",
                        "id": str(row.id),
                        "data": json.dumps(
                            {
                                "id": row.id,
                                "case_id": row.case_id,
                                "event_type": row.event_type,
                                "actor": row.actor,
                                "created_at": row.created_at.isoformat(),
                            }
                        ),
                    }
            await asyncio.sleep(2)

    return EventSourceResponse(events())
