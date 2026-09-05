"""PostgreSQL persistence adapter for the recovered Day 2 workflow logic."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.database import SessionLocal
from app.models import AuditEvent, Customer, PromiseToPay, RecoveryAction, RecoveryCase


def _case(database, reference: str) -> RecoveryCase | None:
    return database.scalar(
        select(RecoveryCase).where(RecoveryCase.case_reference == reference)
    )


def upsert_case(payload: dict) -> None:
    with SessionLocal() as database:
        customer_ref = str(payload["customer_id"])
        customer = database.scalar(
            select(Customer).where(Customer.external_reference == customer_ref)
        )
        if not customer:
            customer = Customer(
                external_reference=customer_ref,
                name=payload.get("metadata", {}).get(
                    "customer_name", "Recovery customer"
                ),
                email=None,
                phone=None,
                preferred_language=payload.get("preferred_language", "en-IN"),
                timezone=payload.get("customer_timezone", "Asia/Kolkata"),
                whatsapp_consent=payload.get("whatsapp_consent", False),
                voice_consent=payload.get("voice_consent", False),
                opted_out=payload.get("opted_out", False),
                lifetime_value_paise=0,
            )
            database.add(customer)
            database.flush()
        row = _case(database, payload["case_id"])
        if not row:
            row = RecoveryCase(
                case_reference=payload["case_id"],
                customer_id=customer.id,
                case_type=payload["case_type"],
                amount_paise=payload["amount_paise"],
                currency=payload.get("currency", "INR"),
                status=str(payload["status"]),
                failure_reason=payload.get("failure_reason"),
                invoice_disputed=payload.get("invoice_disputed", False),
                risk_score=None,
                attempt_count=payload.get("attempt_count", 0),
                recovered_amount_paise=payload["amount_paise"]
                if payload.get("payment_confirmed")
                else 0,
                payment_confirmed_at=datetime.now(timezone.utc)
                if payload.get("payment_confirmed")
                else None,
                data_source=payload.get("metadata", {}).get("data_source", "SYNTHETIC"),
                dataset_split=payload.get("metadata", {}).get("dataset_split"),
            )
            database.add(row)
        else:
            row.status = str(payload["status"])
            row.attempt_count = payload.get("attempt_count", 0)
            row.invoice_disputed = payload.get("invoice_disputed", False)
        database.commit()


def insert_action(action: dict) -> bool:
    with SessionLocal() as database:
        row = _case(database, action["case_id"])
        if not row:
            return False
        database.add(
            RecoveryAction(
                case_id=row.id,
                action_type=action["action_type"],
                status=action["status"],
                channel=None,
                attempt_number=max(1, row.attempt_count + 1),
                scheduled_at=datetime.now(timezone.utc),
                executed_at=None,
                idempotency_key=action["idempotency_key"],
                blocked_reason=None,
                provider_reference=action["action_id"],
            )
        )
        try:
            database.commit()
        except IntegrityError:
            database.rollback()
            return False
        return True


def insert_audit(
    *,
    case_id: str,
    event_type: str,
    actor: str,
    decision: str | None,
    reason: str | None,
    metadata: dict | None = None,
) -> int:
    with SessionLocal() as database:
        row = _case(database, case_id)
        audit = AuditEvent(
            case_id=row.id if row else None,
            event_type=event_type,
            actor=actor,
            decision=decision,
            reason=reason,
            metadata_json=metadata or {},
        )
        database.add(audit)
        database.commit()
        database.refresh(audit)
        return audit.id


def insert_promise(
    *, case_id: str, amount_paise: int, promise_date: str, source: str
) -> int:
    with SessionLocal() as database:
        row = _case(database, case_id)
        if not row:
            raise ValueError("Case must exist before recording a promise")
        promise = PromiseToPay(
            case_id=row.id,
            promised_amount_paise=amount_paise,
            promised_date=datetime.fromisoformat(promise_date).date(),
            source=source,
            status="PENDING",
        )
        database.add(promise)
        database.commit()
        database.refresh(promise)
        return promise.id
