from datetime import date, datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models import PromiseToPay, RecoveryCase
from app.services.audit import append_audit
from app.workers.celery_app import celery_app


def process_overdue_promises(db: Session, today: date | None = None) -> int:
    today = today or datetime.now(timezone.utc).date()
    due = db.scalars(
        select(PromiseToPay).where(
            PromiseToPay.status == "PENDING", PromiseToPay.promised_date <= today
        )
    ).all()
    for promise in due:
        case = db.get(RecoveryCase, promise.case_id)
        if not case:
            continue
        if case.payment_confirmed_at:
            promise.status = "KEPT"
            promise.kept_at = datetime.now(timezone.utc)
            event_type = "PROMISE_KEPT"
        else:
            promise.status = "BROKEN"
            promise.broken_at = datetime.now(timezone.utc)
            case.status = "RECOVERY_REQUIRED"
            event_type = "PROMISE_BROKEN"
        append_audit(
            db,
            case_id=case.id,
            event_type=event_type,
            actor="SYSTEM",
            data={"promise_id": promise.id},
        )
    db.commit()
    return len(due)


@celery_app.task(name="check_overdue_promises")
def check_overdue_promises():
    with SessionLocal() as db:
        return process_overdue_promises(db)
