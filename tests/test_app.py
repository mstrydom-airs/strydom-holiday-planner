"""Tests for the holiday planning Flask helpers and routes.

Needs: REQ-003, REQ-004, UC-001, TEST-002, TEST-005, TEST-006, TEST-007,
TEST-008, TEST-009, TEST-011
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlparse

import pytest
from flask import session

import app as app_module


def _trip_id_from_redirect(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["trip"][0]


def test_holiday_planning__empty_database__renders_start_panel(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Render the holiday hub with its accessible start controls.

    Pytest node: tests/test_app.py::test_holiday_planning__empty_database__renders_start_panel
    Needs: REQ-003, UC-001, TEST-002
    """

    # Arrange / Act
    response = flask_client.get("/holiday-planning")

    # Assert
    assert response.status_code == 200
    assert b"Start Holiday Plan" in response.data
    assert b"Choose a destination" in response.data
    assert b"Trip length" in response.data


def test_new_empty_plan__extended_trip__starts_with_blank_leg(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Create a blank extended trip shell ready for the destination page.

    Pytest node: tests/test_app.py::test_new_empty_plan__extended_trip__starts_with_blank_leg
    Needs: REQ-003, TEST-007
    """

    # Arrange
    monkeypatch.setattr(app_module, "_new_trip_id", lambda: "new-extended")

    # Act
    plan = app_module._new_empty_plan("extended", "Tasmania Loop")

    # Assert
    assert plan == {
        "id": "new-extended",
        "title": "Tasmania Loop",
        "legs": [{}],
        "trip_start": "",
        "trip_end": "",
    }


def test_duplicate_plan_without_dates__extended_trip__clears_dates_and_keeps_details(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Duplicate an extended plan without carrying old calendar dates forward.

    Pytest node:
    tests/test_app.py::
    test_duplicate_plan_without_dates__extended_trip__clears_dates_and_keeps_details
    Needs: REQ-003, UC-001, TEST-005
    """

    # Arrange
    monkeypatch.setattr(app_module, "_new_trip_id", lambda: "copy-1")
    source = {
        "id": "original",
        "title": "Great Ocean Road",
        "trip_start": "2026-04-01",
        "trip_end": "2026-04-07",
        "legs": [
            {
                "destination": "Lorne",
                "start_date": "2026-04-01",
                "end_date": "2026-04-03",
                "transport": "Car",
            }
        ],
        "planner_days": {"2026-04-02": "Waterfall walk"},
        "travelers": ["family"],
    }

    # Act
    duplicate = app_module._duplicate_plan_without_dates("extended", source)

    # Assert
    assert duplicate["id"] == "copy-1"
    assert duplicate["title"] == "Great Ocean Road"
    assert duplicate["trip_start"] == ""
    assert duplicate["trip_end"] == ""
    assert duplicate["legs"] == [
        {"destination": "Lorne", "start_date": "", "end_date": "", "transport": "Car"}
    ]
    assert duplicate["planner_days"] == {}
    assert source["trip_start"] == "2026-04-01"


def test_plans_payload_for_holiday_json__duplicate_labels__adds_trip_type_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disambiguate saved trips that would otherwise have the same label.

    Pytest node:
    tests/test_app.py::
    test_plans_payload_for_holiday_json__duplicate_labels__adds_trip_type_suffix
    Needs: REQ-003, TEST-006
    """

    # Arrange
    plans_by_kind = {
        "day_trip": [],
        "weekend": [
            {
                "id": "weekend-1",
                "title": "Noosa",
                "start_date": "2026-05-01",
                "end_date": "2026-05-03",
            }
        ],
        "long_weekend": [
            {
                "id": "long-1",
                "title": "Noosa",
                "start_date": "2026-05-01",
                "end_date": "2026-05-03",
            }
        ],
        "extended": [{"id": "ext-1", "title": "Tasmania", "trip_start": "", "trip_end": ""}],
    }
    monkeypatch.setattr(app_module, "_get_plans", lambda kind: plans_by_kind[kind])

    # Act
    payload = app_module._plans_payload_for_holiday_json()

    # Assert
    labels = [row["label"] for row in payload["all_trips"]]
    assert labels == [
        "Noosa — 01 May 26 → 03 May 26 · Long weekend",
        "Noosa — 01 May 26 → 03 May 26 · Weekend",
        "Tasmania — dates open",
    ]
    assert payload["destination_names"] == ["Noosa", "Tasmania"]


def test_calendar_dates_for_plan__extended_legs_without_overall_dates__uses_leg_span() -> None:
    """Build an inclusive planning calendar from extended-trip leg dates.

    Pytest node:
    tests/test_app.py::
    test_calendar_dates_for_plan__extended_legs_without_overall_dates__uses_leg_span
    Needs: REQ-004, TEST-008
    """

    # Arrange
    plan = {
        "trip_start": "",
        "trip_end": "",
        "legs": [
            {"start_date": "2026-06-05", "end_date": "2026-06-06"},
            {"start_date": "2026-06-03", "end_date": "2026-06-04"},
        ],
    }

    # Act
    dates = app_module._calendar_dates_for_plan("extended", plan)

    # Assert
    assert dates == ["2026-06-03", "2026-06-04", "2026-06-05", "2026-06-06"]


def test_checklist_sync__selected_transport_and_hotel__stores_numbered_items_with_auto_header() -> (
    None
):
    """Sync reusable checklist text for a selected transport/accommodation pair.

    Pytest node:
    tests/test_app.py::
    test_checklist_sync__selected_transport_and_hotel__stores_numbered_items_with_auto_header
    Needs: REQ-004, TEST-009
    """

    # Arrange
    plan = {
        "transport": ["Ute"],
        "accommodation": [],
        "accommodation_places": "Beach Hotel",
        "holiday_types": ["Camping"],
    }
    key = app_module._pair_key("Ute", "Hotel")

    # Act
    with app_module.app.test_request_context("/"):
        session["checklist_pairs"] = {key: "torch\n- sunscreen"}
        app_module._sync_checklist_auto_headers(plan, "weekend")
        saved = session["checklist_pairs"][key]

    # Assert
    assert saved == (
        "--- Trip selections (auto) ---\n"
        "Transport: Ute\n"
        "Accommodation: Hotel\n"
        "Activity Type: Camping\n"
        "1. torch\n"
        "2. sunscreen"
    )


def test_search_route__saved_trip_matches_query__shows_result(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Find a saved trip by text stored in its notes.

    Pytest node: tests/test_app.py::test_search_route__saved_trip_matches_query__shows_result
    Needs: REQ-004, UC-001, TEST-011
    """

    # Arrange
    created = flask_client.get("/weekend?new=1&title=Noosa")
    trip_id = _trip_id_from_redirect(created.headers["Location"])
    flask_client.post(
        "/weekend",
        data={
            "trip_id": trip_id,
            "title": "Noosa",
            "start_date": "2026-05-01",
            "end_date": "2026-05-03",
            "travelers": ["family"],
            "notes": "Lagoon kayaking after lunch",
        },
    )

    # Act
    response = flask_client.get("/search?q=lagoon")

    # Assert
    assert response.status_code == 200
    assert b"Noosa" in response.data
    assert b"Weekend" in response.data
