from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.integrations.razorpay_client import create_order, create_payment_link
from app.models import Customer, Provenance, ProviderReference, RecoveryCase
from app.services.audit import append_audit

router = APIRouter(prefix="/api/razorpay", tags=["razorpay"])
Db = Annotated[Session, Depends(get_db)]


class CaseRequest(BaseModel):
    case_id: int


def _case_customer(db: Session, case_id: int) -> tuple[RecoveryCase, Customer]:
    case = db.get(RecoveryCase, case_id)
    if not case:
        raise HTTPException(404, "Case not found")
    customer = db.get(Customer, case.customer_id)
    if not customer:
        raise HTTPException(409, "Case has no customer")
    return case, customer


@router.post("/orders")
def new_order(body: CaseRequest, db: Db):
    case, _ = _case_customer(db, body.case_id)
    if case.payment_confirmed_at:
        raise HTTPException(409, "Payment already confirmed")
    result = create_order(
        case_id=str(case.id),
        amount_rupees=case.amount_paise / 100,
        receipt=f"vasooli-{case.case_reference[:20]}",
    )
    db.add(
        ProviderReference(
            case_id=case.id,
            provider="RAZORPAY",
            reference_type="ORDER",
            provider_reference_id=result["id"],
            provenance=Provenance.RAZORPAY_TEST,
        )
    )
    append_audit(
        db,
        case_id=case.id,
        event_type="RAZORPAY_ORDER_CREATED",
        actor="SYSTEM",
        data={"order_id": result["id"]},
    )
    db.commit()
    return {
        "key_id": settings.razorpay_key_id,
        "order_id": result["id"],
        "amount": result["amount"],
        "currency": result["currency"],
        "case_id": case.id,
    }


@router.post("/payment-links")
def new_payment_link(body: CaseRequest, db: Db):
    case, customer = _case_customer(db, body.case_id)
    if case.payment_confirmed_at:
        raise HTTPException(409, "Payment already confirmed")
    if customer.opted_out:
        raise HTTPException(403, "Customer opted out")
    if not customer.phone:
        raise HTTPException(409, "Customer has no phone")
    result = create_payment_link(
        case_id=str(case.id),
        amount_rupees=case.amount_paise / 100,
        customer_name=customer.name,
        customer_phone=customer.phone,
        customer_email=customer.email,
        description=f"Payment recovery for {case.case_reference}",
    )
    case.latest_payment_url = result["short_url"]
    db.add(
        ProviderReference(
            case_id=case.id,
            provider="RAZORPAY",
            reference_type="PAYMENT_LINK",
            provider_reference_id=result["id"],
            provenance=Provenance.RAZORPAY_TEST,
        )
    )
    append_audit(
        db,
        case_id=case.id,
        event_type="RAZORPAY_PAYMENT_LINK_CREATED",
        actor="SYSTEM",
        data={"payment_link_id": result["id"], "short_url": result["short_url"]},
    )
    db.commit()
    return {key: result[key] for key in ("id", "short_url", "status")}
