import hashlib
import hmac
import json
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_database
from app.models import PaymentEvent
from app.services.audit import record_audit_event

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


def find_payment(payload: dict[str, Any]) -> dict[str, Any]:
    return payload.get("payload", {}).get("payment", {}).get("entity", {})


@router.post("/razorpay", status_code=200)
async def receive_razorpay_webhook(
    request: Request,
    database: Annotated[Session, Depends(get_database)],
    x_razorpay_signature: Annotated[str | None, Header()] = None,
    x_razorpay_event_id: Annotated[str | None, Header()] = None,
):
    if not settings.razorpay_webhook_secret:
        raise HTTPException(
            status_code=503,
            detail="Webhook secret is not configured",
        )

    if not x_razorpay_signature or not x_razorpay_event_id:
        raise HTTPException(
            status_code=400,
            detail="Required Razorpay headers are missing",
        )

    raw_body = await request.body()

    expected_signature = hmac.new(
        settings.razorpay_webhook_secret.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected_signature, x_razorpay_signature):
        raise HTTPException(
            status_code=401,
            detail="Invalid webhook signature",
        )

    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=400,
            detail="Invalid JSON payload",
        ) from error

    payment = find_payment(payload)

    event = PaymentEvent(
        provider="razorpay",
        provider_event_id=x_razorpay_event_id,
        provider_payment_id=payment.get("id"),
        event_type=payload.get("event", "unknown"),
        payment_status=payment.get("status"),
        amount_paise=payment.get("amount"),
        raw_payload=payload,
    )

    database.add(event)

    try:
        database.commit()
    except IntegrityError:
        database.rollback()
        record_audit_event(
            database,
            case_id=None,
            actor="razorpay_webhook",
            event_type="DUPLICATE_SUPPRESSED",
            input_summary="Duplicate Razorpay webhook received.",
            decision="SUPPRESS",
            reason="The provider event identifier already exists.",
            policy_result={"result": "BLOCK", "code": "DUPLICATE_EVENT"},
            metadata={"provider_event_id": x_razorpay_event_id},
        )

        return {
            "status": "duplicate",
            "event_id": x_razorpay_event_id,
        }

    return {
        "status": "accepted",
        "event_id": x_razorpay_event_id,
    }
