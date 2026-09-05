import copy
import json
import random
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SOURCE = PROJECT_ROOT / "data/generated/synthetic_cases.json"
DEVELOPMENT = PROJECT_ROOT / "data/splits/development.json"
HELD_OUT = PROJECT_ROOT / "data/splits/held_out.json"
SEED = 42
EDGE_PREDICATES = {
    "opted_out": lambda case: case["opted_out"],
    "missing_whatsapp": lambda case: not case["whatsapp_consent"],
    "missing_voice": lambda case: not case["voice_consent"],
    "already_refunded": lambda case: case["already_refunded"],
    "order_cancelled": lambda case: case["order_cancelled"],
    "alternate_payment_found": lambda case: case["alternate_payment_found"],
    "revoked_mandate": lambda case: case["mandate_active"] is False,
    "invoice_disputed": lambda case: case["invoice_disputed"],
    "duplicate_webhook": lambda case: case["duplicate_webhook"],
    "out_of_order_event": lambda case: case["out_of_order_event"],
    "invalid_contact": lambda case: case["invalid_contact"],
    "failed_recovery": lambda case: case["simulated_outcome"] == "not_recovered",
    "broken_promise": lambda case: case["simulated_outcome"] == "broken_promise",
    "manual_review": lambda case: case["manual_review"],
}


def ensure_edge_coverage(development: list[dict], held_out: list[dict]) -> None:
    for predicate in EDGE_PREDICATES.values():
        for target, source in ((development, held_out), (held_out, development)):
            if any(predicate(case) for case in target):
                continue
            source_edge = next((case for case in source if predicate(case)), None)
            if source_edge is None:
                continue
            target_plain = next(
                case
                for case in target
                if case["case_type"] == source_edge["case_type"]
                and not predicate(case)
            )
            source.remove(source_edge)
            target.remove(target_plain)
            source.append(target_plain)
            target.append(source_edge)


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    grouped: dict[str, list[dict]] = defaultdict(list)
    for case in payload["cases"]:
        grouped[case["case_type"]].append(copy.deepcopy(case))

    development: list[dict] = []
    held_out: list[dict] = []
    for case_type in sorted(grouped):
        cases = sorted(grouped[case_type], key=lambda case: case["case_id"])
        random.Random(f"{SEED}:{case_type}").shuffle(cases)
        split_at = round(len(cases) * 0.8)
        development.extend(cases[:split_at])
        held_out.extend(cases[split_at:])

    ensure_edge_coverage(development, held_out)
    for case in development:
        case["dataset_split"] = "development"
        case["field_provenance"]["dataset_split"] = "DERIVED"
    for case in held_out:
        case["dataset_split"] = "held_out"
        case["field_provenance"]["dataset_split"] = "DERIVED"

    development.sort(key=lambda case: case["case_id"])
    held_out.sort(key=lambda case: case["case_id"])
    metadata = {
        "source": "data/generated/synthetic_cases.json",
        "split_seed": SEED,
        "strategy": "deterministic_stratified_80_20",
    }
    DEVELOPMENT.parent.mkdir(parents=True, exist_ok=True)
    DEVELOPMENT.write_text(
        json.dumps(
            {**metadata, "case_count": len(development), "cases": development},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    HELD_OUT.write_text(
        json.dumps(
            {**metadata, "case_count": len(held_out), "cases": held_out},
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"Development cases: {len(development)}")
    print(f"Held-out cases: {len(held_out)}")


if __name__ == "__main__":
    main()
