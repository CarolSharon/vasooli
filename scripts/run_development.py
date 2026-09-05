from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import get_settings
from app.database import initialize_database
from app.dataset import generate_development_cases
from app.workflows import execute_workflow


def main() -> None:
    initialize_database()
    settings = get_settings()
    cases = generate_development_cases()
    evaluation_time = datetime(
        2026, 9, 1, 12, tzinfo=ZoneInfo("Asia/Kolkata")
    )
    results = [
        execute_workflow(case=case, settings=settings, now=evaluation_time)
        for case in cases
    ]
    policy_counts = Counter(
        result.policy_decision.result.value for result in results
    )
    model_counts = Counter(result.selected_model for result in results)
    print(
        {
            "processed": len(results),
            "policy_results": dict(policy_counts),
            "model_routes": dict(model_counts),
            "fallback_decisions": sum(result.used_fallback for result in results),
            "held_out_processed": 0,
        }
    )


if __name__ == "__main__":
    main()
