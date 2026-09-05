from collections import Counter

from app.dataset import CASE_COUNTS, generate_development_cases


def test_development_batch_is_fixed():
    first = generate_development_cases(seed=42)
    second = generate_development_cases(seed=42)
    assert len(first) == 240
    assert [case.model_dump(mode="json") for case in first] == [
        case.model_dump(mode="json") for case in second
    ]
    assert Counter(case.case_type for case in first) == Counter(CASE_COUNTS)
    assert all(
        case.metadata["dataset_split"] == "development" for case in first
    )
