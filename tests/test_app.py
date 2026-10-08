"""Tests for the holiday planning Flask helpers and routes.

Needs: REQ-003, REQ-004, UC-001, TEST-002, TEST-005, TEST-006, TEST-007,
TEST-008, TEST-009, TEST-011
"""

from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlparse

import pytest
from flask import session

import app as app_module


def _trip_id_from_redirect(location: str) -> str:
    query = parse_qs(urlparse(location).query)
    return query["trip"][0]


def test_holiday_planning__empty_database__renders_start_panel(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Render the holiday details hub with accessible trip controls.

    Pytest node: tests/test_app.py::test_holiday_planning__empty_database__renders_start_panel
    Needs: REQ-003, UC-001, TEST-002
    """

    # Arrange / Act
    response = flask_client.get("/holiday-planning")

    # Assert
    assert response.status_code == 200
    assert b"Holiday Details" in response.data
    assert b"Import Emails and Bookings" in response.data
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


def test_upcoming_trip_rows__past_shared_and_far__includes_every_saved_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The home list keeps finished trips, shared trips, and trips past 12 months.

    Pytest node:
    tests/test_app.py::test_upcoming_trip_rows__past_shared_and_far__includes_every_saved_trip
    Needs: REQ-005, UC-002, TEST-017
    """
    plans_by_kind = {
        "day_trip": [],
        "weekend": [],
        "long_weekend": [],
        "extended": [
            {
                "id": "past",
                "title": "Legends",
                "trip_start": "2026-09-04",
                "trip_end": "2026-09-07",
                "travelers": ["mario_esme"],
            },
            {
                "id": "shared",
                "title": "Easter",
                "trip_start": "2027-03-25",
                "trip_end": "2027-03-31",
                "travelers": [],
                "planner_profile": "all_of_us",
            },
            {
                "id": "far",
                "title": "Kings",
                "trip_start": "2028-09-24",
                "trip_end": "2028-10-05",
                "travelers": [],
            },
        ],
    }
    monkeypatch.setattr(app_module, "_get_plans", lambda kind: plans_by_kind[kind])

    rows = app_module._upcoming_trip_rows(today=date(2026, 10, 8))

    assert [row["plan"]["id"] for row in rows] == ["shared", "far", "past"]


def test_all_glance_groups_sorted__home_window__hides_old_trips(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Show only trips in the next 12 months on the home page.

    Pytest node:
    tests/test_app.py::test_all_glance_groups_sorted__home_window__hides_old_trips
    Needs: REQ-005, UC-002, TEST-017
    """

    # Arrange
    plans_by_kind = {
        "day_trip": [
            {"id": "old", "title": "Old movie", "start_date": "2026-01-01"},
            {"id": "future", "title": "Beach", "start_date": "2026-10-01"},
            {"id": "too-far", "title": "Far away", "start_date": "2027-10-05"},
        ],
        "weekend": [],
        "long_weekend": [],
        "extended": [],
    }
    monkeypatch.setattr(app_module, "_get_plans", lambda kind: plans_by_kind[kind])

    # Act
    groups = app_module._all_glance_groups_sorted(today=date(2026, 9, 29))

    # Assert
    assert [trip["title"] for group in groups for trip in group["group"]["trips"]] == ["Beach"]


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


def test_stay_timeline__checkout_time__shows_on_checkout_day() -> None:
    """Show check-in and check-out times on their own days.

    Pytest node: tests/test_app.py::test_stay_timeline__checkout_time__shows_on_checkout_day
    Needs: REQ-006, TEST-018
    """

    # Arrange
    rows: list[dict[str, str]] = []
    booking = {
        "category": "Accommodation",
        "name": "Beach House Seaside Resort",
        "date": "2026-12-11",
        "end_date": "2026-12-18",
        "time": "15:00",
        "checkout_time": "11:00",
        "address": "52 Marine Parade, Coolangatta QLD 4225, Australia",
        "notes": "Check-in 3:00 PM AEST. Check-out 11:00 AM AEST.",
    }

    # Act
    app_module._add_stay_checkin_checkout_rows(rows, booking, None, booking["name"])

    # Assert
    assert rows[0]["date"] == "2026-12-11"
    assert rows[0]["time"] == "15:00"
    assert rows[0]["title"] == "Check-in: Beach House Seaside Resort"
    assert rows[1]["date"] == "2026-12-18"
    assert rows[1]["time"] == "11:00"
    assert rows[1]["title"] == "Check-out: Beach House Seaside Resort"


def test_compact_timeline_days__event_and_activities__groups_under_event_heading() -> None:
    """Use the named event as the heading for its day's expandable activities."""
    plan = {
        "booking_items": [
            {
                "category": "Tour / activity",
                "name": "Agile Partner Event",
                "date": "2026-10-15",
                "time": "14:00",
                "notes": "Business casual.",
            }
        ],
        "planner_days": {
            "2026-10-15": "14:00 Registration\n15:00 Product roadmap",
        },
    }

    days = app_module._compact_timeline_days(plan, "extended")

    assert len(days) == 1
    assert days[0]["title"] == "Agile Partner Event"
    assert [row["title"] for row in days[0]["rows"]] == [
        "14:00 Registration",
        "Agile Partner Event",
        "15:00 Product roadmap",
    ]
    assert days[0]["rows"][1]["comments"] == "Business casual."


def test_compact_timeline_days__same_activity_on_separate_dates__keeps_each_day() -> None:
    """Repeated event names remain visible when they occur on different dates."""
    plan = {
        "planner_days": {
            "2026-10-11": "Robot show / NECC activities.",
            "2026-10-12": "Robot show / NECC activities.",
            "2026-10-13": "Robot show / NECC activities.",
        }
    }

    days = app_module._compact_timeline_days(plan, "extended")

    assert [day["date"] for day in days] == ["2026-10-11", "2026-10-12", "2026-10-13"]


def test_compact_timeline_days__stay_and_activity__uses_activity_as_day_heading() -> None:
    """A check-in day summary describes the day's activity, not only the hotel."""
    plan = {
        "legs": [
            {
                "destination": "InterContinental Shanghai NECC",
                "start_date": "2026-10-10",
                "end_date": "2026-10-16",
            }
        ],
        "planner_days": {
            "2026-10-10": "Arrive Shanghai; check in and explore the area.",
        },
    }

    days = app_module._compact_timeline_days(plan, "extended")

    assert days[0]["title"] == "Arrive Shanghai; check in and explore the area."
    assert len(days[0]["rows"]) == 2


def test_workspace_booking_rows__extended_stay_legs__adds_missing_hotels() -> None:
    """Accommodation legs appear on Bookings even without imported confirmations."""
    plan = {
        "booking_items": [],
        "legs": [
            {
                "destination": "InterContinental Shanghai NECC",
                "start_date": "2026-10-10",
                "end_date": "2026-10-16",
            }
        ],
    }

    rows = app_module._workspace_booking_rows(plan, "extended")

    assert rows == [
        {
            "category": "Accommodation",
            "name": "InterContinental Shanghai NECC",
            "date": "2026-10-10",
            "end_date": "2026-10-16",
        }
    ]


def test_booking_comments__flight_arrival__includes_arrival_and_notes() -> None:
    """Flight details show the scheduled arrival without repeating departure."""
    booking = {
        "category": "Flight",
        "time": "19:05",
        "checkout_time": "21:50",
        "notes": "PVG Terminal 2 to HKG Terminal 1.",
    }

    comments = app_module._booking_comments(booking)

    assert comments == "Scheduled arrival: 21:50 · PVG Terminal 2 to HKG Terminal 1."
