from datetime import date, datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.config import get_settings
from app.database import initialize_database, list_audit
from app.main import app
from app.schemas import CaseType, RecoveryCase
from app.workflows import execute_workflow


def make_case(
    case_id: str, case_type: CaseType, **changes
) -> RecoveryCase:
    payload = {
        "case_id": case_id,
        "case_type": case_type,
        "customer_id": "cust_test",
        "amount_paise": 250_000,
        "failure_reason": "bank_timeout",
    }
    payload.update(changes)
    return RecoveryCase(**payload)


def test_degradation_route():
    with TestClient(app) as client:
        response = client.post(
            "/workflows/payment-degradation",
            json={
                "current_failure_rate": 0.24,
                "baseline_failure_rate": 0.06,
                "payment_method": "upi",
                "bank": "TEST_BANK",
                "affected_amount_paise": 500_000,
            },
        )
        assert response.status_code == 200
        assert response.json()["degraded"] is True


def test_checkout_subscription_invoice_and_mandate_routes():
    routes = [
        (
            "/workflows/checkout-dropoff",
            make_case("checkout", CaseType.CHECKOUT_ABANDONMENT),
        ),
        (
            "/workflows/subscription-recovery",
            make_case(
                "subscription",
                CaseType.SUBSCRIPTION_FAILURE,
                failure_reason="insufficient_funds",
            ),
        ),
        (
            "/workflows/b2b-receivables",
            make_case(
                "invoice", CaseType.B2B_INVOICE, failure_reason="invoice_overdue"
            ),
        ),
        (
            "/workflows/mandate-retry",
            make_case(
                "mandate",
                CaseType.MANDATE_RETRY,
                failure_reason="mandate_revoked",
                mandate_active=False,
            ),
        ),
    ]
    with TestClient(app) as client:
        for route, case in routes:
            response = client.post(route, json=case.model_dump(mode="json"))
            assert response.status_code == 200, response.text


def test_voice_and_promise_routes():
    with TestClient(app) as client:
        voice_case = make_case(
            "voice",
            CaseType.VOICE_RECOVERY,
            amount_paise=2_000_000,
            voice_consent=True,
        )
        response = client.post(
            "/cases/process", json=voice_case.model_dump(mode="json")
        )
        assert response.status_code == 200
        voice_response = client.post(
            "/workflows/voice/turn",
            json={
                "case_id": "voice",
                "customer_utterance": "Friday ko payment kar dungi",
            },
        )
        assert voice_response.status_code == 200
        assert voice_response.json()["intent"] == "promise_to_pay"

        promise_case = make_case(
            "promise",
            CaseType.PROMISE_TO_PAY,
            promise_date=date(2026, 9, 5),
            promised_amount_paise=250_000,
        )
        response = client.post(
            "/cases/process", json=promise_case.model_dump(mode="json")
        )
        assert response.status_code == 200
        promise_response = client.post(
            "/workflows/promises",
            json={
                "case_id": "promise",
                "promised_amount_paise": 250_000,
                "promise_date": "2026-09-05",
                "source": "voice",
            },
        )
        assert promise_response.status_code == 200
        assert promise_response.json()["counted_as_recovered"] is False


def test_fallback_without_api_key():
    initialize_database()
    result = execute_workflow(
        make_case("fallback", CaseType.PAYMENT_FAILURE),
        get_settings(),
        now=datetime(2026, 9, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata")),
    )
    assert result.used_fallback is True
    assert result.ai_decision.root_cause == "bank_timeout"


def test_duplicate_action_is_suppressed():
    initialize_database()
    case = make_case("duplicate", CaseType.PAYMENT_FAILURE)
    now = datetime(2026, 9, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata"))
    first = execute_workflow(case, get_settings(), now=now)
    second = execute_workflow(case, get_settings(), now=now)
    assert first.action_id is not None
    assert second.action_id is None
    assert second.policy_decision.code == "DUPLICATE_ACTION"


def test_audit_trail_is_created():
    initialize_database()
    execute_workflow(make_case("audit", CaseType.PAYMENT_FAILURE), get_settings())
    events = list_audit("audit")
    assert len(events) == 3
    assert events[0]["event_type"] == "CASE_RECEIVED"
    assert events[1]["event_type"] == "ACTION_PROPOSED"
