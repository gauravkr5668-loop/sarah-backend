"""
Sarah — Database layer.

Manages the SQLite connection, schema creation, and all CRUD operations.
WAL journal mode is enabled for safe concurrent read/write access under
Gunicorn workers.

Schema
------
Table: calls
    id           INTEGER  PRIMARY KEY AUTOINCREMENT
    created_at   TEXT     ISO-8601 UTC timestamp
    caller_name  TEXT     Customer's name (extracted from transcript)
    phone        TEXT     Customer's phone number
    suburb       TEXT     Suburb / locality
    service      TEXT     Trade service requested
    urgency      TEXT     emergency | urgent | standard | unknown
    summary      TEXT     Human-readable call summary
    transcript   TEXT     Full call transcript
    raw_json     TEXT     Complete Vapi payload (JSON string)
    call_id      TEXT     Vapi's unique call ID (UNIQUE constraint)
"""

import json
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# DDL
# --------------------------------------------------------------------------- #

_DDL_CREATE_CALLS = """
CREATE TABLE IF NOT EXISTS calls (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT    NOT NULL,
    call_id      TEXT    UNIQUE,
    caller_name  TEXT,
    phone        TEXT,
    suburb       TEXT,
    service      TEXT,
    urgency      TEXT,
    summary      TEXT,
    transcript   TEXT,
    raw_json     TEXT
);
"""

_DDL_INDEX_CALL_ID = """
CREATE UNIQUE INDEX IF NOT EXISTS uix_calls_call_id ON calls (call_id);
"""

_DDL_INDEX_CREATED = """
CREATE INDEX IF NOT EXISTS ix_calls_created_at ON calls (created_at);
"""


# --------------------------------------------------------------------------- #
# Public helpers
# --------------------------------------------------------------------------- #

def init_db(db_path: str) -> None:
    """
    Initialise the SQLite database at *db_path*.

    Creates the calls table and indexes if they do not already exist.
    Enables WAL journal mode for better concurrency.

    Args:
        db_path: Filesystem path to the .db file.  Railway's ephemeral
                 filesystem is fine for demos; attach a persistent volume
                 for production use.

    Raises:
        sqlite3.Error: Re-raised if schema creation fails (startup is aborted).
    """
    try:
        with _get_conn(db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA foreign_keys=ON;")
            conn.execute(_DDL_CREATE_CALLS)
            conn.execute(_DDL_INDEX_CALL_ID)
            conn.execute(_DDL_INDEX_CREATED)
            conn.commit()
        logger.info("Database schema initialised successfully.")
    except sqlite3.Error as exc:
        logger.exception("Fatal: could not initialise database — %s", exc)
        raise


def save_call(db_path: str, record: Dict[str, Any]) -> bool:
    """
    Persist one call record to the *calls* table.

    Uses INSERT OR REPLACE so re-delivered Vapi webhooks are idempotent
    (same call_id simply overwrites the previous row).

    Args:
        db_path: Path to the SQLite file.
        record:  Dict produced by combining call_service + lead_service output.
                 Expected keys: call_id, caller_name, phone, suburb, service,
                 urgency, summary, transcript, raw_json.

    Returns:
        True if the row was saved successfully, False otherwise.
    """
    sql = """
        INSERT OR REPLACE INTO calls
            (created_at, call_id, caller_name, phone, suburb,
             service, urgency, summary, transcript, raw_json)
        VALUES
            (:created_at, :call_id, :caller_name, :phone, :suburb,
             :service, :urgency, :summary, :transcript, :raw_json);
    """
    raw = record.get("raw_json", {})
    params: Dict[str, Any] = {
        "created_at":   _utcnow(),
        "call_id":      record.get("call_id") or "",
        "caller_name":  record.get("caller_name"),
        "phone":        record.get("phone"),
        "suburb":       record.get("suburb"),
        "service":      record.get("service"),
        "urgency":      record.get("urgency"),
        "summary":      record.get("summary"),
        "transcript":   record.get("transcript"),
        "raw_json":     json.dumps(raw) if not isinstance(raw, str) else raw,
    }
    try:
        with _get_conn(db_path) as conn:
            conn.execute(sql, params)
            conn.commit()
        logger.info("Saved call to DB: call_id=%s", params["call_id"])
        return True
    except sqlite3.Error as exc:
        logger.exception(
            "DB error saving call_id=%s — %s", params["call_id"], exc
        )
        return False


def get_all_calls(db_path: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Return the most recent *limit* call records, newest first.

    Args:
        db_path: Path to the SQLite file.
        limit:   Maximum number of rows to return.

    Returns:
        List of dicts, one per row.  Empty list on error.
    """
    sql = "SELECT * FROM calls ORDER BY id DESC LIMIT ?;"
    try:
        with _get_conn(db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(sql, (limit,)).fetchall()
            return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        logger.exception("DB error fetching calls — %s", exc)
        return []


def get_call_by_id(db_path: str, call_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch a single call record by its Vapi call ID.

    Args:
        db_path: Path to the SQLite file.
        call_id: Vapi's unique call identifier string.

    Returns:
        Dict of column values, or None if not found / on error.
    """
    sql = "SELECT * FROM calls WHERE call_id = ? LIMIT 1;"
    try:
        with _get_conn(db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(sql, (call_id,)).fetchone()
            return dict(row) if row else None
    except sqlite3.Error as exc:
        logger.exception("DB error fetching call_id=%s — %s", call_id, exc)
        return None


# --------------------------------------------------------------------------- #
# Private helpers
# --------------------------------------------------------------------------- #

def _get_conn(db_path: str) -> sqlite3.Connection:
    """
    Open and return a SQLite connection with a 10-second busy timeout.

    Args:
        db_path: Filesystem path to the database file.

    Returns:
        An open sqlite3.Connection.
    """
    return sqlite3.connect(db_path, timeout=10, check_same_thread=False)


def _utcnow() -> str:
    """Return the current time as a UTC ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()
