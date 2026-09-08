from enum import StrEnum
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditEvent


class AuditEventType(StrEnum):
    CASE_CREATED = "CASE_CREATED"
    FAILURE_DETECTED = "FAILURE_DETECTED"
    ACTION_PROPOSED = "ACTION_PROPOSED"
    ACTION_ALLOWED = "ACTION_ALLOWED"
    ACTION_EXECUTED = "ACTION_EXECUTED"
    ACTION_BLOCKED = "ACTION_BLOCKED"
    ACTION_DELAYED = "ACTION_DELAYED"
    DUPLICATE_SUPPRESSED = "DUPLICATE_SUPPRESSED"
    OUTCOME_RECEIVED = "OUTCOME_RECEIVED"
    PAYMENT_CONFIRMED = "PAYMENT_CONFIRMED"
    CASE_RECOVERED = "CASE_RECOVERED"
    CASE_ESCALATED = "CASE_ESCALATED"


def append_audit(
    database: Session,
    *,
    case_id: int | None,
    event_type: str,
    actor: str,
    data: dict[str, Any],
) -> AuditEvent:
    event = AuditEvent(
        case_id=case_id,
        actor=actor,
        event_type=event_type,
        input_summary=None,
        decision=data.get("decision"),
        reason=data.get("reason"),
        policy_result=data.get("policy_result"),
        metadata_json=data,
    )
    database.add(event)
    database.flush()
    return event


def record_audit_event(
    database: Session,
    *,
    case_id: int | None,
    actor: str,
    event_type: str,
    input_summary: str | None,
    decision: str | None,
    reason: str | None,
    policy_result: dict[str, Any] | None,
    metadata: dict[str, Any] | None,
) -> AuditEvent:
    event = AuditEvent(
        case_id=case_id,
        actor=actor,
        event_type=event_type,
        input_summary=input_summary,
        decision=decision,
        reason=reason,
        policy_result=policy_result,
        metadata_json=metadata,
    )
    database.add(event)
    database.commit()
    database.refresh(event)
    return event
