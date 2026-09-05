import json
import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

from app.schemas.dataset import CaseType, DatasetCase, Provenance

DATASET_SEED = 42
OUTCOME_SEED = 2026
EVALUATION_TIME = datetime.fromisoformat("2026-09-01T09:00:00+05:30")
OUTPUT = PROJECT_ROOT / "data" / "generated" / "synthetic_cases.json"
CASE_COUNTS = {
    CaseType.CONTROL_SUCCESS: 105,
    CaseType.PAYMENT_FAILURE: 60,
    CaseType.CHECKOUT_ABANDONMENT: 45,
    CaseType.SUBSCRIPTION_FAILURE: 40,
    CaseType.B2B_INVOICE: 30,
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
    "blocked_suspicious",
]
FAILURE_WEIGHTS = [30, 20, 15, 10, 10, 7, 5, 3]
LANGUAGES = ["en", "hi", "hinglish", "ta", "te", "mr"]
PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet"]


def choose_indexes(
    cases: list[dict], predicate, count: int, offset: int = 0
) -> list[int]:
    candidates = [index for index, case in enumerate(cases) if predicate(case)]
    if len(candidates) < count:
        raise ValueError(f"Not enough eligible cases for quota {count}")
    return [
        candidates[(offset + position) % len(candidates)] for position in range(count)
    ]


def build_cases() -> list[dict]:
    random.seed(DATASET_SEED)
    np.random.seed(DATASET_SEED)
    outcome_random = random.Random(OUTCOME_SEED)
    cases: list[dict] = []
    sequence = 1

    for case_type, count in CASE_COUNTS.items():
        for _ in range(count):
            is_control = case_type == CaseType.CONTROL_SUCCESS
            is_subscription = case_type == CaseType.SUBSCRIPTION_FAILURE
            is_promise = case_type == CaseType.PROMISE_TO_PAY
            amount = int(np.clip(np.random.lognormal(10.2, 0.9), 5000, 5_000_000))
            occurred_at = EVALUATION_TIME - timedelta(
                days=random.randint(0, 120),
                hours=random.randint(0, 23),
                minutes=random.randint(0, 59),
            )
            failure_reason = (
                None
                if is_control
                else random.choices(FAILURE_REASONS, weights=FAILURE_WEIGHTS, k=1)[0]
            )
            if failure_reason == "mandate_revoked" and not is_subscription:
                failure_reason = "issuer_declined"
            historical_failures = 0 if is_control else random.randint(1, 8)
            lifetime_value = max(
                amount,
                amount * random.randint(2, 20) + random.randint(0, 50000),
            )
            promise_date = (
                (EVALUATION_TIME + timedelta(days=random.randint(1, 14))).date()
                if is_promise
                else None
            )
            case = {
                "case_id": f"case_{sequence:04d}",
                "customer_id": f"customer_{sequence:04d}",
                "case_type": case_type.value,
                "amount_paise": amount,
                "currency": "INR",
                "status": "paid" if is_control else "at_risk",
                "failure_reason": failure_reason,
                "payment_method": random.choice(PAYMENT_METHODS),
                "attempt_count": 0 if is_control else random.randint(1, 3),
                "occurred_at": occurred_at.isoformat(),
                "dataset_split": None,
                "contact_consent": True,
                "whatsapp_consent": True,
                "voice_consent": True,
                "opted_out": False,
                "already_refunded": False,
                "order_cancelled": False,
                "alternate_payment_found": False,
                "invoice_disputed": False,
                "mandate_active": False
                if failure_reason == "mandate_revoked"
                else (True if is_subscription else None),
                "duplicate_webhook": False,
                "out_of_order_event": False,
                "invalid_contact": False,
                "manual_review": False,
                "historical_failures": historical_failures,
                "subscription_age_months": random.randint(1, 48)
                if is_subscription
                else 0,
                "lifetime_value_paise": lifetime_value,
                "preferred_language": random.choice(LANGUAGES),
                "timezone": "Asia/Kolkata",
                "reminder_count": 0 if is_control else random.randint(0, 3),
                "voice_call_count": 0 if is_control else random.randint(0, 1),
                "promise_date": promise_date.isoformat() if promise_date else None,
                "recovered_amount_paise": amount if is_control else 0,
                "expected_policy": "NO_ACTION" if is_control else "ALLOW",
                "simulated_outcome": "confirmed_paid"
                if is_control
                else outcome_random.choice(
                    ["recovered", "not_recovered", "not_recovered", "pending"]
                ),
                "source_event_id": f"synthetic_event_{sequence:04d}",
            }
            provenance = {
                field: (
                    Provenance.SIMULATED_OUTCOME.value
                    if field == "simulated_outcome"
                    else Provenance.DERIVED.value
                    if field in {"expected_policy", "recovered_amount_paise"}
                    else Provenance.SYNTHETIC.value
                )
                for field in case
            }
            case["field_provenance"] = provenance
            cases.append(case)
            sequence += 1

    non_control = lambda case: case["case_type"] != CaseType.CONTROL_SUCCESS.value
    subscription = lambda case: case["case_type"] == CaseType.SUBSCRIPTION_FAILURE.value
    invoice = lambda case: case["case_type"] == CaseType.B2B_INVOICE.value
    promise = lambda case: case["case_type"] == CaseType.PROMISE_TO_PAY.value
    refundable = lambda case: (
        case["case_type"]
        in {
            CaseType.PAYMENT_FAILURE.value,
            CaseType.CHECKOUT_ABANDONMENT.value,
        }
    )

    for index in choose_indexes(cases, non_control, 12, 3):
        cases[index]["opted_out"] = True
        cases[index]["contact_consent"] = False
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(cases, non_control, 10, 25):
        cases[index]["whatsapp_consent"] = False
    for index in choose_indexes(cases, non_control, 20, 50):
        cases[index]["voice_consent"] = False
    for index in choose_indexes(cases, refundable, 8, 7):
        cases[index]["already_refunded"] = True
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(cases, refundable, 8, 31):
        cases[index]["order_cancelled"] = True
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(
        cases,
        lambda case: case["case_type"] == CaseType.CHECKOUT_ABANDONMENT.value,
        7,
        4,
    ):
        cases[index]["alternate_payment_found"] = True
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(cases, subscription, 6, 2):
        cases[index]["failure_reason"] = "mandate_revoked"
        cases[index]["mandate_active"] = False
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(cases, invoice, 5, 3):
        cases[index]["invoice_disputed"] = True
        cases[index]["expected_policy"] = "ESCALATE"
    for index in choose_indexes(cases, non_control, 5, 70):
        cases[index]["duplicate_webhook"] = True
    for index in choose_indexes(cases, non_control, 5, 90):
        cases[index]["out_of_order_event"] = True
    for index in choose_indexes(cases, non_control, 6, 110):
        cases[index]["invalid_contact"] = True
        cases[index]["contact_consent"] = False
        cases[index]["expected_policy"] = "BLOCK"
    for index in choose_indexes(cases, non_control, 35, 130):
        cases[index]["simulated_outcome"] = "not_recovered"
    for index in choose_indexes(cases, promise, 8, 1):
        cases[index]["simulated_outcome"] = "broken_promise"
    for index in choose_indexes(cases, non_control, 8, 170):
        cases[index]["manual_review"] = True
        cases[index]["expected_policy"] = "ESCALATE"

    return [DatasetCase.model_validate(case).model_dump(mode="json") for case in cases]


def main() -> None:
    cases = build_cases()
    payload = {
        "generator_version": "1.0.0",
        "dataset_seed": DATASET_SEED,
        "outcome_seed": OUTCOME_SEED,
        "generated_at": EVALUATION_TIME.isoformat(),
        "case_count": len(cases),
        "distribution": {
            case_type.value: count for case_type, count in CASE_COUNTS.items()
        },
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Generated {len(cases)} deterministic cases at {OUTPUT}")


if __name__ == "__main__":
    main()
