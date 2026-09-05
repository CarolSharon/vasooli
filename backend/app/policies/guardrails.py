from dataclasses import asdict, dataclass
from datetime import datetime, time, timedelta
from enum import StrEnum


class Result(StrEnum):
    ALLOW = "ALLOW"
    BLOCK = "BLOCK"
    DELAY = "DELAY"
    ESCALATE = "ESCALATE"


@dataclass(frozen=True)
class GuardrailDecision:
    result: Result
    code: str
    reason: str
    next_allowed_at: datetime | None = None
    requires_human_review: bool = False

    def as_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GuardrailContext:
    opted_out: bool = False
    case_recovered: bool = False
    already_refunded: bool = False
    order_cancelled: bool = False
    invoice_disputed: bool = False
    mandate_active: bool | None = None
    whatsapp_consent: bool = True
    voice_consent: bool = True
    contact_consent: bool = True
    last_contact_at: datetime | None = None
    retry_count: int = 0
    reminder_count: int = 0
    voice_call_count: int = 0
    duplicate_action: bool = False


def decision(
    result: Result,
    code: str,
    reason: str,
    *,
    next_allowed_at: datetime | None = None,
    requires_human_review: bool = False,
) -> GuardrailDecision:
    return GuardrailDecision(
        result, code, reason, next_allowed_at, requires_human_review
    )


def evaluate_guardrails(
    *,
    action_type: str,
    channel: str | None,
    attempt_number: int,
    now: datetime,
    context: GuardrailContext,
) -> GuardrailDecision:
    if context.case_recovered:
        return decision(
            Result.BLOCK, "CASE_ALREADY_RECOVERED", "The case is already recovered."
        )
    if context.already_refunded:
        return decision(
            Result.BLOCK, "ORDER_REFUNDED", "The order has already been refunded."
        )
    if context.order_cancelled:
        return decision(
            Result.BLOCK, "ORDER_CANCELLED", "The order has been cancelled."
        )
    if context.opted_out:
        return decision(
            Result.BLOCK,
            "CUSTOMER_OPTED_OUT",
            "The customer previously withdrew contact consent.",
        )
    if context.invoice_disputed:
        return decision(
            Result.ESCALATE,
            "INVOICE_DISPUTED",
            "The invoice is disputed and requires human review.",
            requires_human_review=True,
        )
    if action_type == "payment_retry" and context.mandate_active is False:
        return decision(
            Result.BLOCK, "MANDATE_REVOKED", "The payment mandate has been revoked."
        )
    if not context.contact_consent and channel is not None:
        return decision(
            Result.BLOCK, "CONTACT_CONSENT_MISSING", "Contact consent is missing."
        )
    if channel == "whatsapp" and not context.whatsapp_consent:
        return decision(
            Result.BLOCK, "WHATSAPP_CONSENT_MISSING", "WhatsApp consent is missing."
        )
    if channel == "voice" and not context.voice_consent:
        return decision(
            Result.BLOCK, "VOICE_CONSENT_MISSING", "Voice consent is missing."
        )
    if action_type == "payment_retry" and (
        attempt_number >= 4 or context.retry_count >= 3
    ):
        return decision(
            Result.BLOCK,
            "RETRY_LIMIT_REACHED",
            "The maximum retry count has been reached.",
        )
    if action_type == "reminder" and context.reminder_count >= 3:
        return decision(
            Result.BLOCK,
            "REMINDER_LIMIT_REACHED",
            "The maximum reminder count has been reached.",
        )
    if channel == "voice" and context.voice_call_count >= 1:
        return decision(
            Result.BLOCK,
            "VOICE_CALL_LIMIT_REACHED",
            "The maximum voice-call count has been reached.",
        )
    if context.duplicate_action:
        return decision(
            Result.BLOCK,
            "DUPLICATE_ACTION",
            "An equivalent recovery action already exists.",
        )
    if channel == "voice" and (now.time() >= time(21, 0) or now.time() < time(9, 0)):
        next_day = (
            now.date() + timedelta(days=1) if now.time() >= time(21, 0) else now.date()
        )
        next_allowed = datetime.combine(next_day, time(9, 0), tzinfo=now.tzinfo)
        return decision(
            Result.DELAY,
            "QUIET_HOURS",
            "Voice calls are delayed during quiet hours.",
            next_allowed_at=next_allowed,
        )
    if context.last_contact_at is not None:
        next_allowed = context.last_contact_at + timedelta(hours=24)
        if now < next_allowed:
            return decision(
                Result.DELAY,
                "CONTACT_COOLDOWN",
                "The customer is still inside the contact cooldown.",
                next_allowed_at=next_allowed,
            )
    return decision(Result.ALLOW, "ACTION_ALLOWED", "All guardrail checks passed.")
