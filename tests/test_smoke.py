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
    """When saved trips exist, At a glance shows the month rail and headings.

    Needs: REQ-005, TEST-017, UC-002
    """

    fake_glance = [
        {
            "kind": "day_trip",
            "group": {
                "label": "1/5/2026",
                "trips": [{"id": "t1", "title": "Beach", "start_date": "2026-05-01"}],
                "multiple": False,
            },
            "sort_key": "2026-05-01",
        }
    ]
    monkeypatch.setattr(app_module, "_all_glance_groups_sorted", lambda: fake_glance)

    response = flask_client.get("/")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert 'data-glance-timeline' in html
    assert "glance-rail" in html
    assert "glance-month-heading" in html
    assert 'id="glance-section-2026-05"' in html
