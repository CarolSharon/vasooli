import hashlib
import hmac
import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models import Provenance, ProviderEvent, ProviderReference, RecoveryCase
from app.services.audit import append_audit

router = APIRouter(tags=["razorpay-webhooks"])
Db = Annotated[Session, Depends(get_db)]
PAYMENT_STATUS_RANK = {
    "created": 10,
    "authorized": 20,
    "failed": 30,
    "captured": 40,
    "refunded": 50,
}
CONFIRMED_EVENTS = {"payment.captured", "payment_link.paid", "order.paid"}


def verify_signature(
    raw_body: bytes, received_signature: str, secret: str | None = None
) -> bool:
    key = secret or settings.razorpay_webhook_secret
    if not key or not received_signature:
        return False
    expected = hmac.new(key.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received_signature)


def entity_from_payload(payload: dict) -> dict:
    entities = payload.get("payload", {})
    for name in (
        "payment",
        "payment_link",
        "order",
        "subscription",
        "invoice",
        "refund",
    ):
        if entity := entities.get(name, {}).get("entity"):
            return entity
    return {}


def locate_case(db: Session, entity: dict) -> RecoveryCase | None:
    notes = entity.get("notes") or {}
    raw_id = notes.get("case_id") or entity.get("reference_id")
    if raw_id:
        case = (
            db.get(RecoveryCase, int(raw_id))
            if str(raw_id).isdigit()
            else db.scalar(
                select(RecoveryCase).where(RecoveryCase.case_reference == str(raw_id))
            )
        )
        if case:
            return case
    ids = [
        str(entity[k])
        for k in ("id", "order_id", "payment_id", "subscription_id", "invoice_id")
        if entity.get(k)
    ]
    reference = (
        db.scalar(
            select(ProviderReference).where(
                ProviderReference.provider == "RAZORPAY",
                ProviderReference.provider_reference_id.in_(ids),
            )
        )
        if ids
        else None
    )
    return db.get(RecoveryCase, reference.case_id) if reference else None


@router.post("/webhooks/razorpay")
async def razorpay_webhook(
    request: Request,
    db: Db,
    x_razorpay_signature: Annotated[str, Header()],
    x_razorpay_event_id: Annotated[str | None, Header()] = None,
):
    raw = await request.body()
    if not verify_signature(raw, x_razorpay_signature):
        raise HTTPException(400, "Invalid Razorpay signature")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(400, "Invalid JSON") from exc
    event_id = x_razorpay_event_id or hashlib.sha256(raw).hexdigest()
    if db.scalar(
        select(ProviderEvent).where(
            ProviderEvent.provider == "RAZORPAY",
            ProviderEvent.provider_event_id == event_id,
        )
    ):
        return {"received": True, "duplicate": True}
    entity = entity_from_payload(payload)
    case = locate_case(db, entity)
    created = (
        datetime.fromtimestamp(int(entity["created_at"]), tz=timezone.utc)
        if entity.get("created_at")
        else None
    )
    event = ProviderEvent(
        provider="RAZORPAY",
        provider_event_id=event_id,
        event_type=payload.get("event", "unknown"),
        provider_created_at=created,
        signature_valid=True,
        processing_status="RECEIVED",
        case_id=case.id if case else None,
        payload=payload,
    )
    db.add(event)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return {"received": True, "duplicate": True}
    if not case:
        event.processing_status = "UNMATCHED"
        event.error = "No case matched provider identifiers"
        db.commit()
        return {"received": True, "matched": False}
    incoming = entity.get("status")
    stale = bool(
        incoming
        and PAYMENT_STATUS_RANK.get(incoming, 0)
        < PAYMENT_STATUS_RANK.get(case.provider_status or "", 0)
    )
    if incoming and not stale:
        case.provider_status = incoming
    event_type = event.event_type
    if event_type in CONFIRMED_EVENTS:
        case.payment_confirmed_at = datetime.now(timezone.utc)
        case.status = "RECOVERED"
        case.funnel_stage = "RECOVERED"
        case.outcome_provenance = Provenance.RAZORPAY_TEST.value
        case.recovered_amount_paise = case.amount_paise
    elif event_type == "payment.failed" and not case.payment_confirmed_at:
        case.status = "RECOVERY_REQUIRED"
        case.failure_code = entity.get("error_code")
        case.failure_description = entity.get("error_description")
    event.processing_status = "IGNORED_STALE" if stale else "PROCESSED"
    event.processed_at = datetime.now(timezone.utc)
    append_audit(
        db,
        case_id=case.id,
        event_type=f"RAZORPAY_{event_type.upper().replace('.', '_')}",
        actor="RAZORPAY_WEBHOOK",
        data={
            "provider_event_id": event_id,
            "status": incoming,
            "stale": stale,
            "provenance": Provenance.RAZORPAY_TEST.value,
        },
    )
    db.commit()
    return {"received": True, "duplicate": False, "matched": True, "stale": stale}
