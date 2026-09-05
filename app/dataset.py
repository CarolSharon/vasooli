import random
from datetime import UTC, date, datetime, timedelta

from app.schemas import CaseType, RecoveryCase

CASE_COUNTS = {
    CaseType.PAYMENT_FAILURE: 55,
    CaseType.CHECKOUT_ABANDONMENT: 45,
    CaseType.SUBSCRIPTION_FAILURE: 40,
    CaseType.B2B_INVOICE: 30,
    CaseType.MANDATE_RETRY: 30,
    CaseType.VOICE_RECOVERY: 20,
    CaseType.PROMISE_TO_PAY: 20,
}
FAILURE_REASONS = [
    "insufficient_funds",
    "issuer_declined",
    "bank_timeout",
    "authentication_failed",
    "expired_card",
    "mandate_revoked",
    "technical_error",
]
FAILURE_WEIGHTS = [30, 20, 15, 10, 10, 7, 8]


def generate_development_cases(seed: int = 42) -> list[RecoveryCase]:
    randomizer = random.Random(seed)
    anchor = datetime(2026, 9, 1, 12, tzinfo=UTC)
    cases: list[RecoveryCase] = []
    index = 0
    for case_type, count in CASE_COUNTS.items():
        for _ in range(count):
            index += 1
            failure_reason = randomizer.choices(
                FAILURE_REASONS, weights=FAILURE_WEIGHTS, k=1
            )[0]
            if randomizer.random() < 0.82:
                amount_rupees = randomizer.randint(200, 5_000)
            else:
                amount_rupees = randomizer.randint(5_001, 50_000)
            is_voice_case = case_type == CaseType.VOICE_RECOVERY
            is_promise_case = case_type == CaseType.PROMISE_TO_PAY
            is_invoice_case = case_type == CaseType.B2B_INVOICE
            cases.append(
                RecoveryCase(
                    case_id=f"dev_{index:04d}",
                    case_type=case_type,
                    customer_id=f"cust_{randomizer.randint(1, 180):04d}",
                    amount_paise=amount_rupees * 100,
                    failure_reason=failure_reason,
                    payment_method=randomizer.choice(
                        ["upi", "card", "netbanking", "mandate"]
                    ),
                    attempted_at=anchor
                    - timedelta(hours=randomizer.randint(1, 720)),
                    mandate_active=failure_reason != "mandate_revoked",
                    voice_consent=is_voice_case,
                    invoice_disputed=is_invoice_case and index % 11 == 0,
                    opted_out=index % 29 == 0,
                    already_refunded=index % 37 == 0,
                    is_ambiguous=index % 19 == 0,
                    promise_date=date(2026, 9, 5) if is_promise_case else None,
                    promised_amount_paise=amount_rupees * 100
                    if is_promise_case
                    else None,
                    metadata={"dataset_split": "development", "dataset_seed": seed},
                )
            )
    assert len(cases) == 240
    return cases
