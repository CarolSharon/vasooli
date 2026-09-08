from sqlalchemy.orm import Session

from app.integrations.twilio_client import send_whatsapp
from app.models import CommunicationEvent, Customer, RecoveryCase
from app.services.audit import append_audit


def send_recovery_message(
    database: Session,
    case: RecoveryCase,
    customer: Customer,
    payment_url: str,
) -> str:
    if case.payment_confirmed_at:
        raise ValueError("STOP_PAYMENT_CONFIRMED")
    if customer.opted_out:
        raise ValueError("STOP_OPTED_OUT")
    if not customer.whatsapp_consent:
        raise ValueError("STOP_NO_CONSENT")
    if not customer.phone:
        raise ValueError("STOP_NO_PHONE")
    message = (
        f"Namaste {customer.name}, aapka ₹{case.amount_paise / 100:.2f} payment "
        f"complete nahi hua. Secure payment link: {payment_url}\n\n"
        "Reply PAY for the link, FRIDAY or another date for a promise, "
        "LATER for a callback, DISPUTE for help, HUMAN for an agent, "
        "or STOP to opt out."
    )
    sid = send_whatsapp(to=customer.phone, message=message)
    database.add(
        CommunicationEvent(
            case_id=case.id,
            channel="WHATSAPP",
            direction="OUTBOUND",
            provider_message_id=sid,
            status="SENT",
            body=message,
            metadata_json={"payment_url": payment_url},
        )
    )
    append_audit(
        database,
        case_id=case.id,
        event_type="WHATSAPP_SENT",
        actor="SYSTEM",
        data={"message_sid": sid},
    )
    database.commit()
    return sid
