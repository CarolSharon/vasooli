from twilio.rest import Client

from app.config import settings


def _client() -> Client:
    if not settings.twilio_account_sid or not settings.twilio_auth_token:
        raise RuntimeError("Twilio credentials are not configured")
    return Client(settings.twilio_account_sid, settings.twilio_auth_token)


def normalize_whatsapp_number(number: str) -> str:
    return number if number.startswith("whatsapp:") else f"whatsapp:{number}"


def send_whatsapp(*, to: str, message: str) -> str:
    result = _client().messages.create(
        from_=settings.twilio_whatsapp_from,
        to=normalize_whatsapp_number(to),
        body=message,
    )
    return str(result.sid)


def start_voice_call(*, to: str, case_id: str) -> str:
    if not settings.twilio_voice_from:
        raise RuntimeError("Twilio voice number is not configured")
    result = _client().calls.create(
        from_=settings.twilio_voice_from,
        to=to,
        url=f"{settings.public_api_url}/api/twilio/voice?case_id={case_id}",
        status_callback=f"{settings.public_api_url}/api/twilio/voice/status",
        status_callback_event=["initiated", "ringing", "answered", "completed"],
    )
    return str(result.sid)
