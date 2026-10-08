"""Tests for the smart trip workspace helpers and routes.

Needs: REQ-006, SPEC-006, TEST-018, TEST-019
"""

from __future__ import annotations

from trip_planner.services.smart_trip import (
    add_typical_trip_tasks,
    append_suggestions_to_packing,
    assistant_suggestions,
    budget_items_for_plan,
    budget_totals_by_currency,
    normalise_workspace_plan,
    packing_text,
    parse_booking_rows,
    parse_budget_rows,
    parse_document_rows,
    parse_packing_text,
    parse_task_rows,
    previous_packing_items,
)


def _trip_id(location: str) -> str:
    return location.rstrip("/").split("/")[-1]


class FakeForm:
    """Small form double with the ``getlist`` method used by parser helpers."""

    def __init__(self, rows: dict[str, list[str]]) -> None:
        self.rows = rows

    def getlist(self, key: str) -> list[str]:
        return self.rows.get(key, [])


def test_assistant_suggestions__caravan_trip__includes_contextual_packing() -> None:
    """Suggest packing from trip category, transport, accommodation, and prior trips.

    Pytest node:
    tests/test_smart_trip.py::
    test_assistant_suggestions__caravan_trip__includes_contextual_packing
    Needs: REQ-006, TEST-018
    """

    # Arrange
    plan = normalise_workspace_plan(
        {
            "plan_category": "Caravan trip",
            "planner_profile": "mario",
            "transport": ["Car"],
            "accommodation": ["Caravan"],
        },
        "weekend",
    )

    # Act
    suggestions = assistant_suggestions(plan, "weekend", ["Board games"])

    # Assert
    assert "Power lead" in suggestions.packing_items
    assert "Phone mount" in suggestions.packing_items
    assert "Fuel card" in suggestions.packing_items
    assert "Board games" in suggestions.packing_items


def test_booking_and_packing_helpers__mixed_rows__keep_only_useful_values() -> None:
    """Parse dynamic booking rows and packing text into clean workspace payloads.

    Pytest node:
    tests/test_smart_trip.py::
    test_booking_and_packing_helpers__mixed_rows__keep_only_useful_values
    Needs: REQ-006, TEST-018
    """

    # Arrange
    form = FakeForm(
        {
            "booking_category": ["Hotel", ""],
            "booking_name": ["Harbour Hotel", ""],
            "booking_date": ["2026-05-01"],
            "booking_end_date": ["2026-05-03"],
            "booking_time": ["15:00"],
            "booking_checkout_time": ["11:00"],
            "booking_website": ["https://example.test"],
            "booking_reference": ["REF-1"],
            "booking_address": ["Main Street"],
            "booking_notes": ["Late check-in"],
        }
    )

    # Act
    bookings = parse_booking_rows(form)
    packing = parse_packing_text("1. Charger\n- Tickets\n\n", ["Tickets"])
    tasks = parse_task_rows(
        FakeForm({"task_owner": ["Mario"], "task_text": ["Check tyres"], "task_due": [""]})
    )
    budget = parse_budget_rows(
        FakeForm(
            {
                "budget_category": ["Fuel"],
                "budget_description": ["Trip fuel"],
                "budget_amount": ["80"],
            }
        )
    )
    documents = parse_document_rows(
        FakeForm(
            {
                "document_label": ["Tickets"],
                "document_location": ["Phone"],
                "document_notes": ["QR"],
            }
        )
    )

    # Assert
    assert bookings == [
        {
            "category": "Hotel",
            "name": "Harbour Hotel",
            "date": "2026-05-01",
            "end_date": "2026-05-03",
            "time": "15:00",
            "checkout_time": "11:00",
            "website": "https://example.test",
            "reference": "REF-1",
            "address": "Main Street",
            "notes": "Late check-in",
            "cost": "",
            "cost_currency": "",
            "cost_status": "",
            "cost_note": "",
        }
    ]
    assert packing == [
        {"text": "Charger", "packed": False, "source": "workspace"},
        {"text": "Tickets", "packed": True, "source": "workspace"},
    ]
    assert tasks == [{"owner": "Mario", "text": "Check tyres", "due": "", "status": ""}]
    assert budget == [{"category": "Fuel", "description": "Trip fuel", "amount": "80", "paid": ""}]
    assert documents == [{"label": "Tickets", "location": "Phone", "notes": "QR"}]


def test_budget_helpers__mixed_currencies__preserve_research_and_total_separately() -> None:
    """Keep researched estimates and avoid combining currencies.

    Needs: REQ-006, TEST-019
    """

    plan = {
        "booking_items": [
            {
                "category": "Hotel",
                "name": "Confirmed hotel",
                "cost": "100",
                "cost_currency": "AUD",
                "cost_status": "confirmed",
            }
        ],
        "budget_items": [
            {
                "description": "Tower tickets",
                "amount": "360",
                "currency": "CNY",
                "status": "estimated",
                "source": "online",
            }
        ],
    }

    items = budget_items_for_plan(plan)

    assert budget_totals_by_currency(items) == {"AUD": 100.0, "CNY": 360.0}
    assert items[1]["description"] == "Tower tickets"


def test_typical_tasks__overseas_flight_and_hotel__adds_relevant_items_once() -> None:
    """Seed every trip with relevant, idempotent tasks.

    Needs: REQ-006, TEST-019
    """

    plan = {
        "plan_category": "Holiday overseas",
        "task_items": [],
        "booking_items": [
            {"category": "Flight", "name": "CX156"},
            {"category": "Accommodation", "name": "City Hotel"},
        ],
    }

    first_count = add_typical_trip_tasks(plan, "extended")
    second_count = add_typical_trip_tasks(plan, "extended")
    task_text = {item["text"] for item in plan["task_items"]}

    assert first_count > 4
    assert second_count == 0
    assert "Check passport validity and entry requirements" in task_text
    assert "Reconfirm check-in, check-out and room or site inclusions" in task_text


def test_packing_reuse_helpers__previous_and_suggestions__dedupe_items() -> None:
    """Reuse previous packing and append selected assistant suggestions once.

    Pytest node:
    tests/test_smart_trip.py::
    test_packing_reuse_helpers__previous_and_suggestions__dedupe_items
    Needs: REQ-006, TEST-018
    """

    # Arrange
    plan = {"id": "current", "packing_items": [{"text": "Charger", "packed": True}]}
    plans = {
        "weekend": [
            plan,
            {"id": "old", "packing_items": [{"text": "Torch"}, "Charger"]},
        ],
        "extended": [{"id": "older", "packing_items": ["Passport"]}],
    }

    # Act
    previous = previous_packing_items(plans, "current")
    append_suggestions_to_packing(plan, ["Torch", "Torch", "Passport"])

    # Assert
    assert previous == ["Torch", "Charger", "Passport"]
    assert packing_text(plan) == "Charger\nTorch\nPassport"


def test_smart_trip_new__type_and_length__combine_without_confusion(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Create smart trips from separate trip type and trip length selections.

    Pytest node:
    tests/test_smart_trip.py::test_smart_trip_new__type_and_length__combine_without_confusion
    Needs: REQ-006, UC-003, TEST-019
    """

    # Arrange / Act
    movie = flask_client.post(
        "/smart-trip/new",
        data={
            "title": "Movie night",
            "plan_category": "Movie",
            "trip_kind": "day_trip",
            "start_date": "2026-05-01",
            "end_date": "2026-05-01",
        },
    )
    caravan = flask_client.post(
        "/smart-trip/new",
        data={
            "title": "Caravan long weekend",
            "plan_category": "Caravan trip",
            "trip_kind": "long_weekend",
        },
    )

    # Assert
    assert "/trip/day_trip/" in movie.headers["Location"]
    assert "/trip/long_weekend/" in caravan.headers["Location"]
    assert b"2026-05-01" in flask_client.get(movie.headers["Location"]).data


def test_trip_workspace__create_update_booking_and_packing__renders_saved_workspace(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """Create a smart trip, save booking/packing details, and reopen the workspace.

    Pytest node:
    tests/test_smart_trip.py::
    test_trip_workspace__create_update_booking_and_packing__renders_saved_workspace
    Needs: REQ-006, UC-003, TEST-019
    """

    # Arrange
    created = flask_client.post(
        "/smart-trip/new",
        data={
            "title": "Easter caravan",
            "plan_category": "Caravan trip",
            "trip_kind": "weekend",
            "planner_profile": "all_of_us",
            "travelers": ["mario", "esme", "reuben", "vanessa", "noah"],
        },
    )
    trip_id = _trip_id(created.headers["Location"])

    # Act
    saved = flask_client.post(
        f"/trip/weekend/{trip_id}",
        data={
            "title": "Easter caravan",
            "plan_category": "Caravan trip",
            "travelers": ["mario", "esme", "reuben", "vanessa", "noah"],
            "start_date": "2026-04-03",
            "end_date": "2026-04-06",
            "transport": ["Car"],
            "accommodation": ["Caravan"],
            "booking_category": ["Caravan stand"],
            "booking_name": ["Beach Holiday Park"],
            "booking_date": ["2026-04-03"],
            "booking_time": ["14:00"],
            "booking_reference": ["ABC123"],
            "booking_website": ["https://example.test/park"],
            "booking_address": ["Site 42"],
            "booking_notes": ["Powered site"],
            "booking_cost": ["320.50"],
            "booking_import_text": "Confirmation ABC123 for powered site",
            "task_owner": ["Mario"],
            "task_text": ["Check tyre pressure"],
            "task_due": ["2026-04-02"],
            "task_status": ["To do"],
            "budget_category": ["Accommodation"],
            "budget_description": ["Powered site"],
            "budget_amount": ["320.50"],
            "budget_paid": ["Deposit"],
            "document_label": ["Park confirmation"],
            "document_location": ["Email"],
            "document_notes": ["Search ABC123"],
            "packing_text": "Power lead\nBoard games",
            "packing_done": ["Power lead"],
            "notes": "Leave after breakfast",
        },
    )
    opened = flask_client.get(f"/trip/weekend/{trip_id}")
    pack = flask_client.get(f"/trip/weekend/{trip_id}/pack")

    # Assert
    assert saved.status_code == 302
    assert opened.status_code == 200
    assert b"Beach Holiday Park" in opened.data
    assert b"ABC123" in opened.data
    assert b"Power lead" in opened.data
    assert b"Mario" in opened.data
    assert b"Vanessa" in opened.data
    assert b"AI Assist" in opened.data
    assert b'<option value="all" selected>Full itinerary</option>' in opened.data
    assert b"data-close-details" in opened.data
    assert b"Check tyre pressure" in pack.data
    assert b"Park confirmation" in pack.data
    assert b"AUD 320.50" in pack.data


def test_trip_workspace__autosave_booking__persists_without_redirect(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Save booking details from the workspace without leaving the page.

    Pytest node:
    tests/test_smart_trip.py::
    test_trip_workspace__autosave_booking__persists_without_redirect
    Needs: REQ-006, TEST-019
    """

    # Arrange
    created = flask_client.post(
        "/smart-trip/new",
        data={"title": "Autosave stay", "plan_category": "Hotel", "trip_kind": "weekend"},
    )
    trip_id = _trip_id(created.headers["Location"])

    # Act
    saved = flask_client.post(
        f"/trip/weekend/{trip_id}",
        data={
            "autosave": "1",
            "title": "Autosave stay",
            "plan_category": "Hotel",
            "start_date": "2026-12-11",
            "end_date": "2026-12-18",
            "booking_category": ["Accommodation"],
            "booking_name": ["Beach House Seaside Resort"],
            "booking_date": ["2026-12-11"],
            "booking_reference": ["BH482910"],
            "active_tab": "bookings",
        },
    )
    opened = flask_client.get(f"/trip/weekend/{trip_id}")

    # Assert
    assert saved.status_code == 200
    assert saved.json == {"ok": True}
    assert b"BH482910" in opened.data
    assert b"Add booking" in opened.data
    assert b"Autosaves" in opened.data


def test_trip_workspace_task_status__autosave_checkbox__persists_done_state(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """Autosave a Family Tasks checkbox change without a full workspace submit.

    Pytest node:
    tests/test_smart_trip.py::
    test_trip_workspace_task_status__autosave_checkbox__persists_done_state
    Needs: REQ-006, TEST-019
    """

    # Arrange
    created = flask_client.post(
        "/smart-trip/new",
        data={
            "title": "Task trip",
            "plan_category": "Weekend away",
            "trip_kind": "weekend",
        },
    )
    trip_id = _trip_id(created.headers["Location"])
    flask_client.post(
        f"/trip/weekend/{trip_id}",
        data={
            "title": "Task trip",
            "plan_category": "Weekend away",
            "task_owner": [""],
            "task_text": ["Passport"],
            "task_due": [""],
            "task_status": ["To do"],
        },
    )

    # Act
    autosaved = flask_client.post(
        f"/trip/weekend/{trip_id}/task-status",
        json={"index": 0, "text": "Passport", "done": True},
    )
    opened = flask_client.get(f"/trip/weekend/{trip_id}#tasks")

    # Assert
    assert autosaved.status_code == 200
    assert autosaved.json == {"index": 0, "ok": True, "status": "Done"}
    assert b'value="Done" data-task-status-hidden' in opened.data
    assert b"data-task-done data-inline-autosave" in opened.data
    assert b"checked" in opened.data
