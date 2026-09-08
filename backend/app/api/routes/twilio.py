from datetime import datetime, timedelta, timezone
from typing import Annotated

from dateutil import parser as date_parser
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.config import settings
from app.database import get_db
from app.models import CommunicationEvent, Customer, PromiseToPay, RecoveryCase
from app.services.audit import append_audit

router = APIRouter(prefix="/api/twilio", tags=["twilio"])
Db = Annotated[Session, Depends(get_db)]


def classify_intent(
    text: str, now: datetime | None = None
) -> tuple[str, datetime | None]:
    now = now or datetime.now(timezone.utc)
    normalized = " ".join(text.lower().split())
    if any(x in normalized for x in ("stop", "unsubscribe", "band karo")):
        return "OPT_OUT", None
    if any(x in normalized for x in ("dispute", "fraud", "mera payment nahi")):
        return "DISPUTE", None
    if any(x in normalized for x in ("human", "agent", "person")):
        return "HUMAN_TRANSFER", None
    if any(x in normalized for x in ("pay", "link", "bhejo")):
        return "SEND_PAYMENT_LINK", None
    if any(x in normalized for x in ("later", "baad mein", "call later")):
        return "CALL_LATER", now + timedelta(hours=24)
    weekdays = {
        name: index
        for index, name in enumerate(
            (
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
                "sunday",
            )
        )
    }
    for name, weekday in weekdays.items():
        if name in normalized:
            return "PROMISE_TO_PAY", now + timedelta(
                days=(weekday - now.weekday()) % 7 or 7
            )
    try:
        parsed = date_parser.parse(normalized, fuzzy=True)
        parsed = (
            parsed.replace(tzinfo=timezone.utc) if parsed.tzinfo is None else parsed
        )
        if parsed.date() >= now.date():
            return "PROMISE_TO_PAY", parsed
    except (ValueError, OverflowError):
        pass
    return "UNKNOWN", None


def validate_twilio_request(request: Request, form: dict[str, str]) -> None:
    if not settings.twilio_auth_token:
        raise HTTPException(503, "Twilio is not configured")
    base = settings.public_api_url.rstrip("/")
    url = f"{base}{request.url.path}" + (
        f"?{request.url.query}" if request.url.query else ""
    )
    if not RequestValidator(settings.twilio_auth_token).validate(
        url, form, request.headers.get("X-Twilio-Signature", "")
    ):
        raise HTTPException(403, "Invalid Twilio signature")


@router.post("/whatsapp/inbound")
async def inbound_whatsapp(request: Request, db: Db):
    form = dict(await request.form())
    validate_twilio_request(request, form)
    sid, sender, body = (
        form.get("MessageSid"),
        form.get("From", "").replace("whatsapp:", ""),
        form.get("Body", ""),
    )
    response = MessagingResponse()
    if sid and db.scalar(
        select(CommunicationEvent).where(CommunicationEvent.provider_message_id == sid)
    ):
        return Response(content=str(response), media_type="application/xml")
    customer = db.scalar(
        select(Customer).where(
            Customer.phone.in_([sender, f"+{sender.lstrip('+')} ".strip()])
        )
    )
    case = (
        db.scalar(
            select(RecoveryCase)
            .where(RecoveryCase.customer_id == customer.id)
            .order_by(RecoveryCase.created_at.desc())
        )
        if customer
        else None
    )
    if not case or not customer:
        response.message("We could not match this reply. Please contact support.")
        return Response(content=str(response), media_type="application/xml")
    intent, intent_date = classify_intent(body)
    db.add(
        CommunicationEvent(
            case_id=case.id,
            channel="WHATSAPP",
            direction="INBOUND",
            provider_message_id=sid,
            status="RECEIVED",
            intent=intent,
            body=body,
            metadata_json={},
        )
    )
    if intent == "OPT_OUT":
        customer.opted_out = True
        case.status = "BLOCKED"
        response.message("You have been opted out. No more reminders will be sent.")
    elif intent == "DISPUTE":
        case.invoice_disputed = True
        case.status = "HUMAN_ESCALATION"
        response.message("We paused recovery and sent this to support.")
    elif intent == "HUMAN_TRANSFER":
        case.status = "HUMAN_ESCALATION"
        response.message("A support agent will contact you.")
    elif intent == "PROMISE_TO_PAY" and intent_date:
        db.add(
            PromiseToPay(
                case_id=case.id,
                promised_amount_paise=case.amount_paise,
                promised_date=intent_date.date(),
                source="WHATSAPP",
                status="PENDING",
            )
        )
        case.status = "PROMISE_PENDING"
        response.message(
            f"Thank you. We recorded your promise for {intent_date.date().isoformat()}."
        )
    elif intent == "CALL_LATER":
        case.next_action_at = intent_date
        response.message("Okay, we will contact you later.")
    elif intent == "SEND_PAYMENT_LINK":
        response.message(
            f"Here is your secure payment link: {case.latest_payment_url}"
            if case.latest_payment_url
            else "We are preparing your payment link."
        )
    else:
        response.message("Reply PAY, a payment date, LATER, DISPUTE, HUMAN, or STOP.")
    append_audit(
        db,
        case_id=case.id,
        event_type=f"WHATSAPP_INTENT_{intent}",
        actor="CUSTOMER",
        data={"message_sid": sid},
    )
    db.commit()
    return Response(content=str(response), media_type="application/xml")
