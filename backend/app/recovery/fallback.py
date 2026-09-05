from app.recovery.schemas import ActionType, AIDecision, CaseType, RecoveryCase


def deterministic_diagnosis(case: RecoveryCase) -> AIDecision:
    reason = (case.failure_reason or "unknown").lower()
    if case.case_type == CaseType.CHECKOUT_ABANDONMENT:
        return AIDecision(
            root_cause="checkout_abandoned",
            confidence=0.99,
            proposed_action=ActionType.SEND_PAYMENT_LINK,
            channel="whatsapp",
            reason_summary="Checkout began without a completed payment.",
        )
    if case.case_type == CaseType.B2B_INVOICE:
        if case.invoice_disputed:
            return AIDecision(
                root_cause="invoice_disputed",
                confidence=0.99,
                proposed_action=ActionType.ESCALATE_HUMAN,
                reason_summary="Disputed invoices require human review.",
                requires_human_review=True,
            )
        return AIDecision(
            root_cause="invoice_overdue",
            confidence=0.98,
            proposed_action=ActionType.SEND_REMINDER,
            channel="email",
            reason_summary="The undisputed invoice is overdue.",
        )
    if case.case_type == CaseType.VOICE_RECOVERY:
        return AIDecision(
            root_cause=reason,
            confidence=0.90,
            proposed_action=ActionType.PLACE_VOICE_CALL,
            channel="voice",
            reason_summary="The high-value case is eligible for bounded voice recovery.",
        )
    if case.case_type == CaseType.PROMISE_TO_PAY:
        return AIDecision(
            root_cause="payment_promised",
            confidence=0.98,
            proposed_action=ActionType.RECORD_PROMISE,
            reason_summary="The customer supplied a payment amount and date.",
        )
    if "revoked" in reason or "expired" in reason:
        return AIDecision(
            root_cause=reason,
            confidence=0.97,
            proposed_action=ActionType.REQUEST_REAUTHORIZATION,
            channel="whatsapp",
            reason_summary="The mandate or payment instrument requires reauthorization.",
        )
    if "timeout" in reason or "technical" in reason:
        return AIDecision(
            root_cause=reason,
            confidence=0.95,
            proposed_action=ActionType.RETRY_PAYMENT,
            retry_delay_hours=2,
            reason_summary="A transient failure is suitable for a delayed retry.",
        )
    if "insufficient" in reason:
        return AIDecision(
            root_cause="insufficient_funds",
            confidence=0.96,
            proposed_action=ActionType.RETRY_PAYMENT,
            retry_delay_hours=24,
            reason_summary="Insufficient funds should not be retried immediately.",
        )
    if "declin" in reason or "authentication" in reason:
        return AIDecision(
            root_cause=reason,
            confidence=0.90,
            proposed_action=ActionType.OFFER_ALTERNATIVE_METHOD,
            channel="whatsapp",
            reason_summary="An alternative method is safer than repeating a hard decline.",
        )
    return AIDecision(
        root_cause="ambiguous_failure",
        confidence=0.40,
        proposed_action=ActionType.ESCALATE_HUMAN,
        reason_summary="Available evidence is insufficient for automatic recovery.",
        requires_human_review=True,
        missing_information=["normalized failure code"],
    )
