import json
import sqlite3
from contextlib import contextmanager
from datetime import UTC, datetime

from app.config import get_settings

SCHEMA = """
CREATE TABLE IF NOT EXISTS cases (
    case_id TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recovery_actions (
    action_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL,
    action_type TEXT NOT NULL,
    status TEXT NOT NULL,
    idempotency_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    event_type TEXT NOT NULL,
    actor TEXT NOT NULL,
    decision TEXT,
    reason TEXT,
    metadata_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS promises (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    case_id TEXT NOT NULL,
    amount_paise INTEGER NOT NULL,
    promise_date TEXT NOT NULL,
    source TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat()


@contextmanager
def connection():
    database = sqlite3.connect(get_settings().database_path)
    database.row_factory = sqlite3.Row
    try:
        yield database
        database.commit()
    finally:
        database.close()


def initialize_database() -> None:
    with connection() as database:
        database.executescript(SCHEMA)


def upsert_case(payload: dict) -> None:
    now = utc_now()
    with connection() as database:
        database.execute(
            """
            INSERT INTO cases(case_id, payload_json, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(case_id) DO UPDATE SET
                payload_json = excluded.payload_json,
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (
                payload["case_id"],
                json.dumps(payload, default=str),
                payload["status"],
                now,
                now,
            ),
        )


def get_case(case_id: str) -> dict | None:
    with connection() as database:
        row = database.execute(
            "SELECT payload_json FROM cases WHERE case_id = ?", (case_id,)
        ).fetchone()
    return None if row is None else json.loads(row["payload_json"])


def list_cases() -> list[dict]:
    with connection() as database:
        rows = database.execute(
            "SELECT payload_json FROM cases ORDER BY case_id"
        ).fetchall()
    return [json.loads(row["payload_json"]) for row in rows]


def insert_action(action: dict) -> bool:
    try:
        with connection() as database:
            database.execute(
                """
                INSERT INTO recovery_actions(
                    action_id, case_id, action_type, status,
                    idempotency_key, payload_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    action["action_id"],
                    action["case_id"],
                    action["action_type"],
                    action["status"],
                    action["idempotency_key"],
                    json.dumps(action, default=str),
                    utc_now(),
                ),
            )
        return True
    except sqlite3.IntegrityError:
        return False


def insert_audit(
    case_id: str,
    event_type: str,
    actor: str,
    decision: str | None,
    reason: str | None,
    metadata: dict | None = None,
) -> int:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO audit_events(
                case_id, event_type, actor, decision,
                reason, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                case_id,
                event_type,
                actor,
                decision,
                reason,
                json.dumps(metadata or {}, default=str),
                utc_now(),
            ),
        )
        return int(cursor.lastrowid)


def list_audit(case_id: str | None = None) -> list[dict]:
    query = "SELECT * FROM audit_events"
    parameters: tuple = ()
    if case_id:
        query += " WHERE case_id = ?"
        parameters = (case_id,)
    query += " ORDER BY id"
    with connection() as database:
        rows = database.execute(query, parameters).fetchall()
    return [
        {**dict(row), "metadata": json.loads(row["metadata_json"])}
        for row in rows
    ]


def insert_promise(
    case_id: str, amount_paise: int, promise_date: str, source: str
) -> int:
    with connection() as database:
        cursor = database.execute(
            """
            INSERT INTO promises(
                case_id, amount_paise, promise_date, source, status, created_at
            ) VALUES (?, ?, ?, ?, 'pending', ?)
            """,
            (case_id, amount_paise, promise_date, source, utc_now()),
        )
        return int(cursor.lastrowid)
