from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from app.models import Customer, PromiseToPay
from app.services.audit import append_audit


def execute_voice_tool(db: Session, *, case, name: str, arguments: dict) -> dict:
    customer = db.get(Customer, case.customer_id)
    if case.payment_confirmed_at:
        return {"ok": False, "blocked_by": "PAYMENT_CONFIRMED"}
    if name not in {"opt_out", "open_dispute"}:
        if customer and customer.opted_out:
            return {"ok": False, "blocked_by": "OPT_OUT"}
        if case.invoice_disputed:
            return {"ok": False, "blocked_by": "ACTIVE_DISPUTE"}
    try:
        if name == "send_payment_link":
            result = (
                {"ok": True, "payment_url": case.latest_payment_url}
                if case.latest_payment_url
                else {"ok": False, "blocked_by": "NO_PAYMENT_LINK"}
            )
        elif name == "record_promise":
            due = date.fromisoformat(arguments["due_date"])
            if due <= datetime.now(timezone.utc).date():
                return {"ok": False, "blocked_by": "INVALID_PROMISE_DATE"}
            db.add(
                PromiseToPay(
                    case_id=case.id,
                    promised_amount_paise=case.amount_paise,
                    promised_date=due,
                    status="PENDING",
                    source="VOICE",
                )
            )
            case.status = "PROMISE_PENDING"
            result = {"ok": True, "due_date": due.isoformat()}
        elif name == "schedule_callback":
            when = datetime.fromisoformat(arguments["when"])
            case.next_action_at = when
            result = {"ok": True, "callback_at": when.isoformat()}
        elif name == "open_dispute":
            case.invoice_disputed = True
            case.status = "HUMAN_ESCALATION"
            result = {"ok": True, "recovery_paused": True}
        elif name == "opt_out":
            if customer:
                customer.opted_out = True
            case.status = "BLOCKED"
            result = {"ok": True, "recovery_stopped": True}
        elif name == "human_transfer":
            case.status = "HUMAN_ESCALATION"
            result = {"ok": True, "transfer_requested": True}
        else:
            result = {"ok": False, "blocked_by": "UNKNOWN_TOOL"}
    except (KeyError, ValueError):
        result = {"ok": False, "blocked_by": "INVALID_ARGUMENTS"}
    append_audit(
        db,
        case_id=case.id,
        event_type=f"VOICE_TOOL_{name.upper()}",
        actor="VOICE_AGENT",
        data={"arguments": arguments, "result": result},
    )
    db.commit()
    return result
