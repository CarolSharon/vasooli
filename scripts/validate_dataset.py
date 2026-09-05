import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import ValidationError

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

from app.schemas.dataset import DatasetCase, Provenance

EXPECTED_COUNTS = {
    "control_success": 105,
    "payment_failure": 60,
    "checkout_abandonment": 45,
    "subscription_failure": 40,
    "b2b_invoice": 30,
    "promise_to_pay": 20,
}
QUOTAS = {
    "opted_out": 12,
    "missing_whatsapp": 10,
    "missing_voice": 20,
    "already_refunded": 8,
    "order_cancelled": 8,
    "alternate_payment_found": 7,
    "revoked_mandate": 6,
    "invoice_disputed": 5,
    "duplicate_webhook": 5,
    "out_of_order_event": 5,
    "invalid_contact": 6,
    "failed_recovery": 30,
    "broken_promise": 8,
    "manual_review": 8,
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_augmented(path: Path) -> list[str]:
    payload = load_json(path)
    cases = payload.get("cases", [])
    source_by_id = {
        load_json(source)["provider_event_id"]: load_json(source)
        for source in sorted((PROJECT_ROOT / "data/raw/razorpay").glob("event_*.json"))
    }
    errors = []
    for case in cases:
        provider = case.get("provider_record", {})
        event_id = provider.get("provider_event_id")
        if event_id not in source_by_id or provider != source_by_id[event_id]:
            errors.append(f"provider record overwritten: {case.get('case_id')}")
        provenance = case.get("provenance", {})
        if provenance.get("provider_record") != Provenance.RAZORPAY_TEST.value:
            errors.append(f"invalid provider provenance: {case.get('case_id')}")
        if provenance.get("synthetic_context") != Provenance.SYNTHETIC.value:
            errors.append(f"invalid synthetic provenance: {case.get('case_id')}")
        if provenance.get("derived_context") != Provenance.DERIVED.value:
            errors.append(f"invalid derived provenance: {case.get('case_id')}")
    if len(cases) != len(source_by_id):
        errors.append("augmented case count does not match sanitized source count")
    return errors


def quota_counts(cases: list[dict]) -> dict[str, int]:
    return {
        "opted_out": sum(case["opted_out"] for case in cases),
        "missing_whatsapp": sum(not case["whatsapp_consent"] for case in cases),
        "missing_voice": sum(not case["voice_consent"] for case in cases),
        "already_refunded": sum(case["already_refunded"] for case in cases),
        "order_cancelled": sum(case["order_cancelled"] for case in cases),
        "alternate_payment_found": sum(
            case["alternate_payment_found"] for case in cases
        ),
        "revoked_mandate": sum(case["mandate_active"] is False for case in cases),
        "invoice_disputed": sum(case["invoice_disputed"] for case in cases),
        "duplicate_webhook": sum(case["duplicate_webhook"] for case in cases),
        "out_of_order_event": sum(case["out_of_order_event"] for case in cases),
        "invalid_contact": sum(case["invalid_contact"] for case in cases),
        "failed_recovery": sum(
            case["simulated_outcome"] == "not_recovered" for case in cases
        ),
        "broken_promise": sum(
            case["simulated_outcome"] == "broken_promise" for case in cases
        ),
        "manual_review": sum(case["manual_review"] for case in cases),
    }


def validate_cases(
    cases: list[dict], *, full: bool = True
) -> tuple[list[str], int, int]:
    errors: list[str] = []
    schema_errors = 0
    validated = []
    for position, raw_case in enumerate(cases):
        try:
            validated.append(
                DatasetCase.model_validate(raw_case).model_dump(mode="json")
            )
        except ValidationError as error:
            schema_errors += 1
            errors.append(f"schema error at case {position}: {error}")
    if schema_errors:
        return errors, schema_errors, 0

    ids = [case["case_id"] for case in validated]
    if len(ids) != len(set(ids)):
        errors.append("duplicated case IDs")
    if any(not case["customer_id"].startswith("customer_") for case in validated):
        errors.append("invalid customer ID")
    distribution_errors = 0
    if full:
        counts = Counter(case["case_type"] for case in validated)
        if len(validated) != 300:
            errors.append(f"expected 300 cases, found {len(validated)}")
        if dict(counts) != EXPECTED_COUNTS:
            distribution_errors += 1
            errors.append(f"case distribution mismatch: {dict(counts)}")
        counts_by_quota = quota_counts(validated)
        for name, minimum in QUOTAS.items():
            if counts_by_quota[name] < minimum:
                errors.append(f"quota {name} below {minimum}: {counts_by_quota[name]}")

    allowed = {item.value for item in Provenance}
    for case in validated:
        if case["amount_paise"] < 0 or case["recovered_amount_paise"] < 0:
            errors.append(f"negative money: {case['case_id']}")
        if case["recovered_amount_paise"] > case["amount_paise"]:
            errors.append(f"recovery exceeds amount: {case['case_id']}")
        if (
            case["case_type"] == "control_success"
            and case["failure_reason"] is not None
        ):
            errors.append(f"control has failure reason: {case['case_id']}")
        if (
            case["case_type"] != "subscription_failure"
            and case["subscription_age_months"]
        ):
            errors.append(f"invalid subscription age: {case['case_id']}")
        if (
            case["mandate_active"] is False
            and case["case_type"] != "subscription_failure"
        ):
            errors.append(f"invalid revoked mandate: {case['case_id']}")
        if case["simulated_outcome"] == "broken_promise" and not case["promise_date"]:
            errors.append(f"broken promise lacks date: {case['case_id']}")
        if case["opted_out"] and case["expected_policy"] not in {"BLOCK", "ESCALATE"}:
            errors.append(f"opted-out contact allowed: {case['case_id']}")
        if case["already_refunded"] and case["recovered_amount_paise"]:
            errors.append(f"refunded case recovered: {case['case_id']}")
        provenance = case["field_provenance"]
        expected_provenance_fields = set(case) - {"field_provenance"}
        if set(provenance) != expected_provenance_fields:
            errors.append(f"incomplete provenance: {case['case_id']}")
        if not set(provenance.values()).issubset(allowed):
            errors.append(f"invalid provenance: {case['case_id']}")
        if any(
            label == Provenance.RAZORPAY_TEST.value
            for field, label in provenance.items()
            if field != "source_event_id"
        ):
            errors.append(f"synthetic field labelled RAZORPAY_TEST: {case['case_id']}")
        source = case.get("source_event_id") or ""
        if (
            source.startswith(("evt_", "pay_"))
            and provenance.get("source_event_id") != Provenance.RAZORPAY_TEST.value
        ):
            errors.append(f"real-looking unlabelled source event: {case['case_id']}")
    return errors, schema_errors, distribution_errors


def validate_split(development: Path, held_out: Path) -> list[str]:
    dev = load_json(development)["cases"]
    held = load_json(held_out)["cases"]
    errors = []
    if len(dev) != 240 or len(held) != 60:
        errors.append(f"invalid split sizes: {len(dev)}/{len(held)}")
    dev_ids = {case["case_id"] for case in dev}
    held_ids = {case["case_id"] for case in held}
    if dev_ids & held_ids:
        errors.append("split overlap")
    if len(dev_ids | held_ids) != 300:
        errors.append("split missing cases")
    for label, subset in (("development", dev), ("held_out", held)):
        if {case["case_type"] for case in subset} != set(EXPECTED_COUNTS):
            errors.append(f"{label} lacks a workflow")
        expected_label = "development" if label == "development" else "held_out"
        if any(case["dataset_split"] != expected_label for case in subset):
            errors.append(f"{label} contains wrong split labels")
        counts = quota_counts(subset)
        for edge, count in counts.items():
            if count == 0:
                errors.append(f"{label} lacks edge case: {edge}")
    return errors


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--file",
        type=Path,
        default=PROJECT_ROOT / "data/generated/synthetic_cases.json",
    )
    parser.add_argument("--development", type=Path)
    parser.add_argument("--held-out", type=Path)
    args = parser.parse_args()

    if args.development or args.held_out:
        if not args.development or not args.held_out:
            parser.error("--development and --held-out must be supplied together")
        errors = validate_split(args.development, args.held_out)
        if errors:
            print("Dataset split validation failed", *errors, sep="\n")
            raise SystemExit(1)
        print(
            "Development cases: 240\nHeld-out cases: 60\nOverlap: 0\nMissing cases: 0\nStratification: passed"
        )
        return

    payload = load_json(args.file)
    if payload.get("dataset_type") == "razorpay_augmented":
        errors = validate_augmented(args.file)
        if errors:
            print("Augmented dataset validation failed", *errors, sep="\n")
            raise SystemExit(1)
        print(
            f"Augmented dataset validation passed\nCases: {len(payload['cases'])}\nProvider records unchanged: yes"
        )
        return

    errors, schema_errors, distribution_errors = validate_cases(
        payload.get("cases", [])
    )
    if errors:
        print("Dataset validation failed", *errors, sep="\n")
        raise SystemExit(1)
    print(
        "Dataset validation passed\n"
        f"Cases: {len(payload['cases'])}\n"
        f"Schema errors: {schema_errors}\n"
        f"Distribution errors: {distribution_errors}\n"
        "Impossible combinations: 0\n"
        "Required edge-case quotas: passed"
    )


if __name__ == "__main__":
    main()
