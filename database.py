"""SQLite persistence for Strydom Travel Hub trips."""

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import current_app, g


def _db_path() -> Path:
    return Path(current_app.root_path) / "travel_hub.db"


def get_db() -> sqlite3.Connection:
    if "db" not in g:
        conn = sqlite3.connect(_db_path(), detect_types=sqlite3.PARSE_DECLTYPES)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        g.db = conn
    return g.db


def close_db(_e: Any = None) -> None:
    conn: sqlite3.Connection | None = g.pop("db", None)
    if conn is not None:
        conn.close()


def register_db(app) -> None:
    app.teardown_appcontext(close_db)


def ensure_trips_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL CHECK (kind IN ('day_trip', 'weekend', 'long_weekend', 'extended')),
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )
    row = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'trips'"
    ).fetchone()
    if row and "day_trip" not in (row["sql"] or ""):
        conn.execute("ALTER TABLE trips RENAME TO trips_old")
        conn.execute(
            """
            CREATE TABLE trips (
                id TEXT PRIMARY KEY,
                kind TEXT NOT NULL CHECK (kind IN ('day_trip', 'weekend', 'long_weekend', 'extended')),
                data TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            INSERT INTO trips (id, kind, data, updated_at)
            SELECT id, kind, data, updated_at FROM trips_old
            """
        )
        conn.execute("DROP TABLE trips_old")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_trips_kind ON trips(kind)")
    conn.commit()


def trip_row_to_plan(row: sqlite3.Row) -> Optional[Dict[str, Any]]:
    try:
        return json.loads(row["data"])
    except (json.JSONDecodeError, TypeError):
        return None


def count_trips(conn: sqlite3.Connection) -> int:
    cur = conn.execute("SELECT COUNT(*) AS c FROM trips")
    return int(cur.fetchone()["c"])


def fetch_plans_for_kind(conn: sqlite3.Connection, kind: str) -> List[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT data FROM trips WHERE kind = ? ORDER BY updated_at ASC, id ASC",
        (kind,),
    )
    out: List[Dict[str, Any]] = []
    for row in cur:
        p = trip_row_to_plan(row)
        if p is not None:
            out.append(p)
    return out


def fetch_plan(conn: sqlite3.Connection, kind: str, trip_id: str) -> Optional[Dict[str, Any]]:
    cur = conn.execute(
        "SELECT data FROM trips WHERE id = ? AND kind = ?",
        (trip_id, kind),
    )
    row = cur.fetchone()
    if not row:
        return None
    return trip_row_to_plan(row)


def upsert_trip(conn: sqlite3.Connection, kind: str, plan: Dict[str, Any]) -> None:
    tid = plan.get("id")
    if not tid:
        return
    payload = json.dumps(plan, ensure_ascii=False)
    conn.execute(
        """
        INSERT OR REPLACE INTO trips (id, kind, data, updated_at)
        VALUES (?, ?, ?, datetime('now'))
        """,
        (tid, kind, payload),
    )


def delete_trip(conn: sqlite3.Connection, trip_id: str) -> None:
    conn.execute("DELETE FROM trips WHERE id = ?", (trip_id,))


def delete_all_trips(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM trips")
