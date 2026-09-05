from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query

from app.config import get_settings
from app.database import get_case, initialize_database, list_audit, list_cases
from app.dataset import generate_development_cases
from app.degradation import detect_degradation
from app.schemas import (
    CaseType,
    DegradationRequest,
    PromiseRequest,
    RecoveryCase,
    VoiceTurnRequest,
    WorkflowResult,
)
from app.workflows import (
    evaluate_promise,
    execute_workflow,
    process_voice_turn,
    record_promise,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="Vasooli Revenue Recovery API",
    version="0.2.0",
    description="Seven bounded recovery workflows with audit trails.",
    lifespan=lifespan,
)


@app.get("/health")
def health() -> dict:
    settings = get_settings()
    return {
        "status": "ok",
        "openai_enabled": settings.openai_enabled and bool(settings.openai_api_key),
        "fallback_available": True,
        "workflows": [item.value for item in CaseType],
    }


@app.post("/workflows/payment-degradation")
def payment_degradation(request: DegradationRequest) -> dict:
    return detect_degradation(request)


@app.post("/workflows/checkout-dropoff", response_model=WorkflowResult)
def checkout_dropoff(case: RecoveryCase) -> WorkflowResult:
    case.case_type = CaseType.CHECKOUT_ABANDONMENT
    return execute_workflow(case, get_settings())


@app.post("/workflows/subscription-recovery", response_model=WorkflowResult)
def subscription_recovery(case: RecoveryCase) -> WorkflowResult:
    case.case_type = CaseType.SUBSCRIPTION_FAILURE
    return execute_workflow(case, get_settings())


@app.post("/workflows/b2b-receivables", response_model=WorkflowResult)
def b2b_receivables(case: RecoveryCase) -> WorkflowResult:
    case.case_type = CaseType.B2B_INVOICE
    return execute_workflow(case, get_settings())


@app.post("/workflows/mandate-retry", response_model=WorkflowResult)
def mandate_retry(case: RecoveryCase) -> WorkflowResult:
    case.case_type = CaseType.MANDATE_RETRY
    return execute_workflow(case, get_settings())


@app.post("/workflows/voice/turn")
def hinglish_voice_turn(request: VoiceTurnRequest) -> dict:
    if get_case(request.case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return process_voice_turn(request)


@app.post("/workflows/promises")
def create_promise(request: PromiseRequest) -> dict:
    if get_case(request.case_id) is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return record_promise(request)


@app.post("/workflows/promises/{case_id}/evaluate")
def check_promise(case_id: str) -> dict:
    payload = get_case(case_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Case not found")
    return evaluate_promise(RecoveryCase.model_validate(payload))


@app.post("/cases/process", response_model=WorkflowResult)
def process_case(case: RecoveryCase) -> WorkflowResult:
    return execute_workflow(case, get_settings())


@app.get("/cases")
def cases() -> list[dict]:
    return list_cases()


@app.get("/audit")
def audit(case_id: str | None = Query(default=None)) -> list[dict]:
    return list_audit(case_id)


@app.post("/development/run")
def run_development_batch(limit: int = Query(default=240, ge=1, le=240)) -> dict:
    settings = get_settings()
    development_cases = generate_development_cases()[:limit]
    evaluation_time = datetime(
        2026, 9, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    results = [
        execute_workflow(case=case, settings=settings, now=evaluation_time)
        for case in development_cases
    ]
    return {
        "processed": len(results),
        "allowed": sum(r.policy_decision.result.value == "allow" for r in results),
        "blocked": sum(r.policy_decision.result.value == "block" for r in results),
        "delayed": sum(r.policy_decision.result.value == "delay" for r in results),
        "escalated": sum(
            r.policy_decision.result.value == "escalate" for r in results
        ),
        "fallback_decisions": sum(r.used_fallback for r in results),
        "held_out_cases_processed": 0,
    }
