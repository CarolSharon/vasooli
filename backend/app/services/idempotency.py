import hashlib


def action_idempotency_key(
    case_id: str,
    action_type: str,
    attempt_number: int,
    scheduled_bucket: str,
) -> str:
    raw = f"{case_id}:{action_type}:{attempt_number}:{scheduled_bucket}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()
