"""Shared pytest fixtures for the Trip Planner test suite.

Fixtures defined here are available to every test file under ``tests/``.
See ``.cursor/rules/project-standards.mdc`` §7 for testing conventions.
"""

from __future__ import annotations

import os
import sys
import tempfile
from collections.abc import Iterator
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_database_path() -> Iterator[Path]:
    """Provide a temporary SQLite file path for a single test.

    The file is removed automatically when the test finishes, even if it
    fails. Use this for any test that needs to read or write to the DB
    without polluting the real ``travel_hub.db``.
    """

    fd, path = tempfile.mkstemp(suffix=".db", prefix="trip_planner_test_")
    os.close(fd)
    try:
        yield Path(path)
    finally:
        Path(path).unlink(missing_ok=True)


@pytest.fixture
def flask_client(tmp_database_path: Path, monkeypatch):  # type: ignore[no-untyped-def]
    """Return a Flask test client for the current ``app.py``.

    NOTE: ``app.py`` is currently a single module exposing ``app`` at module
    scope. Once we refactor to a ``create_app()`` factory, switch this fixture
    to use the factory plus a testing config.

    Needs: REQ-001, REQ-002, REQ-003, REQ-004
    """

    import app as app_module  # imported lazily so collection still works without Flask
    import database

    monkeypatch.setattr(database, "_db_path", lambda: tmp_database_path)
    flask_app = app_module.app
    flask_app.config.update(TESTING=True)
    with flask_app.test_client() as client:
        yield client
