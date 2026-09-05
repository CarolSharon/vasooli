from app.services.idempotency import action_idempotency_key


def test_action_idempotency_key_is_deterministic_and_contextual():
    first = action_idempotency_key("case_1", "reminder", 1, "2026-09-01T09")
    assert first == action_idempotency_key("case_1", "reminder", 1, "2026-09-01T09")
    assert first != action_idempotency_key("case_1", "reminder", 2, "2026-09-01T09")
    assert len(first) == 64
