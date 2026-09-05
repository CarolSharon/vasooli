from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session
from twilio.twiml.voice_response import Connect, VoiceResponse

from app.config import settings
from app.database import get_db
from app.integrations.twilio_client import start_voice_call
from app.models import Customer, RecoveryCase

router = APIRouter(prefix="/api/twilio", tags=["voice"])
Db = Annotated[Session, Depends(get_db)]


@router.post("/voice")
def voice_twiml(case_id: Annotated[int, Query()]):
    response = VoiceResponse()
    connect = Connect()
    stream = connect.stream(
        url=f"{settings.public_ws_url.rstrip('/')}/api/twilio/media"
    )
    stream.parameter(name="case_id", value=str(case_id))
    response.append(connect)
    if settings.twilio_fallback_audio_url:
        response.play(settings.twilio_fallback_audio_url)
    else:
        response.say(
            "We could not connect the payment assistant. Our team will contact you later."
        )
    return Response(content=str(response), media_type="application/xml")


@router.post("/voice/start/{case_id}")
def start_call(case_id: int, db: Db):
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    customer = db.get(Customer, case.customer_id)
    if not customer or not customer.phone:
        raise HTTPException(409, "Customer has no phone")
    if case.payment_confirmed_at:
        raise HTTPException(409, "Payment already confirmed")
    if customer.opted_out or not customer.voice_consent:
        raise HTTPException(403, "Voice contact not permitted")
    if case.invoice_disputed:
        raise HTTPException(409, "Disputed case requires human handling")
    return {
        "call_sid": start_voice_call(to=customer.phone, case_id=str(case.id)),
        "status": "QUEUED",
    }
