import hashlib
import hmac
from datetime import datetime, timedelta, timezone

import pytest
from fastapi import FastAPI
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool
from starlette.testclient import TestClient

from app.api.routes.dashboard import router as dashboard_router
from app.api.routes.razorpay_webhooks import (
    entity_from_payload,
    locate_case,
    verify_signature,
)
from app.api.routes.razorpay_webhooks import router as webhook_router
from app.api.routes.twilio import classify_intent
from app.database import Base, get_db
from app.models import (
    Customer,
    PromiseToPay,
    Provenance,
    ProviderEvent,
    ProviderReference,
    RecoveryCase,
)
from app.realtime.guarded_actions import execute_voice_tool
from app.services.whatsapp import send_recovery_message
from app.tasks.promises import process_overdue_promises


@pytest.fixture
def db():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    event.listen(
        engine,
        "connect",
        lambda connection, _: connection.execute("PRAGMA foreign_keys=ON"),
    )
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture
def recovery(db):
    customer = Customer(
        external_reference="customer-1",
        name="Test Customer",
        email="test@example.com",
        phone="+919123456789",
        whatsapp_consent=True,
        voice_consent=True,
        opted_out=False,
        lifetime_value_paise=100_000,
    )
    db.add(customer)
    db.flush()
    case = RecoveryCase(
        case_reference="case-1",
        customer_id=customer.id,
        case_type="payment_failure",
        amount_paise=10_000,
        currency="INR",
        status="RECOVERY_REQUIRED",
        data_source="SYNTHETIC",
        dataset_split="development",
        recovered_amount_paise=0,
    )
    db.add(case)
    db.commit()
    return case, customer


def make_client(db: Session, *routers) -> TestClient:
    app = FastAPI()
    for router in routers:
        app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def signed_post(client: TestClient, payload: dict, event_id: str):
    import json

    raw = json.dumps(payload, separators=(",", ":")).encode()
    signature = hmac.new(b"test-secret", raw, hashlib.sha256).hexdigest()
    return client.post(
        "/webhooks/razorpay",
        content=raw,
        headers={
            "content-type": "application/json",
            "x-razorpay-signature": signature,
            "x-razorpay-event-id": event_id,
        },
    )


def test_razorpay_signature_accepts_valid():
    raw, secret = b'{"event":"payment.captured"}', "secret"
    signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
    assert verify_signature(raw, signature, secret)


def test_razorpay_signature_rejects_invalid():
    assert not verify_signature(b"body", "incorrect", "secret")


@pytest.mark.parametrize(
    "name", ["payment", "payment_link", "order", "subscription", "invoice", "refund"]
)
def test_entity_extraction(name):
    assert (
        entity_from_payload({"payload": {name: {"entity": {"id": "provider-id"}}}})[
            "id"
        ]
        == "provider-id"
    )


def test_case_lookup_by_note(db, recovery):
    case, _ = recovery
    assert locate_case(db, {"notes": {"case_id": str(case.id)}}) == case


def test_case_lookup_by_provider_reference(db, recovery):
    case, _ = recovery
    db.add(
        ProviderReference(
            case_id=case.id,
            provider="RAZORPAY",
            reference_type="ORDER",
            provider_reference_id="order_1",
            provenance=Provenance.RAZORPAY_TEST,
        )
    )
    db.commit()
    assert locate_case(db, {"order_id": "order_1"}) == case


@pytest.mark.parametrize(
    ("text", "intent"),
    [
        ("STOP", "OPT_OUT"),
        ("This is fraud", "DISPUTE"),
        ("human please", "HUMAN_TRANSFER"),
        ("pay link bhejo", "SEND_PAYMENT_LINK"),
        ("call later", "CALL_LATER"),
        ("Friday", "PROMISE_TO_PAY"),
        ("hello", "UNKNOWN"),
    ],
)
def test_whatsapp_intents(text, intent):
    assert classify_intent(text, datetime(2026, 9, 5, tzinfo=timezone.utc))[0] == intent


def test_confirmed_payment_blocks_voice_tool(db, recovery):
    case, _ = recovery
    case.payment_confirmed_at = datetime.now(timezone.utc)
    db.commit()
    assert (
        execute_voice_tool(db, case=case, name="send_payment_link", arguments={})[
            "blocked_by"
        ]
        == "PAYMENT_CONFIRMED"
    )


def test_opt_out_blocks_voice_tool(db, recovery):
    case, customer = recovery
    customer.opted_out = True
    db.commit()
    assert (
        execute_voice_tool(db, case=case, name="send_payment_link", arguments={})[
            "blocked_by"
        ]
        == "OPT_OUT"
    )


def test_dispute_blocks_voice_tool(db, recovery):
    case, _ = recovery
    case.invoice_disputed = True
    db.commit()
    assert (
        execute_voice_tool(db, case=case, name="send_payment_link", arguments={})[
            "blocked_by"
        ]
        == "ACTIVE_DISPUTE"
    )


def test_missing_link_is_blocked(db, recovery):
    case, _ = recovery
    assert (
        execute_voice_tool(db, case=case, name="send_payment_link", arguments={})[
            "blocked_by"
        ]
        == "NO_PAYMENT_LINK"
    )


def test_future_promise_is_recorded(db, recovery):
    case, _ = recovery
    due = datetime.now(timezone.utc).date() + timedelta(days=2)
    result = execute_voice_tool(
        db, case=case, name="record_promise", arguments={"due_date": due.isoformat()}
    )
    assert result == {"ok": True, "due_date": due.isoformat()}


def test_past_promise_is_blocked(db, recovery):
    case, _ = recovery
    result = execute_voice_tool(
        db, case=case, name="record_promise", arguments={"due_date": "2020-01-01"}
    )
    assert result["blocked_by"] == "INVALID_PROMISE_DATE"


def test_unknown_voice_tool_is_blocked(db, recovery):
    case, _ = recovery
    assert (
        execute_voice_tool(db, case=case, name="make_discount", arguments={})[
            "blocked_by"
        ]
        == "UNKNOWN_TOOL"
    )


def test_overdue_promise_becomes_broken(db, recovery):
    case, _ = recovery
    today = datetime.now(timezone.utc).date()
    execute_voice_tool(
        db,
        case=case,
        name="record_promise",
        arguments={"due_date": (today + timedelta(days=1)).isoformat()},
    )
    assert process_overdue_promises(db, today=today + timedelta(days=2)) == 1
    assert case.status == "RECOVERY_REQUIRED"


def test_duplicate_provider_event_is_ignored(db, recovery, monkeypatch):
    case, _ = recovery
    monkeypatch.setattr(
        "app.api.routes.razorpay_webhooks.settings.razorpay_webhook_secret",
        "test-secret",
    )
    client = make_client(db, webhook_router)
    payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_1",
                    "status": "captured",
                    "notes": {"case_id": str(case.id)},
                }
            }
        },
    }
    assert signed_post(client, payload, "event-1").json()["duplicate"] is False
    assert signed_post(client, payload, "event-1").json()["duplicate"] is True


def test_out_of_order_event_cannot_reverse_capture(db, recovery, monkeypatch):
    case, _ = recovery
    case.provider_status = "captured"
    db.commit()
    monkeypatch.setattr(
        "app.api.routes.razorpay_webhooks.settings.razorpay_webhook_secret",
        "test-secret",
    )
    payload = {
        "event": "payment.authorized",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_2",
                    "status": "authorized",
                    "notes": {"case_id": str(case.id)},
                }
            }
        },
    }
    result = signed_post(make_client(db, webhook_router), payload, "event-2").json()
    db.refresh(case)
    assert result["stale"] is True and case.provider_status == "captured"


def test_opt_out_blocks_whatsapp(db, recovery):
    case, customer = recovery
    customer.opted_out = True
    db.commit()
    with pytest.raises(ValueError, match="STOP_OPTED_OUT"):
        send_recovery_message(db, case, customer, "https://example.test/pay")


def test_promise_becomes_kept_after_confirmed_payment(db, recovery):
    case, _ = recovery
    case.payment_confirmed_at = datetime.now(timezone.utc)
    promise = PromiseToPay(
        case_id=case.id,
        promised_amount_paise=case.amount_paise,
        promised_date=datetime.now(timezone.utc).date(),
        source="TEST",
        status="PENDING",
    )
    db.add(promise)
    db.commit()
    process_overdue_promises(db, today=datetime.now(timezone.utc).date())
    assert promise.status == "KEPT"


def test_dashboard_separates_real_and_simulated(db, recovery):
    case, _ = recovery
    case.status = "RECOVERED"
    case.recovered_amount_paise = 10_000
    case.outcome_provenance = "SIMULATED_OUTCOME"
    db.commit()
    result = make_client(db, dashboard_router).get("/api/dashboard/overview").json()
    assert result["simulated_confirmed_recovery"] == 100
    assert result["razorpay_test_confirmed_recovery"] == 0


def test_dashboard_keeps_held_out_separate(db, recovery):
    result = make_client(db, dashboard_router).get("/api/dashboard/evaluation").json()
    assert [row["split"] for row in result] == ["development", "held_out"]


def test_webhook_records_provider_event(db, recovery, monkeypatch):
    case, _ = recovery
    monkeypatch.setattr(
        "app.api.routes.razorpay_webhooks.settings.razorpay_webhook_secret",
        "test-secret",
    )
    payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": "pay_3",
                    "status": "failed",
                    "notes": {"case_id": str(case.id)},
                }
            }
        },
    }
    assert (
        signed_post(make_client(db, webhook_router), payload, "event-3").status_code
        == 200
    )
    assert (
        db.query(ProviderEvent).filter_by(provider_event_id="event-3").one().case_id
        == case.id
    )
