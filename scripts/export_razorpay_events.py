import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import psycopg
from dotenv import dotenv_values

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = PROJECT_ROOT / "data" / "raw" / "razorpay"
SENSITIVE_KEYS = {
    "account_number",
    "address",
    "card_id",
    "contact",
    "customer_id",
    "email",
    "international",
    "iin",
    "last4",
    "name",
    "notes",
    "phone",
    "token_id",
    "token_iin",
    "vpa",
}


def sanitize(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "[REDACTED]" if key.lower() in SENSITIVE_KEYS else sanitize(item)
            for key, item in value.items()
        }

    if isinstance(value, list):
        return [sanitize(item) for item in value]

    return value


def database_url() -> str:
    values = dotenv_values(PROJECT_ROOT / ".env")
    url = values.get("DATABASE_URL")

    if not url:
        raise RuntimeError("DATABASE_URL is missing from .env")

    return url.replace("postgresql+psycopg://", "postgresql://", 1)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    query = """
        SELECT provider_event_id, raw_payload, received_at
        FROM payment_events
        WHERE provider = 'razorpay'
        ORDER BY received_at, id
    """

    with (
        psycopg.connect(database_url()) as connection,
        connection.cursor() as cursor,
    ):
        cursor.execute(query)
        rows = cursor.fetchall()

    for index, (event_id, payload, captured_at) in enumerate(rows, start=1):
        record = {
            "provider": "razorpay",
            "environment": "test",
            "provider_event_id": event_id,
            "raw_payload": sanitize(payload),
            "captured_at": captured_at.isoformat()
            if isinstance(captured_at, datetime)
            else str(captured_at),
            "sanitized": True,
        }
        destination = args.output / f"event_{index:03d}.json"
        destination.write_text(
            json.dumps(record, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(f"Exported {len(rows)} sanitized Razorpay events to {args.output}")


if __name__ == "__main__":
    main()
