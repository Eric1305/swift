"""Call records in SQLite: one local file on the agency's machine (default data/swift.db, override SWIFT_DB).

households - latest known state per home (what dispatch and rescue crews read)
calls      - one row per phone call: status, how it ended, full transcript and the record as captured
"""
import json
import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from agent.script import Record

DB_PATH = Path(os.environ.get("SWIFT_DB", Path(__file__).resolve().parents[1] / "data" / "swift.db"))
_lock = threading.Lock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS households (
    household_id     TEXT PRIMARY KEY,
    address          TEXT,
    status           TEXT NOT NULL,
    people           INTEGER,
    cant_leave_alone TEXT NOT NULL,          -- JSON list of {who, need}
    water_inside     INTEGER,                -- 1 / 0 / NULL (not answered)
    truck            INTEGER NOT NULL,
    boat             INTEGER NOT NULL,
    seats            INTEGER NOT NULL,
    language         TEXT,
    house_card       TEXT,
    attempts         INTEGER NOT NULL,
    last_call_id     TEXT,
    updated_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS calls (
    call_id              TEXT PRIMARY KEY,
    household_id         TEXT NOT NULL,
    call_status          TEXT NOT NULL,      -- ringing / in-progress / completed / no-answer
    disconnection_reason TEXT,
    started_at           TEXT NOT NULL,
    updated_at           TEXT NOT NULL,
    transcript           TEXT NOT NULL,      -- JSON list of {who, text}
    record               TEXT NOT NULL       -- JSON record as captured on this call
);
CREATE INDEX IF NOT EXISTS calls_by_household ON calls (household_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def connect(path: Path | None = None) -> sqlite3.Connection:
    path = Path(path or DB_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


_conn: sqlite3.Connection | None = None


def _db() -> sqlite3.Connection:
    global _conn
    if _conn is None:
        _conn = connect()
    return _conn


def save_call(call_id: str, record: Record, call_status: str, disconnection_reason: str | None = None,
              conn: sqlite3.Connection | None = None) -> None:
    """Upsert this call and the household's latest state. Called after every turn and when the call ends."""
    db = conn or _db()
    now = _now()
    rec = record.model_dump()
    with _lock, db:
        db.execute(
            """INSERT INTO calls (call_id, household_id, call_status, disconnection_reason, started_at, updated_at, transcript, record)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(call_id) DO UPDATE SET call_status=excluded.call_status,
                 disconnection_reason=COALESCE(excluded.disconnection_reason, calls.disconnection_reason),
                 updated_at=excluded.updated_at, transcript=excluded.transcript, record=excluded.record""",
            (call_id, record.id, call_status, disconnection_reason, now, now,
             json.dumps(rec["transcript"]), json.dumps({k: v for k, v in rec.items() if k != "transcript"})),
        )
        db.execute(
            """INSERT INTO households (household_id, address, status, people, cant_leave_alone, water_inside, truck, boat,
                 seats, language, house_card, attempts, last_call_id, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(household_id) DO UPDATE SET address=excluded.address, status=excluded.status,
                 people=excluded.people, cant_leave_alone=excluded.cant_leave_alone, water_inside=excluded.water_inside,
                 truck=excluded.truck, boat=excluded.boat, seats=excluded.seats, language=excluded.language,
                 house_card=COALESCE(excluded.house_card, households.house_card), attempts=excluded.attempts,
                 last_call_id=excluded.last_call_id, updated_at=excluded.updated_at""",
            (record.id, record.address, record.status, record.people, json.dumps(record.cant_leave_alone),
             None if record.water_inside is None else int(record.water_inside), int(record.can_help.truck),
             int(record.can_help.boat), record.can_help.seats, record.language, record.house_card, record.attempts,
             call_id, now),
        )


def households(conn: sqlite3.Connection | None = None) -> list[dict]:
    rows = (conn or _db()).execute("SELECT * FROM households ORDER BY updated_at DESC").fetchall()
    return [{**dict(r), "cant_leave_alone": json.loads(r["cant_leave_alone"])} for r in rows]


def calls_for(household_id: str, conn: sqlite3.Connection | None = None) -> list[dict]:
    rows = (conn or _db()).execute("SELECT * FROM calls WHERE household_id = ? ORDER BY started_at", (household_id,)).fetchall()
    return [{**dict(r), "transcript": json.loads(r["transcript"]), "record": json.loads(r["record"])} for r in rows]
