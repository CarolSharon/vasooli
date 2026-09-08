from app.recovery.schemas import ActionType, DegradationRequest


def detect_degradation(request: DegradationRequest) -> dict:
    increase = request.current_failure_rate - request.baseline_failure_rate
    ratio = (
        request.current_failure_rate / request.baseline_failure_rate
        if request.baseline_failure_rate > 0
        else 99.0
    )
    degraded = increase >= 0.08 and ratio >= 2.0
    if degraded:
        root_cause = (
            "bank_or_method_degradation"
            if request.bank
            else "payment_method_degradation"
        )
        action = ActionType.PAUSE_RETRIES
    else:
        root_cause = "within_expected_range"
        action = ActionType.NO_ACTION
    return {
        "degraded": degraded,
        "root_cause": root_cause,
        "failure_rate_increase": round(increase, 4),
        "failure_rate_ratio": round(ratio, 2),
        "recommended_action": action.value,
        "affected_amount_paise": request.affected_amount_paise,
        "group": {"payment_method": request.payment_method, "bank": request.bank},
    }
