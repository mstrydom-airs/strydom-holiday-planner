"""Route coverage for trip creation, duplication, checklist, and search flows.

Needs: REQ-002, REQ-003, REQ-004, UC-001, TEST-012, TEST-013, TEST-014,
TEST-015
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

ROUTE_CASES = [
    (
        "day_trip",
        "/day-trip",
        {
            "title": "Gardens",
            "start_date": "2026-07-01",
            "transport": ["Car"],
            "travelers": ["family"],
            "holiday_types": ["Walk"],
            "accommodation": ["Tent"],
            "things_to_do": ["Swimming"],
            "things_to_do_new": "Picnic",
            "transport_extra": "water\nsnacks",
            "notes": "Rose garden walk",
            "planner_day_2026-07-01": "Arrive early",
        },
    ),
    (
        "weekend",
        "/weekend",
        {
            "title": "Coast",
            "start_date": "2026-07-03",
            "end_date": "2026-07-05",
            "transport": ["Ute"],
            "travelers": ["friends"],
            "travelers_other": "Ava",
            "holiday_types": ["Camping"],
            "accommodation": ["Caravan"],
            "accommodation_places": "Beach Hotel",
            "things_to_do": ["Beach"],
            "transport_extra": "- awning",
            "notes": "Ocean weekend",
            "planner_day_2026-07-04": "Surf lesson",
        },
    ),
    (
        "long_weekend",
        "/long-weekend",
        {
            "title": "Ranges",
            "start_date": "2026-08-01",
            "end_date": "2026-08-04",
            "transport": ["train"],
            "travelers": ["mario_esme"],
            "holiday_types": ["Hiking"],
            "accommodation": ["Accor"],
            "things_to_do": ["Hiking"],
            "notes": "Lookout trail",
        },
    ),
]


def _trip_id(location: str) -> str:
    return parse_qs(urlparse(location).query)["trip"][0]


@pytest.mark.parametrize(("kind", "route", "form_data"), ROUTE_CASES)
def test_trip_routes__new_post_duplicate_and_invalid_paths__preserve_expected_redirects(
    flask_client, kind: str, route: str, form_data: Mapping[str, Any]
) -> None:  # type: ignore[no-untyped-def]
    """Exercise the standard trip route branches for date-based holiday types.

    Pytest node:
    tests/test_app_routes.py::
    test_trip_routes__new_post_duplicate_and_invalid_paths__preserve_expected_redirects
    Needs: REQ-002, REQ-003, REQ-004, UC-001, TEST-012
    """

    # Arrange
    empty_page = flask_client.get(route)
    created = flask_client.get(f"{route}?new=1&title={form_data['title']}")
    trip_id = _trip_id(created.headers["Location"])
    post_data = {"trip_id": trip_id, **form_data}

    # Act
    saved = flask_client.post(route, data=post_data)
    opened = flask_client.get(f"{route}?trip={trip_id}")
    single_default = flask_client.get(route)
    missing_duplicate = flask_client.get(f"{route}?duplicate=1")
    bad_duplicate = flask_client.get(f"{route}?duplicate=1&from=missing")
    good_duplicate = flask_client.get(f"{route}?duplicate=1&from={trip_id}")
    copied_id = _trip_id(good_duplicate.headers["Location"])
    invalid_trip = flask_client.get(f"{route}?trip=missing")
    deleted = flask_client.post("/delete-trip", data={"trip_kind": kind, "trip_id": copied_id})

    # Assert
    assert empty_page.status_code == 200
    assert saved.status_code == 302
    assert opened.status_code == 200
    assert bytes(str(form_data["title"]), "utf-8") in opened.data
    assert single_default.status_code in {200, 302}
    assert missing_duplicate.headers["Location"].endswith("/holiday-planning")
    assert bad_duplicate.headers["Location"].endswith("/holiday-planning")
    assert copied_id != trip_id
    assert invalid_trip.headers["Location"].endswith("/holiday-planning")
    assert deleted.headers["Location"].endswith("/")


def test_extended_route__post_duplicate_and_render__handles_legs_and_overall_dates(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """Save and duplicate an extended trip with leg-level planning data.

    Pytest node:
    tests/test_app_routes.py::
    test_extended_route__post_duplicate_and_render__handles_legs_and_overall_dates
    Needs: REQ-003, REQ-004, UC-001, TEST-013
    """

    # Arrange
    empty_page = flask_client.get("/extended")
    created = flask_client.get("/extended?new=1&title=Island%20Loop")
    trip_id = _trip_id(created.headers["Location"])

    # Act
    saved = flask_client.post(
        "/extended",
        data={
            "trip_id": trip_id,
            "title": "Island Loop",
            "trip_start": "2026-09-01",
            "trip_end": "2026-09-06",
            "leg_destination": ["Hobart", "Freycinet"],
            "leg_start": ["2026-09-01", "2026-09-03"],
            "leg_end": ["2026-09-02", "2026-09-06"],
            "leg_transport": ["Flights", "Car"],
            "transport": ["Flights", "Car"],
            "travelers": ["family"],
            "holiday_types": ["Walk"],
            "accommodation": ["Accor"],
            "notes": "National park walks",
            "planner_day_2026-09-04": "Wineglass Bay",
        },
    )
    opened = flask_client.get(f"/extended?trip={trip_id}")
    duplicate = flask_client.get(f"/extended?duplicate=1&from={trip_id}")
    copied_id = _trip_id(duplicate.headers["Location"])
    invalid = flask_client.get("/extended?trip=missing")

    # Assert
    assert empty_page.status_code == 200
    assert saved.status_code == 302
    assert opened.status_code == 200
    assert b"Island Loop" in opened.data
    assert b"Hobart" in opened.data
    assert copied_id != trip_id
    assert invalid.headers["Location"].endswith("/holiday-planning")


def test_save_checklist__valid_and_invalid_pairs__updates_only_allowed_pairs(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """Store checklist content for valid transport/accommodation pairs only.

    Pytest node:
    tests/test_app_routes.py::
    test_save_checklist__valid_and_invalid_pairs__updates_only_allowed_pairs
    Needs: REQ-004, TEST-014
    """

    # Arrange / Act
    invalid = flask_client.post(
        "/save-checklist",
        data={
            "pair_transport": "Skateboard",
            "pair_accommodation": "Hotel",
            "checklist_content": "helmet",
            "return_to": "weekend",
        },
    )
    valid = flask_client.post(
        "/save-checklist",
        data={
            "pair_transport": "Car",
            "pair_accommodation": "Hotel",
            "checklist_content": "charger\n- booking printout",
            "return_to": "weekend",
        },
    )

    # Assert
    assert invalid.headers["Location"].endswith("/weekend")
    assert valid.headers["Location"].endswith("/weekend")
    with flask_client.session_transaction() as stored_session:
        pairs = stored_session["checklist_pairs"]
    assert pairs["Car|Hotel"] == "1. charger\n2. booking printout"
    assert "Skateboard|Hotel" not in pairs


def test_search_route__empty_query_and_checklist_match__show_expected_messages(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """Render empty search state and checklist-only search hints.

    Pytest node:
    tests/test_app_routes.py::
    test_search_route__empty_query_and_checklist_match__show_expected_messages
    Needs: REQ-004, UC-001, TEST-015
    """

    # Arrange
    empty = flask_client.get("/search")
    flask_client.post(
        "/save-checklist",
        data={
            "pair_transport": "Boat Trip",
            "pair_accommodation": "Hotel",
            "checklist_content": "reef shoes",
        },
    )

    # Act
    matched = flask_client.get("/search?q=reef")

    # Assert
    assert empty.status_code == 200
    assert b"Enter a word or phrase" in empty.data
    assert b"saved checklist" in matched.data
