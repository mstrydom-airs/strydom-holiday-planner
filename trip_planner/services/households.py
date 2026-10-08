"""Which family a saved trip belongs to on the home page.

A trip shows on Mario & Esme, Reuben & Vanessa, or both tabs. Two saved
plans may share a title so each family can keep its own copy.

Needs: REQ-007, SPEC-007, IMPL-007, TEST-021
"""

from __future__ import annotations

import copy
from typing import Any

HOUSEHOLD_MARIO = "mario_esme"
HOUSEHOLD_REUBEN = "reuben_vanessa"
MARIO_HOUSEHOLD = frozenset({"mario", "esme", HOUSEHOLD_MARIO})
REUBEN_HOUSEHOLD = frozenset({"reuben", "vanessa", HOUSEHOLD_REUBEN, "reuben_family"})
HOUSEHOLD_LABELS = {
    HOUSEHOLD_MARIO: "Mario & Esme",
    HOUSEHOLD_REUBEN: "Reuben & Vanessa",
}


def households_for_plan(plan: dict[str, Any]) -> set[str]:
    """Return the home tabs a trip belongs on.

    ``all_of_us`` and other shared people stay unassigned until a family
    is chosen.

    Needs: REQ-007, TEST-021
    """
    people = set(plan.get("travelers") or [])
    profile = str(plan.get("planner_profile") or "").strip()
    if profile in MARIO_HOUSEHOLD or profile in REUBEN_HOUSEHOLD:
        people.add(profile)
    found: set[str] = set()
    if people & MARIO_HOUSEHOLD:
        found.add(HOUSEHOLD_MARIO)
    if people & REUBEN_HOUSEHOLD:
        found.add(HOUSEHOLD_REUBEN)
    return found


def other_household(household: str) -> str:
    """Return the opposite family tag.

    Needs: REQ-007, TEST-021
    """
    if household == HOUSEHOLD_MARIO:
        return HOUSEHOLD_REUBEN
    if household == HOUSEHOLD_REUBEN:
        return HOUSEHOLD_MARIO
    return ""


def describe_households(plan: dict[str, Any]) -> str:
    """Short label such as ``Mario & Esme`` for a plan's families.

    Needs: REQ-007, TEST-021
    """
    found = households_for_plan(plan)
    names = [HOUSEHOLD_LABELS[key] for key in (HOUSEHOLD_MARIO, HOUSEHOLD_REUBEN) if key in found]
    return ", ".join(names)


def trips_for_household_tab(rows: list[dict[str, Any]], household: str) -> list[dict[str, Any]]:
    """Return only trips explicitly assigned to one family.

    Needs: REQ-007, TEST-021
    """
    return [row for row in rows if household in (row.get("households") or set())]


def split_traveler_groups(selected: list[str]) -> list[list[str]]:
    """Split a create-form selection into one list per family.

    Shared people such as Noah are copied onto each family's trip. A
    selection that names only one family is returned unchanged.

    Needs: REQ-007, TEST-021
    """
    mario = [person for person in selected if person in MARIO_HOUSEHOLD]
    reuben = [person for person in selected if person in REUBEN_HOUSEHOLD]
    shared = [
        person
        for person in selected
        if person not in MARIO_HOUSEHOLD and person not in REUBEN_HOUSEHOLD
    ]
    if mario and reuben:
        return [mario + shared, reuben + shared]
    return [list(selected)]


def assign_household(plan: dict[str, Any], household: str) -> None:
    """Turn one family tag on or off without removing the other family.

    Needs: REQ-007, TEST-021
    """
    if household not in HOUSEHOLD_LABELS:
        return
    drop = MARIO_HOUSEHOLD if household == HOUSEHOLD_MARIO else REUBEN_HOUSEHOLD
    people = [str(person) for person in (plan.get("travelers") or [])]
    if household in households_for_plan(plan):
        plan["travelers"] = [person for person in people if person not in drop]
        if plan.get("planner_profile") in drop:
            plan["planner_profile"] = ""
        return
    shared = [
        person
        for person in people
        if person not in MARIO_HOUSEHOLD and person not in REUBEN_HOUSEHOLD
    ]
    plan["travelers"] = [household, *shared]
    plan["planner_profile"] = household


def copy_plan_for_household(plan: dict[str, Any], household: str, new_id: str) -> dict[str, Any]:
    """Deep-copy a trip for one family, keeping the title and dates.

    Needs: REQ-007, TEST-021
    """
    copied: dict[str, Any] = copy.deepcopy(plan)
    copied["id"] = new_id
    people = [str(person) for person in (plan.get("travelers") or [])]
    shared = [
        person
        for person in people
        if person not in MARIO_HOUSEHOLD and person not in REUBEN_HOUSEHOLD
    ]
    copied["travelers"] = [household, *shared]
    copied["planner_profile"] = household
    return copied


def has_household_copy(
    rows: list[dict[str, Any]], source_row: dict[str, Any], household: str
) -> bool:
    """True when another saved row already has this title, dates, and family.

    Needs: REQ-007, TEST-021
    """
    source_plan = source_row.get("plan") or {}
    title = str(source_plan.get("title") or "").strip().lower()
    dates = str(source_row.get("date_label") or "")
    source_id = source_plan.get("id")
    for row in rows:
        plan = row.get("plan") or {}
        if plan.get("id") == source_id:
            continue
        if household not in (row.get("households") or set()):
            continue
        other_title = str(plan.get("title") or "").strip().lower()
        if other_title == title and str(row.get("date_label") or "") == dates:
            return True
    return False


def attach_copy_targets(rows: list[dict[str, Any]]) -> None:
    """Mark which opposite-family copy each row is still allowed to create.

    Needs: REQ-007, TEST-021
    """
    for row in rows:
        targets: list[str] = []
        for household in row.get("households") or []:
            other = other_household(str(household))
            if other and not has_household_copy(rows, row, other):
                targets.append(other)
        row["copy_targets"] = targets
