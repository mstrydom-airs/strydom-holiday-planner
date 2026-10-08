"""Smoke tests — verify the app boots and the home page responds.

These are intentionally minimal so the test suite is green from day one.
Replace and grow them as features land. Each new test should reference a
``TEST-`` need (see ``docs/tests/index.rst``) and the ``REQ-`` it covers.
"""

from __future__ import annotations

import pytest

import app as app_module


@pytest.mark.smoke
def test_home_page_returns_200(flask_client) -> None:  # type: ignore[no-untyped-def]
    """The home page should load successfully.

    Needs: REQ-001, TEST-001
    """

    response = flask_client.get("/")
    assert response.status_code == 200


@pytest.mark.smoke
def test_home_page__glance_trips__shows_month_timeline_rail(
    flask_client, monkeypatch: pytest.MonkeyPatch
) -> None:  # type: ignore[no-untyped-def]
    """When saved trips exist, the home page shows compact date-first rows.

    Needs: REQ-005, TEST-017, UC-002
    """

    fake_rows = [
        {
            "kind": "day_trip",
            "plan": {"id": "t1", "title": "Beach"},
            "sort": "2026-05-01",
            "date_label": "01 May 26",
            "households": {"mario_esme"},
        }
    ]
    monkeypatch.setattr(app_module, "_upcoming_trip_rows", lambda **_: fake_rows)

    response = flask_client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "upcoming-summary" in html
    assert "home-trip-title" in html
    assert "Beach" in html
    assert "Mario" in html
    assert "Next up" not in html
