from datetime import datetime
from zoneinfo import ZoneInfo

from app.policies.guardrails import GuardrailContext, Result, evaluate_guardrails

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))


def evaluate(context: GuardrailContext, **overrides):
    values = {
        "action_type": "reminder",
        "channel": "whatsapp",
        "attempt_number": 1,
        "now": NOW,
        "context": context,
    }
    values.update(overrides)
    return evaluate_guardrails(**values)


def test_opt_out_blocks_contact():
    result = evaluate(GuardrailContext(opted_out=True))
    assert result.result == Result.BLOCK
    assert result.code == "CUSTOMER_OPTED_OUT"


def test_recovered_case_blocks_all_actions():
    result = evaluate(GuardrailContext(case_recovered=True), channel=None)
    assert result.result == Result.BLOCK
    assert result.code == "CASE_ALREADY_RECOVERED"


def test_refunded_order_blocks_recovery():
    result = evaluate(GuardrailContext(already_refunded=True))
    assert result.code == "ORDER_REFUNDED"


def test_revoked_mandate_blocks_retry():
    result = evaluate(
        GuardrailContext(mandate_active=False),
        action_type="payment_retry",
        channel=None,
    )
    assert result.code == "MANDATE_REVOKED"


def test_quiet_hours_delay_voice_call():
    quiet_time = datetime(2026, 9, 1, 22, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    result = evaluate(GuardrailContext(), channel="voice", now=quiet_time)
    assert result.result == Result.DELAY
    assert result.code == "QUIET_HOURS"


def test_retry_limit_blocks_fourth_attempt():
    result = evaluate(
        GuardrailContext(), action_type="payment_retry", channel=None, attempt_number=4
    )
    assert result.code == "RETRY_LIMIT_REACHED"


def test_duplicate_action_is_suppressed():
    result = evaluate(GuardrailContext(duplicate_action=True))
    assert result.code == "DUPLICATE_ACTION"


def test_invoice_dispute_escalates():
    result = evaluate(GuardrailContext(invoice_disputed=True))
    assert result.result == Result.ESCALATE
    assert result.requires_human_review is True
