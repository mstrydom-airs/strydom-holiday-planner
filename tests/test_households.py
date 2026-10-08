"""Home family badges, same-name copies, and selective plan delete.

Needs: REQ-007, SPEC-007, IMPL-007, TEST-021, UC-004
"""

from __future__ import annotations

import pytest

import app as app_module
from trip_planner.services.calendar_feed import trips_to_ics
from trip_planner.services.households import (
    assign_household,
    copy_plan_for_household,
    describe_households,
    has_household_copy,
    other_household,
    split_traveler_groups,
    trips_for_household_tab,
)


def _trip_id(location: str) -> str:
    return location.rstrip("/").split("/")[-1]


def _new_extended(flask_client, title: str, travelers: list[str] | None = None):  # type: ignore[no-untyped-def]
    data: dict[str, str | list[str]] = {
        "title": title,
        "plan_category": "Hotel",
        "trip_kind": "extended",
        "start_date": "2026-12-11",
        "end_date": "2027-01-04",
    }
    if travelers:
        data["travelers"] = travelers
    response = flask_client.post("/smart-trip/new", data=data)
    assert response.status_code == 302
    return _trip_id(response.headers["Location"])


def test_other_household__unknown__returns_blank() -> None:
    """An unknown family tag has no opposite.

    Pytest node: tests/test_households.py::test_other_household__unknown__returns_blank
    Needs: REQ-007, TEST-021
    """
    assert other_household("friends") == ""


def test_assign_household__new_family__keeps_shared_people() -> None:
    """Turning a family on keeps Noah and ignores an unknown tag.

    Pytest node: tests/test_households.py::test_assign_household__new_family__keeps_shared_people
    Needs: REQ-007, TEST-021
    """
    plan = {"travelers": ["noah"], "planner_profile": "all_of_us"}

    assign_household(plan, "not-a-family")
    assign_household(plan, "mario_esme")
    assert plan["planner_profile"] == "mario_esme"

    assign_household(plan, "mario_esme")

    assert plan["travelers"] == ["noah"]
    assert plan["planner_profile"] == ""


def test_describe_households__both_families__joins_both_names() -> None:
    """A plan tagged for both families lists both names.

    Pytest node: tests/test_households.py::test_describe_households__both_families__joins_both_names
    Needs: REQ-007, TEST-021
    """
    label = describe_households({"travelers": ["mario", "reuben"]})

    assert label == "Mario & Esme, Reuben & Vanessa"


def test_has_household_copy__different_title__is_not_a_copy() -> None:
    """A different trip name is not treated as the family's copy.

    Pytest node: tests/test_households.py::test_has_household_copy__different_title__is_not_a_copy
    Needs: REQ-007, TEST-021
    """
    source = {"plan": {"id": "a", "title": "Dec XMAS 2026"}, "date_label": "11 Dec 26 → 04 Jan 27"}
    rows = [
        source,
        {
            "plan": {"id": "c", "title": "Somewhere else"},
            "date_label": "11 Dec 26 → 04 Jan 27",
            "households": {"mario_esme"},
        },
        {
            "plan": {"id": "d", "title": "Other dates"},
            "date_label": "01 May 26",
            "households": {"reuben_vanessa"},
        },
        {
            "plan": {"id": "b", "title": "Easter"},
            "date_label": "11 Dec 26 → 04 Jan 27",
            "households": {"reuben_vanessa"},
        },
    ]

    assert has_household_copy(rows, source, "reuben_vanessa") is False


def test_trips_to_ics__reuben_feed__skips_other_families() -> None:
    """The Reuben & Vanessa calendar contains only trips named for that family.

    Pytest node:
    tests/test_households.py::test_trips_to_ics__reuben_feed__skips_other_families
    Needs: REQ-007, TEST-021
    """
    rows = [
        {
            "plan": {
                "id": "me",
                "title": "Shanghai Robot Show",
                "trip_start": "2026-10-10",
                "trip_end": "2026-10-17",
            },
            "households": {"mario_esme"},
        },
        {
            "plan": {
                "id": "free",
                "title": "Easter 2027 Mainbeach",
                "start_date": "2027-03-25",
                "end_date": "2027-03-31",
            },
            "households": set(),
        },
    ]

    body = trips_to_ics(rows, "Reuben & Vanessa", "reuben_vanessa")

    assert "BEGIN:VCALENDAR" in body
    assert "Shanghai Robot Show" not in body
    assert "Easter 2027 Mainbeach" not in body


def test_trips_for_household_tab__unassigned__stays_off_family_lists() -> None:
    """A trip with no family assignment is not shown under either family.

    Pytest node:
    tests/test_households.py::test_trips_for_household_tab__unassigned__stays_off_family_lists
    Needs: REQ-007, TEST-021
    """
    rows = [
        {"plan": {"id": "free"}, "households": set()},
        {"plan": {"id": "rv"}, "households": {"reuben_vanessa"}},
    ]

    shown = trips_for_household_tab(rows, "mario_esme")

    assert shown == []


def test_assign_household__turn_one_family_off__leaves_the_other() -> None:
    """Clearing one family tag keeps the other family on the plan.

    Pytest node:
    tests/test_households.py::test_assign_household__turn_one_family_off__leaves_the_other
    Needs: REQ-007, TEST-021
    """
    plan = {"travelers": ["mario_esme", "reuben_vanessa"], "planner_profile": "all_of_us"}

    assign_household(plan, "mario_esme")

    assert plan["travelers"] == ["reuben_vanessa"]
    assert plan["planner_profile"] == "all_of_us"


def test_split_traveler_groups__both_families__two_lists_sharing_noah() -> None:
    """People from both families become two traveler lists.

    Pytest node:
    tests/test_households.py::test_split_traveler_groups__both_families__two_lists_sharing_noah
    Needs: REQ-007, TEST-021
    """
    groups = split_traveler_groups(["mario", "esme", "reuben", "vanessa", "noah"])

    assert groups == [
        ["mario", "esme", "noah"],
        ["reuben", "vanessa", "noah"],
    ]


def test_copy_plan_for_household__same_title__sets_only_the_target_family() -> None:
    """A copied plan keeps the name and dates and belongs to one family.

    Pytest node:
    tests/test_households.py::test_copy_plan_for_household__same_title__sets_only_the_target_family
    Needs: REQ-007, TEST-021
    """
    source = {
        "id": "source",
        "title": "Dec XMAS 2026",
        "trip_start": "2026-12-11",
        "trip_end": "2027-01-04",
        "travelers": ["mario_esme", "noah"],
    }

    copied = copy_plan_for_household(source, "reuben_vanessa", "copy-1")

    assert copied["id"] == "copy-1"
    assert copied["title"] == "Dec XMAS 2026"
    assert copied["trip_start"] == "2026-12-11"
    assert copied["travelers"] == ["reuben_vanessa", "noah"]
    assert source["id"] == "source"


def test_home__one_family__shows_only_that_familys_trips(flask_client) -> None:  # type: ignore[no-untyped-def]
    """A trip named for Mario and Esme is listed without a family button.

    Pytest node:
    tests/test_households.py::test_home__one_family__shows_only_that_familys_trips
    Needs: REQ-007, TEST-021
    """
    _new_extended(flask_client, "Shanghai Robot Show", ["mario", "esme"])

    html = flask_client.get("/").get_data(as_text=True)

    assert "Shanghai Robot Show" in html
    assert "who-btn" not in html
    assert "Copy for" not in html
    assert "Next up" not in html


def test_copy_for_household__same_name__keeps_a_plan_for_each_family(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Copying Dec XMAS gives Reuben & Vanessa their own plan with the same name.

    Pytest node:
    tests/test_households.py::test_copy_for_household__same_name__keeps_a_plan_for_each_family
    Needs: REQ-007, UC-004, TEST-021
    """
    trip_id = _new_extended(flask_client, "Dec XMAS 2026", ["mario", "esme"])

    copied = flask_client.post(
        f"/trip/extended/{trip_id}/copy-for-household",
        data={"household": "reuben_vanessa"},
    )
    html = flask_client.get("/").get_data(as_text=True)

    assert copied.status_code == 302
    assert html.count("Dec XMAS 2026") == 2
    assert "who-btn" not in html


def test_copy_for_household__second_click__does_not_add_a_third(flask_client) -> None:  # type: ignore[no-untyped-def]
    """The same family does not get a second copy of an existing named trip.

    Pytest node:
    tests/test_households.py::test_copy_for_household__second_click__does_not_add_a_third
    Needs: REQ-007, TEST-021
    """
    trip_id = _new_extended(flask_client, "Dec XMAS 2026", ["mario", "esme"])
    flask_client.post(
        f"/trip/extended/{trip_id}/copy-for-household",
        data={"household": "reuben_vanessa"},
    )

    flask_client.post(
        f"/trip/extended/{trip_id}/copy-for-household",
        data={"household": "reuben_vanessa"},
    )

    assert flask_client.get("/").get_data(as_text=True).count("Dec XMAS 2026") == 2


def test_smart_trip_new__both_families__saves_two_plans(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Choosing both families at creation stores two plans with the same name.

    Pytest node:
    tests/test_households.py::test_smart_trip_new__both_families__saves_two_plans
    Needs: REQ-007, TEST-021
    """
    _new_extended(flask_client, "Dec XMAS 2026", ["mario", "esme", "reuben", "vanessa"])

    html = flask_client.get("/").get_data(as_text=True)

    assert html.count("Dec XMAS 2026") == 2


def test_smart_trip_new__family_and_companion__shows_companion_above_trip(
    flask_client,
) -> None:  # type: ignore[no-untyped-def]
    """The optional companion is saved and appears only on its trip."""
    created = flask_client.post(
        "/smart-trip/new",
        data={
            "title": "Friends weekend",
            "plan_category": "Hotel",
            "trip_kind": "weekend",
            "travelers": "mario_esme",
            "travelers_other": "Sam and Lee",
        },
    )

    html = flask_client.get("/").get_data(as_text=True)

    assert created.status_code == 302
    assert "With Sam and Lee" in html
    assert html.index("With Sam and Lee") < html.index("Friends weekend")


def test_home__trip_without_companion__does_not_render_companion_line(flask_client) -> None:  # type: ignore[no-untyped-def]
    """The companion line is absent when the optional field is blank."""
    _new_extended(flask_client, "Family only", ["mario_esme"])

    html = flask_client.get("/").get_data(as_text=True)

    assert "Family only" in html
    assert "home-trip-guests" not in html


def test_clear_plans__selected_trip__leaves_the_other(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Delete removes the ticked plan and leaves the unticked plan saved.

    Pytest node:
    tests/test_households.py::test_clear_plans__selected_trip__leaves_the_other
    Needs: REQ-007, UC-004, TEST-021
    """
    remove_id = _new_extended(flask_client, "Old weekend", ["mario"])
    _new_extended(flask_client, "Easter 2027 Mainbeach", ["reuben"])

    deleted = flask_client.post("/clear-plans", data={"trip_id": remove_id})
    html = flask_client.get("/").get_data(as_text=True)

    assert deleted.status_code == 302
    assert "Old weekend" not in html
    assert "Easter 2027 Mainbeach" in html


def test_clear_plans__none_selected__deletes_nothing(flask_client) -> None:  # type: ignore[no-untyped-def]
    """Submitting the chooser with no ticks does not delete plans.

    Pytest node:
    tests/test_households.py::test_clear_plans__none_selected__deletes_nothing
    Needs: REQ-007, UC-004, TEST-021
    """
    _new_extended(flask_client, "Easter 2027 Mainbeach", ["mario"])

    page = flask_client.post("/clear-plans", data={})
    html = page.get_data(as_text=True)

    assert page.status_code == 200
    assert "Choose at least one plan." in html
    assert "Easter 2027 Mainbeach" in flask_client.get("/").get_data(as_text=True)


def test_clear_session__post__does_not_delete_plans(flask_client) -> None:  # type: ignore[no-untyped-def]
    """The old clear-all address opens the chooser and keeps every plan.

    Pytest node:
    tests/test_households.py::test_clear_session__post__does_not_delete_plans
    Needs: REQ-007, TEST-021
    """
    _new_extended(flask_client, "Easter 2027 Mainbeach", ["mario"])

    response = flask_client.post("/clear-session")

    assert response.status_code == 302
    assert response.headers["Location"].endswith("/clear-plans")
    assert "Easter 2027 Mainbeach" in flask_client.get("/").get_data(as_text=True)


def test_plans_payload__same_name_and_length__adds_family_suffix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two extended trips with one name stay distinct in Holiday Details.

    Pytest node:
    tests/test_households.py::test_plans_payload__same_name_and_length__adds_family_suffix
    Needs: REQ-007, TEST-021
    """
    plans_by_kind = {
        "day_trip": [],
        "weekend": [],
        "long_weekend": [],
        "extended": [
            {
                "id": "me",
                "title": "Dec XMAS 2026",
                "trip_start": "2026-12-11",
                "trip_end": "2027-01-04",
                "travelers": ["mario_esme"],
            },
            {
                "id": "rv",
                "title": "Dec XMAS 2026",
                "trip_start": "2026-12-11",
                "trip_end": "2027-01-04",
                "travelers": ["reuben_vanessa"],
            },
        ],
    }
    monkeypatch.setattr(app_module, "_get_plans", lambda kind: plans_by_kind[kind])

    labels = [row["label"] for row in app_module._plans_payload_for_holiday_json()["all_trips"]]

    assert labels == [
        "Dec XMAS 2026 — 11 Dec 26 → 04 Jan 27 · Extended trip · Mario & Esme",
        "Dec XMAS 2026 — 11 Dec 26 → 04 Jan 27 · Extended trip · Reuben & Vanessa",
    ]
