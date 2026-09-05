from uuid import uuid4

import razorpay

from app.config import settings


def _client() -> razorpay.Client:
    if not settings.razorpay_key_id or not settings.razorpay_key_secret:
        raise RuntimeError("Razorpay credentials are not configured")
    return razorpay.Client(
        auth=(settings.razorpay_key_id, settings.razorpay_key_secret)
    )


def create_order(*, case_id: str, amount_rupees: float, receipt: str) -> dict:
    return _client().order.create(
        {
            "amount": round(amount_rupees * 100),
            "currency": "INR",
            "receipt": receipt,
            "notes": {"case_id": case_id, "source": "VASOOLI"},
        }
    )


def create_payment_link(
    *,
    case_id: str,
    amount_rupees: float,
    customer_name: str,
    customer_phone: str,
    customer_email: str | None,
    description: str,
) -> dict:
    customer = {"name": customer_name, "contact": customer_phone}
    if customer_email:
        customer["email"] = customer_email
    return _client().payment_link.create(
        {
            "amount": round(amount_rupees * 100),
            "currency": "INR",
            "accept_partial": False,
            "description": description,
            "customer": customer,
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
            # Razorpay requires reference_id to be unique for every payment link.
            # Keep the stable case ID in notes so webhooks can still locate the case.
            "reference_id": f"{case_id}-{uuid4().hex}",
            "notes": {"case_id": case_id, "source": "VASOOLI"},
            "callback_url": f"{settings.frontend_url}/payment/result",
            "callback_method": "get",
        }
    )


def create_subscription(*, case_id: str, plan_id: str, total_count: int = 12) -> dict:
    return _client().subscription.create(
        {
            "plan_id": plan_id,
            "total_count": total_count,
            "customer_notify": 1,
            "notes": {"case_id": case_id, "source": "VASOOLI"},
        }
    )
