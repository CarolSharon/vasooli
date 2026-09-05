import hashlib
import uuid
from datetime import UTC, date, datetime

from app.config import Settings
from app.recovery.ai import DecisionService
from app.recovery.policies import authorize_action
from app.recovery.repository import (
    insert_action,
    insert_audit,
    insert_promise,
    upsert_case,
)
from app.recovery.schemas import (
    AIDecision,
    CaseStatus,
    PolicyResult,
    PromiseRequest,
    RecoveryCase,
    VoiceTurnRequest,
    WorkflowResult,
)


def action_idempotency_key(case: RecoveryCase, decision: AIDecision) -> str:
    source = (
        f"{case.case_id}:{decision.proposed_action.value}:"
        f"{case.attempt_count}:{case.reminder_count}:{case.voice_call_count}"
    )
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


def execute_workflow(
    case: RecoveryCase, settings: Settings, now: datetime | None = None
) -> WorkflowResult:
    upsert_case(case.model_dump(mode="json"))
    audit_ids = [
        insert_audit(
            case_id=case.case_id,
            event_type="CASE_RECEIVED",
            actor="system",
            decision=None,
            reason="Case entered the recovery workflow.",
            metadata={"case_type": case.case_type.value},
        )
    ]
    ai_decision, selected_model, used_fallback = DecisionService(settings).diagnose(
        case
    )
    audit_ids.append(
        insert_audit(
            case_id=case.case_id,
            event_type="ACTION_PROPOSED",
            actor="deterministic_fallback" if used_fallback else "openai",
            decision=ai_decision.proposed_action.value,
            reason=ai_decision.reason_summary,
            metadata={
                "model": selected_model,
                "confidence": ai_decision.confidence,
                "used_fallback": used_fallback,
            },
        )
    )
    policy = authorize_action(
        case=case, action=ai_decision.proposed_action, settings=settings, now=now
    )
    action_id: str | None = None
    if policy.result == PolicyResult.ALLOW:
        action_id = f"act_{uuid.uuid4().hex[:12]}"
        inserted = insert_action(
            {
                "action_id": action_id,
                "case_id": case.case_id,
                "action_type": ai_decision.proposed_action.value,
                "status": "scheduled",
                "idempotency_key": action_idempotency_key(case, ai_decision),
            }
        )
        if not inserted:
            policy = policy.model_copy(
                update={
                    "result": PolicyResult.BLOCK,
                    "code": "DUPLICATE_ACTION",
                    "reason": "An identical recovery action already exists.",
                }
            )
            action_id = None
    if policy.result == PolicyResult.ALLOW:
        case.status = CaseStatus.SCHEDULED
    elif policy.result == PolicyResult.ESCALATE:
        case.status = CaseStatus.ESCALATED
    elif policy.result == PolicyResult.BLOCK:
        case.status = CaseStatus.BLOCKED
    audit_ids.append(
        insert_audit(
            case_id=case.case_id,
            event_type=f"ACTION_{policy.result.value.upper()}",
            actor="policy_engine",
            decision=policy.code,
            reason=policy.reason,
            metadata={"action_id": action_id},
        )
    )
    upsert_case(case.model_dump(mode="json"))
    return WorkflowResult(
        case=case,
        ai_decision=ai_decision,
        policy_decision=policy,
        selected_model=selected_model,
        used_fallback=used_fallback,
        action_id=action_id,
        audit_event_ids=audit_ids,
    )


def record_promise(request: PromiseRequest) -> dict:
    promise_id = insert_promise(
        case_id=request.case_id,
        amount_paise=request.promised_amount_paise,
        promise_date=request.promise_date.isoformat(),
        source=request.source,
    )
    audit_id = insert_audit(
        case_id=request.case_id,
        event_type="PROMISE_RECORDED",
        actor="customer",
        decision="pending",
        reason="Promise recorded but not counted as recovered revenue.",
        metadata=request.model_dump(mode="json"),
    )
    return {
        "promise_id": promise_id,
        "status": "pending",
        "counted_as_recovered": False,
        "audit_event_id": audit_id,
    }


def evaluate_promise(case: RecoveryCase, today: date | None = None) -> dict:
    check_date = today or datetime.now(UTC).date()
    if case.payment_confirmed:
        status, reason = "kept", "Confirmed payment received."
    elif case.promise_date and check_date > case.promise_date:
        status, reason = "broken", "Promise date passed without confirmed payment."
    else:
        status, reason = "pending", "Promise deadline has not passed."
    audit_id = insert_audit(
        case_id=case.case_id,
        event_type="PROMISE_EVALUATED",
        actor="system",
        decision=status,
        reason=reason,
        metadata={},
    )
    return {
        "case_id": case.case_id,
        "status": status,
        "reason": reason,
        "audit_event_id": audit_id,
    }


def process_voice_turn(request: VoiceTurnRequest) -> dict:
    utterance = request.customer_utterance.lower()
    if any(
        phrase in utterance
        for phrase in ["stop", "don't call", "do not call", "mat call"]
    ):
        intent, next_action = "opt_out", "stop_all_contact"
    elif any(
        phrase in utterance for phrase in ["friday", "tomorrow", "kal", "pay kar"]
    ):
        intent, next_action = "promise_to_pay", "confirm_amount_and_date"
    elif any(phrase in utterance for phrase in ["dispute", "wrong amount", "galat"]):
        intent, next_action = "dispute", "escalate_human"
    elif any(phrase in utterance for phrase in ["link", "whatsapp", "bhej"]):
        intent, next_action = "request_link", "send_secure_payment_link"
    else:
        intent, next_action = "unclear", "clarify_once_then_handoff"
    audit_id = insert_audit(
        case_id=request.case_id,
        event_type="VOICE_INTENT_CAPTURED",
        actor="voice_state_machine",
        decision=intent,
        reason="Bounded voice-state transition.",
        metadata={"next_action": next_action},
    )
    return {
        "intent": intent,
        "next_action": next_action,
        "audit_event_id": audit_id,
        "safety_message": "Never ask for OTP, PIN, CVV, password, or full card details.",
    }
