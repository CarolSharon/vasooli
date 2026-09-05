import copy
import json
import random
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = PROJECT_ROOT / "data/raw/razorpay"
OUTPUT = PROJECT_ROOT / "data/enriched/augmented_cases.json"
SEED = 42


def payment_entity(payload: dict) -> dict:
    return (
        payload.get("raw_payload", {})
        .get("payload", {})
        .get("payment", {})
        .get("entity", {})
    )


def main() -> None:
    random.seed(SEED)
    sources = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(SOURCE_DIR.glob("event_*.json"))
    ]
    cases = []
    for index, source in enumerate(sources, start=1):
        entity = payment_entity(source)
        tenure = random.randint(1, 48)
        historical_failures = random.randint(0, 6)
        amount = entity.get("amount") or 0
        synthetic_context = {
            "customer_reference": f"synthetic_customer_{index:04d}",
            "customer_tenure_months": tenure,
            "historical_failures": historical_failures,
            "lifetime_value_paise": max(amount, amount * random.randint(2, 15)),
            "preferred_language": random.choice(["en", "hi", "hinglish", "ta"]),
            "whatsapp_consent": bool(random.getrandbits(1)),
            "voice_consent": bool(random.getrandbits(1)),
        }
        cases.append(
            {
                "case_id": f"razorpay_case_{index:04d}",
                "provider_record": copy.deepcopy(source),
                "synthetic_context": synthetic_context,
                "derived_context": {
                    "failure_count_band": "high" if historical_failures >= 3 else "low",
                    "value_band": "high"
                    if synthetic_context["lifetime_value_paise"] >= 500_000
                    else "standard",
                },
                "provenance": {
                    "provider_record": "RAZORPAY_TEST",
                    "synthetic_context": "SYNTHETIC",
                    "derived_context": "DERIVED",
                },
            }
        )
    payload = {
        "dataset_type": "razorpay_augmented",
        "augmentation_version": "1.0.0",
        "seed": SEED,
        "case_count": len(cases),
        "cases": cases,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Augmented {len(cases)} sanitized Razorpay events at {OUTPUT}")


if __name__ == "__main__":
    main()
