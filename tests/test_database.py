"""Unit tests for SQLite persistence helpers.

Needs: REQ-002, REQ-004, TEST-003, TEST-004, TEST-010
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import database


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    return conn


def test_ensure_trips_schema__fresh_database__creates_trips_table(tmp_database_path: Path) -> None:
    """Create the trips schema on a new SQLite database.

    Pytest node:
    tests/test_database.py::
    test_ensure_trips_schema__fresh_database__creates_trips_table
    Needs: REQ-002, TEST-003
    """

    # Arrange
    conn = _connect(tmp_database_path)

    # Act
    database.ensure_trips_schema(conn)

    # Assert
    table = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'trips'"
    ).fetchone()
    index_row = conn.execute(
        "SELECT name FROM sqlite_master WHERE type = 'index' AND name = 'idx_trips_kind'"
    ).fetchone()
    conn.close()

    assert table["name"] == "trips"
    assert index_row["name"] == "idx_trips_kind"


def test_upsert_and_fetch_plan__valid_plan__round_trips_json(tmp_database_path: Path) -> None:
    """Persist and reload a weekend plan without losing nested data.

    Pytest node: tests/test_database.py::test_upsert_and_fetch_plan__valid_plan__round_trips_json
    Needs: REQ-002, TEST-004
    """

    # Arrange
    conn = _connect(tmp_database_path)
    database.ensure_trips_schema(conn)
    plan = {
        "id": "weekend-1",
        "title": "Coast break",
        "travelers": ["family"],
        "planner_days": {"2026-05-02": "Beach picnic"},
    }

    # Act
    database.upsert_trip(conn, "weekend", plan)
    conn.commit()
    fetched = database.fetch_plan(conn, "weekend", "weekend-1")
    count = database.count_trips(conn)
    conn.close()

    # Assert
    assert fetched == plan
    assert count == 1


def test_fetch_plans_for_kind__corrupt_json__skips_bad_rows(tmp_database_path: Path) -> None:
    """Ignore unreadable trip payloads while returning valid plans.

    Pytest node: tests/test_database.py::test_fetch_plans_for_kind__corrupt_json__skips_bad_rows
    Needs: REQ-004, TEST-010
    """

    # Arrange
    conn = _connect(tmp_database_path)
    database.ensure_trips_schema(conn)
    valid_plan = {"id": "day-1", "title": "Botanic Gardens"}
    database.upsert_trip(conn, "day_trip", valid_plan)
    conn.execute(
        "INSERT INTO trips (id, kind, data, updated_at) VALUES (?, ?, ?, datetime('now'))",
        ("broken", "day_trip", "{not-json"),
    )
    conn.commit()

    # Act
    plans = database.fetch_plans_for_kind(conn, "day_trip")
    corrupt = conn.execute("SELECT data FROM trips WHERE id = ?", ("broken",)).fetchone()
    decoded = database.trip_row_to_plan(corrupt)
    conn.close()

    # Assert
    assert plans == [valid_plan]
    assert decoded is None


def test_delete_trip__existing_plan__removes_only_matching_id(tmp_database_path: Path) -> None:
    """Delete one saved plan while leaving other trip kinds intact.

    Pytest node: tests/test_database.py::test_delete_trip__existing_plan__removes_only_matching_id
    Needs: REQ-002, TEST-004
    """

    # Arrange
    conn = _connect(tmp_database_path)
    database.ensure_trips_schema(conn)
    database.upsert_trip(conn, "weekend", {"id": "shared", "title": "Weekend"})
    database.upsert_trip(conn, "extended", {"id": "extended-1", "title": "Road loop"})
    conn.commit()

    # Act
    database.delete_trip(conn, "shared")
    conn.commit()
    remaining = database.fetch_plans_for_kind(conn, "extended")
    missing = database.fetch_plan(conn, "weekend", "shared")
    conn.close()

    # Assert
    assert remaining == [{"id": "extended-1", "title": "Road loop"}]
    assert missing is None
