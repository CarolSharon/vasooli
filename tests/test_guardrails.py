from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.policies import authorize_action
from app.schemas import ActionType, CaseType, PolicyResult, RecoveryCase


def sample_case(**changes) -> RecoveryCase:
    payload = {
        "case_id": "guardrail_case",
        "case_type": CaseType.PAYMENT_FAILURE,
        "customer_id": "cust_test",
        "amount_paise": 100_000,
        "failure_reason": "bank_timeout",
    }
    payload.update(changes)
    return RecoveryCase(**payload)


def test_opt_out_blocks_contact():
    decision = authorize_action(
        sample_case(opted_out=True), ActionType.SEND_REMINDER, get_settings()
    )
    assert decision.result == PolicyResult.BLOCK
    assert decision.code == "CUSTOMER_OPTED_OUT"


def test_payment_confirmation_stops_recovery():
    decision = authorize_action(
        sample_case(payment_confirmed=True),
        ActionType.RETRY_PAYMENT,
        get_settings(),
    )
    assert decision.code == "PAYMENT_ALREADY_CONFIRMED"


def test_revoked_mandate_blocks_retry():
    decision = authorize_action(
        sample_case(mandate_active=False), ActionType.RETRY_PAYMENT, get_settings()
    )
    assert decision.code == "MANDATE_REVOKED"


def test_retry_cap_escalates():
    decision = authorize_action(
        sample_case(attempt_count=3), ActionType.RETRY_PAYMENT, get_settings()
    )
    assert decision.result == PolicyResult.ESCALATE
    assert decision.code == "MAX_RETRIES_REACHED"


def test_voice_requires_consent():
    decision = authorize_action(
        sample_case(voice_consent=False), ActionType.PLACE_VOICE_CALL, get_settings()
    )
    assert decision.code == "NO_VOICE_CONSENT"


def test_quiet_hours_delay_contact():
    now = datetime(2026, 9, 1, 22, tzinfo=ZoneInfo("Asia/Kolkata"))
    decision = authorize_action(
        sample_case(voice_consent=True),
        ActionType.PLACE_VOICE_CALL,
        get_settings(),
        now=now,
    )
    assert decision.result == PolicyResult.DELAY
    assert decision.code == "QUIET_HOURS"


def test_disputed_invoice_escalates():
    decision = authorize_action(
        sample_case(invoice_disputed=True), ActionType.SEND_REMINDER, get_settings()
    )
    assert decision.result == PolicyResult.ESCALATE
    assert decision.code == "INVOICE_DISPUTED"


def test_large_discount_requires_approval():
    decision = authorize_action(
        sample_case(requested_discount_paise=60_000),
        ActionType.SEND_PAYMENT_LINK,
        get_settings(),
    )
    assert decision.result == PolicyResult.ESCALATE
    assert decision.code == "DISCOUNT_APPROVAL_REQUIRED"
