from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.config import Settings
from app.recovery.schemas import (
    ActionType,
    PolicyDecision,
    PolicyResult,
    RecoveryCase,
)

CONTACT_ACTIONS = {
    ActionType.SEND_REMINDER,
    ActionType.SEND_PAYMENT_LINK,
    ActionType.PLACE_VOICE_CALL,
}


def in_quiet_hours(hour: int, start: int, end: int) -> bool:
    if start > end:
        return hour >= start or hour < end
    return start <= hour < end


def authorize_action(
    case: RecoveryCase,
    action: ActionType,
    settings: Settings,
    now: datetime | None = None,
) -> PolicyDecision:
    local_now = now or datetime.now(ZoneInfo(case.customer_timezone))
    if case.payment_confirmed or case.status.value == "recovered":
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="PAYMENT_ALREADY_CONFIRMED",
            reason="Recovery stops immediately after confirmed payment.",
        )
    if case.opted_out:
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="CUSTOMER_OPTED_OUT",
            reason="The customer withdrew contact permission.",
        )
    if case.already_refunded or case.order_cancelled:
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="INELIGIBLE_ORDER",
            reason="Refunded or cancelled orders are not recoverable.",
        )
    if case.invoice_disputed:
        return PolicyDecision(
            result=PolicyResult.ESCALATE,
            code="INVOICE_DISPUTED",
            reason="A disputed invoice requires a human account owner.",
            requires_human_review=True,
        )
    if case.requested_discount_paise > settings.max_automatic_discount_paise:
        return PolicyDecision(
            result=PolicyResult.ESCALATE,
            code="DISCOUNT_APPROVAL_REQUIRED",
            reason="The requested discount exceeds automatic authority.",
            requires_human_review=True,
        )
    if action == ActionType.RETRY_PAYMENT and case.mandate_active is False:
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="MANDATE_REVOKED",
            reason="A revoked mandate cannot be retried; reauthorization is required.",
        )
    if (
        action == ActionType.RETRY_PAYMENT
        and case.attempt_count >= settings.max_retries
    ):
        return PolicyDecision(
            result=PolicyResult.ESCALATE,
            code="MAX_RETRIES_REACHED",
            reason="The automatic retry limit has been reached.",
            requires_human_review=True,
        )
    if (
        action == ActionType.SEND_REMINDER
        and case.reminder_count >= settings.max_reminders
    ):
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="MAX_REMINDERS_REACHED",
            reason="The reminder limit has been reached.",
        )
    if action == ActionType.PLACE_VOICE_CALL:
        if not case.contact_consent or not case.voice_consent:
            return PolicyDecision(
                result=PolicyResult.BLOCK,
                code="NO_VOICE_CONSENT",
                reason="Voice contact requires explicit consent.",
            )
        if case.voice_call_count >= settings.max_voice_calls:
            return PolicyDecision(
                result=PolicyResult.BLOCK,
                code="MAX_VOICE_CALLS_REACHED",
                reason="The voice-call limit has been reached.",
            )
    if action in {
        ActionType.SEND_REMINDER,
        ActionType.SEND_PAYMENT_LINK,
    } and (not case.contact_consent or not case.whatsapp_consent):
        return PolicyDecision(
            result=PolicyResult.BLOCK,
            code="NO_MESSAGING_CONSENT",
            reason="Messaging requires customer consent.",
        )
    if action in CONTACT_ACTIONS:
        if in_quiet_hours(
            local_now.hour, settings.quiet_hours_start, settings.quiet_hours_end
        ):
            next_allowed = local_now.replace(
                hour=settings.quiet_hours_end, minute=0, second=0, microsecond=0
            )
            if next_allowed <= local_now:
                next_allowed += timedelta(days=1)
            return PolicyDecision(
                result=PolicyResult.DELAY,
                code="QUIET_HOURS",
                reason="Customer contact is delayed until permitted hours.",
                next_allowed_at=next_allowed,
            )
        if case.last_contact_at:
            last_contact = case.last_contact_at
            if last_contact.tzinfo is None:
                last_contact = last_contact.replace(
                    tzinfo=ZoneInfo(case.customer_timezone)
                )
            next_allowed = last_contact + timedelta(
                hours=settings.contact_cooldown_hours
            )
            if local_now < next_allowed:
                return PolicyDecision(
                    result=PolicyResult.DELAY,
                    code="CONTACT_COOLDOWN",
                    reason="The contact cooldown has not elapsed.",
                    next_allowed_at=next_allowed,
                )
    return PolicyDecision(
        result=PolicyResult.ALLOW,
        code="POLICY_APPROVED",
        reason="All deterministic guardrails passed.",
    )
