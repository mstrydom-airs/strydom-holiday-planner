"""Helpers for the unified smart trip workspace.

The first version is deterministic: it behaves like an assistant by combining
trip type, selected transport/accommodation, and past choices. A later external
AI integration can replace or extend these helpers without changing templates.

Needs: REQ-006, SPEC-006, IMPL-006, TEST-018
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class AssistantSuggestions:
    """Suggested next actions for a trip workspace.

    Needs: REQ-006, TEST-018
    """

    packing_items: list[str]
    booking_prompts: list[str]
    planning_prompts: list[str]


COMMON_PACKING_ITEMS = [
    "Phone charger",
    "Wallet",
    "ID",
    "Medication",
    "Water",
    "Sunscreen",
]

CATEGORY_PACKING_ITEMS = {
    "Holiday overseas": [
        "Passport",
        "Insurance",
        "Power adaptor",
        "Confirmations",
    ],
    "Caravan trip": [
        "Tow mirrors",
        "Levelling ramps",
        "Power lead",
        "Fresh water hose",
        "Wheel chocks",
    ],
    "Weekend away": ["Overnight bag", "Comfortable shoes", "Casual clothes"],
    "Long weekend": ["Clothes", "Laundry bag", "Rain jacket"],
    "Day trip": ["Snacks", "Hat", "Day backpack"],
    "Movie": ["Tickets", "Parking"],
    "Theatre / show": ["Tickets", "Smart casual", "Dinner"],
    "Restaurant booking": ["Confirmation", "Voucher"],
}

TRANSPORT_PACKING_ITEMS = {
    "Flights": ["Boarding pass", "Carry-on", "Luggage tags"],
    "train": ["Train tickets", "Headphones"],
    "Ute": ["Tie-down straps", "Recovery gear"],
    "Car": ["Fuel plan", "Phone mount", "Car snacks"],
    "Boat Trip": ["Sea tablets", "Reef shoes", "Dry bag"],
}

ACCOMMODATION_PACKING_ITEMS = {
    "Caravan": ["Bedding", "Outdoor chairs", "Torch"],
    "Tent": ["Tent pegs", "Sleeping bags", "Camp light"],
    "Timeshares": ["Member details"],
    "Accor": ["Accor details"],
    "Hotel": ["Hotel confirmation", "Check-in ID"],
}

PROFILE_PACKING_ITEMS = {
    "mario": ["Vehicle keys", "Fuel card", "Route plan"],
    "esme": ["Med list", "Toiletries", "Confirmations"],
    "mario_esme": ["Itinerary", "Emergency contacts"],
    "reuben": ["Kids activities", "Chargers"],
    "vanessa": ["Snacks", "Wet wipes", "Spare clothes"],
    "noah": ["Entertainment", "Headphones", "Jumper"],
    "reuben_family": ["Kids activities", "Family snacks", "Spare clothes"],
    "family": ["Family snacks", "Games", "First aid kit"],
    "all_of_us": ["Family snacks", "Games", "First aid kit"],
}

PROFILE_PLANNING_PROMPTS = {
    "mario": ["Driving", "Parking"],
    "esme": ["Packing", "Documents"],
    "mario_esme": ["Travel", "Bookings"],
    "reuben": ["Family timing", "Kids"],
    "vanessa": ["Food", "Clothes"],
    "noah": ["Simple fun"],
    "reuben_family": ["Kids", "Timing"],
    "family": ["Shared tasks"],
    "all_of_us": ["Shared tasks"],
}

BOOKING_PROMPTS_BY_CATEGORY = {
    "Holiday overseas": [
        "Flights",
        "Hotels",
        "Insurance",
        "Passport",
        "Transfers",
    ],
    "Caravan trip": [
        "Site booking",
        "Check-in",
        "Powered site",
        "Route stops",
    ],
    "Movie": ["Cinema", "Session", "Seats", "Parking"],
    "Theatre / show": ["Venue", "Show time", "Seats", "Dinner"],
}


def normalise_workspace_plan(plan: dict[str, Any], kind: str) -> dict[str, Any]:
    """Return a plan with smart workspace defaults populated.

    Args:
        plan: Existing trip payload from SQLite.
        kind: Legacy trip kind such as ``weekend`` or ``extended``.

    Returns:
        The same dictionary, updated with default smart-workspace keys.

    Needs: REQ-006, SPEC-006, TEST-018
    """
    plan.setdefault("plan_category", _default_plan_category(kind))
    plan.setdefault("planner_profile", "all_of_us")
    plan.setdefault("stay_unit_size", "")
    plan.setdefault("booking_items", [])
    plan.setdefault("task_items", [])
    plan.setdefault("budget_items", [])
    plan.setdefault("document_items", [])
    plan.setdefault("booking_import_text", "")
    plan.setdefault("packing_items", [])
    plan.setdefault("assistant_notes", "")
    plan.setdefault("important_links", [])
    add_typical_trip_tasks(plan, kind)
    return plan


def add_typical_trip_tasks(plan: dict[str, Any], kind: str) -> int:
    """Add concise, relevant checklist items that are missing from a trip.

    Args:
        plan: Trip payload updated in place.
        kind: Saved trip type, used to identify extended overseas travel.

    Returns:
        Number of checklist items added.

    Needs: REQ-006, TEST-019
    """

    existing = {
        str(task.get("text") or "").strip().lower() for task in plan.setdefault("task_items", [])
    }
    added = 0
    for text in _typical_task_texts(plan, kind):
        if text.lower() in existing:
            continue
        plan["task_items"].append(
            {"owner": "", "text": text, "due": "", "status": "To do", "source": "auto"}
        )
        existing.add(text.lower())
        added += 1
    return added


def _typical_task_texts(plan: dict[str, Any], kind: str) -> list[str]:
    """Build checklist text from trip category, bookings, and transport."""

    category = str(plan.get("plan_category") or "").lower()
    title = str(plan.get("title") or "").lower()
    booking_blob = " ".join(
        f"{item.get('category', '')} {item.get('name', '')}"
        for item in plan.get("booking_items") or []
    ).lower()
    transport_blob = " ".join(plan.get("transport_overall") or plan.get("transport") or []).lower()
    tasks = [
        "Confirm booking references and outstanding balances",
        "Check weather and adjust packing",
        "Save confirmations and emergency contacts offline",
        "Pack medication, chargers and identification",
    ]
    if "flight" in booking_blob or "plane" in transport_blob:
        tasks.extend(
            ["Complete online check-in and save boarding passes", "Confirm baggage and transfers"]
        )
    if "accommodation" in booking_blob or any(
        word in booking_blob for word in ("hotel", "resort", "caravan")
    ):
        tasks.append("Reconfirm check-in, check-out and room or site inclusions")
    if "overseas" in category or ("flight" in booking_blob and kind == "extended"):
        tasks.extend(
            [
                "Check passport validity and entry requirements",
                "Arrange insurance, eSIM and payments",
            ]
        )
    if "caravan" in category or "caravan" in booking_blob:
        tasks.extend(["Check tyres, gas, water and power lead", "Confirm towing route and parking"])
    if "tour" in booking_blob or "show" in booking_blob or "activity" in booking_blob:
        tasks.append("Confirm timed tickets, venue and seats")
    if "beach" in category or "beach" in title:
        tasks.append("Pack sunscreen, hats and beach gear")
    if "christmas" in title or "xmas" in title or "new year" in title:
        tasks.append("Confirm celebration meals and supplies")
    return tasks


def assistant_suggestions(
    plan: dict[str, Any],
    kind: str,
    previous_packing: list[str] | None = None,
) -> AssistantSuggestions:
    """Build starter suggestions from the current plan and prior items.

    Args:
        plan: Trip payload.
        kind: Legacy trip kind used as a fallback category.
        previous_packing: Items used on other saved trips.

    Returns:
        Packing, booking, and planning suggestions ready for the template.

    Needs: REQ-006, SPEC-006, TEST-018
    """
    category = str(plan.get("plan_category") or _default_plan_category(kind))
    selected_transport = _selected_transport(plan)
    selected_accommodation = _selected_accommodation(plan)
    profile = str(plan.get("planner_profile") or "mario_esme")
    current_packing = _packing_texts(plan)

    items: list[str] = []
    items.extend(COMMON_PACKING_ITEMS)
    items.extend(CATEGORY_PACKING_ITEMS.get(category, []))
    for transport in selected_transport:
        items.extend(TRANSPORT_PACKING_ITEMS.get(transport, []))
    for accommodation in selected_accommodation:
        items.extend(ACCOMMODATION_PACKING_ITEMS.get(accommodation, []))
    items.extend(PROFILE_PACKING_ITEMS.get(profile, []))
    items.extend(previous_packing or [])

    packing_items = _dedupe([item for item in items if item not in current_packing])[:24]
    booking_prompts = BOOKING_PROMPTS_BY_CATEGORY.get(
        category,
        ["Links", "References", "Addresses", "Costs", "Contacts"],
    )
    planning_prompts = [
        "Dates",
        "Travel time",
        "Booking links",
    ]
    planning_prompts.extend(PROFILE_PLANNING_PROMPTS.get(profile, []))
    if kind == "extended":
        planning_prompts.append("Trip stops")
    return AssistantSuggestions(
        packing_items=packing_items,
        booking_prompts=booking_prompts,
        planning_prompts=planning_prompts,
    )


def parse_booking_rows(form: Any) -> list[dict[str, str]]:
    """Parse repeated booking row fields from a Flask form.

    Args:
        form: ``request.form`` or any object with ``getlist``.

    Returns:
        Non-empty booking dictionaries.

    Needs: REQ-006, TEST-018
    """
    fields = {
        "category": form.getlist("booking_category"),
        "name": form.getlist("booking_name"),
        "date": form.getlist("booking_date"),
        "end_date": form.getlist("booking_end_date"),
        "time": form.getlist("booking_time"),
        "checkout_time": form.getlist("booking_checkout_time"),
        "website": form.getlist("booking_website"),
        "reference": form.getlist("booking_reference"),
        "address": form.getlist("booking_address"),
        "notes": form.getlist("booking_notes"),
        "cost": form.getlist("booking_cost"),
        "cost_currency": form.getlist("booking_cost_currency"),
        "cost_status": form.getlist("booking_cost_status"),
        "cost_note": form.getlist("booking_cost_note"),
    }
    count = max((len(values) for values in fields.values()), default=0)
    bookings = []
    for index in range(count):
        row = {key: _form_value(values, index) for key, values in fields.items()}
        if any(row.values()):
            bookings.append(row)
    return bookings


def parse_packing_text(raw_text: str, checked_items: list[str]) -> list[dict[str, Any]]:
    """Convert a newline packing list into stored item dictionaries.

    Args:
        raw_text: Textarea content, one item per line.
        checked_items: Submitted packed item labels.

    Returns:
        Packing item dictionaries with packed state.

    Needs: REQ-006, TEST-018
    """
    checked = set(checked_items)
    rows = []
    for line in str(raw_text or "").splitlines():
        text = _clean_item(line)
        if text:
            rows.append({"text": text, "packed": text in checked, "source": "workspace"})
    return rows


def parse_task_rows(form: Any) -> list[dict[str, str]]:
    """Parse family task rows from the smart workspace form.

    Needs: REQ-006, TEST-019
    """
    fields = {
        "owner": form.getlist("task_owner"),
        "text": form.getlist("task_text"),
        "due": form.getlist("task_due"),
        "status": form.getlist("task_status"),
    }
    rows = _parse_non_empty_rows(fields)
    return [row for row in rows if row.get("text")]


def parse_budget_rows(form: Any) -> list[dict[str, str]]:
    """Parse budget rows from the smart workspace form.

    Needs: REQ-006, TEST-019
    """
    fields = {
        "category": form.getlist("budget_category"),
        "description": form.getlist("budget_description"),
        "amount": form.getlist("budget_amount"),
        "paid": form.getlist("budget_paid"),
    }
    return _parse_non_empty_rows(fields)


def parse_document_rows(form: Any) -> list[dict[str, str]]:
    """Parse document rows from the smart workspace form.

    Needs: REQ-006, TEST-019
    """
    fields = {
        "label": form.getlist("document_label"),
        "location": form.getlist("document_location"),
        "notes": form.getlist("document_notes"),
    }
    return _parse_non_empty_rows(fields)


def budget_items_from_bookings(bookings: list[dict[str, str]]) -> list[dict[str, str]]:
    """Turn each saved booking into one budget line.

    The amount is the booking cost. Estimated meals, flights, and visas are
    not added here.

    Needs: REQ-006, TEST-019
    """
    rows: list[dict[str, str]] = []
    for booking in bookings:
        name = str(booking.get("name") or "").strip()
        cost = str(booking.get("cost") or "").strip()
        if not cost:
            continue
        rows.append(
            {
                "category": str(booking.get("category") or "Booking"),
                "description": name or "Booking",
                "amount": cost,
                "paid": "",
                "source": "booking",
                "currency": str(booking.get("cost_currency") or "AUD"),
                "status": str(booking.get("cost_status") or "estimated"),
                "note": str(booking.get("cost_note") or ""),
            }
        )
    return rows


def budget_items_for_plan(plan: dict[str, Any]) -> list[dict[str, str]]:
    """Combine booking costs with researched or manually added budget rows.

    Args:
        plan: Trip payload containing bookings and optional extra budget rows.

    Returns:
        Booking-derived costs followed by researched or manually added costs.

    Needs: REQ-006, TEST-019
    """

    booking_rows = budget_items_from_bookings(plan.get("booking_items") or [])
    extra_rows = [
        dict(item)
        for item in plan.get("budget_items") or []
        if str(item.get("source") or "") != "booking"
    ]
    return booking_rows + extra_rows


def budget_totals_by_currency(budget_items: list[dict[str, str]]) -> dict[str, float]:
    """Total budget rows separately for each currency.

    Args:
        budget_items: Cost rows with amount and currency values.

    Returns:
        Numeric totals keyed by currency code.

    Needs: REQ-006, TEST-019
    """

    totals: dict[str, float] = {}
    for item in budget_items:
        currency = str(item.get("currency") or "AUD").strip().upper()
        try:
            amount = float(str(item.get("amount", "")).strip() or 0)
        except ValueError:
            continue
        totals[currency] = totals.get(currency, 0.0) + amount
    return totals


def budget_total(budget_items: list[dict[str, str]]) -> float:
    """Return the total numeric budget amount.

    Needs: REQ-006, TEST-019
    """
    total = 0.0
    for item in budget_items:
        try:
            total += float(str(item.get("amount", "")).strip() or 0)
        except ValueError:
            continue
    return total


def packing_text(plan: dict[str, Any]) -> str:
    """Render stored packing items as newline text for editing.

    Needs: REQ-006, TEST-018
    """
    return "\n".join(_packing_texts(plan))


def previous_packing_items(
    plans_by_kind: dict[str, list[dict[str, Any]]],
    trip_id: str,
) -> list[str]:
    """Collect reusable packing items from other trips.

    Needs: REQ-006, TEST-018
    """
    items: list[str] = []
    for plans in plans_by_kind.values():
        for plan in plans:
            if plan.get("id") == trip_id:
                continue
            items.extend(_packing_texts(plan))
    return _dedupe(items)


def append_suggestions_to_packing(
    plan: dict[str, Any],
    suggested_items: list[str],
) -> dict[str, Any]:
    """Add chosen suggestions to a plan's packing list without duplicates.

    Needs: REQ-006, TEST-018
    """
    existing = _packing_texts(plan)
    rows = list(plan.get("packing_items") or [])
    for item in suggested_items:
        clean = _clean_item(item)
        if clean and clean not in existing:
            rows.append({"text": clean, "packed": False, "source": "assistant"})
            existing.append(clean)
    plan["packing_items"] = rows
    return plan


def _default_plan_category(kind: str) -> str:
    return {
        "day_trip": "Day trip",
        "weekend": "Weekend away",
        "long_weekend": "Long weekend",
        "extended": "Holiday overseas",
    }.get(kind, "Other booking")


def _selected_transport(plan: dict[str, Any]) -> list[str]:
    return list(plan.get("transport_overall") or plan.get("transport") or [])


def _selected_accommodation(plan: dict[str, Any]) -> list[str]:
    out = list(plan.get("accommodation") or [])
    if (plan.get("accommodation_places") or "").strip() and "Hotel" not in out:
        out.append("Hotel")
    return out


def _packing_texts(plan: dict[str, Any]) -> list[str]:
    out = []
    for item in plan.get("packing_items") or []:
        if isinstance(item, dict):
            text = _clean_item(str(item.get("text", "")))
        else:
            text = _clean_item(str(item))
        if text:
            out.append(text)
    return out


def _clean_item(value: str) -> str:
    return value.strip().lstrip("-*0123456789. )").strip()


def _dedupe(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for value in values:
        key = value.casefold()
        if key in seen:
            continue
        seen.add(key)
        out.append(value)
    return out


def _form_value(values: list[str], index: int) -> str:
    if index >= len(values):
        return ""
    return str(values[index]).strip()


def _parse_non_empty_rows(fields: dict[str, list[str]]) -> list[dict[str, str]]:
    count = max((len(values) for values in fields.values()), default=0)
    rows = []
    for index in range(count):
        row = {key: _form_value(values, index) for key, values in fields.items()}
        if any(row.values()):
            rows.append(row)
    return rows
