"""iCalendar feeds built from saved Travel Hub trips.

Home Assistant should subscribe to these feeds. Trip details stay in
``travel_hub.db`` and are not copied into Home Assistant.

Needs: REQ-007, SPEC-007, IMPL-007, TEST-021
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

from trip_planner.services.households import households_for_plan


def trips_to_ics(rows: list[dict[str, Any]], calendar_name: str, household: str | None) -> str:
    """Build an iCalendar document for one family, or for every saved trip.

    Args:
        rows: Dictionaries with ``kind``, ``plan``, and ``households``.
        calendar_name: Calendar display name.
        household: ``mario_esme``, ``reuben_vanessa``, or ``None`` for every trip.

    Needs: REQ-007, TEST-021
    """
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Strydom Travel Hub//EN",
        f"X-WR-CALNAME:{_ics_text(calendar_name)}",
    ]
    for row in rows:
        if household is not None and household not in row.get("households", ()):
            continue
        event = _event_lines(row.get("plan") or {})
        if event:
            lines.extend(event)
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"


def calendar_rows(plans_by_kind: dict[str, list[dict[str, Any]]]) -> list[dict[str, Any]]:
    """Shape saved plans for the calendar feed.

    Needs: REQ-007, TEST-021
    """
    rows = []
    for kind, plans in plans_by_kind.items():
        for plan in plans:
            rows.append(
                {
                    "kind": kind,
                    "plan": plan,
                    "households": households_for_plan(plan),
                }
            )
    return rows


def _event_lines(plan: dict[str, Any]) -> list[str]:
    start = _parse_date(plan.get("trip_start") or plan.get("start_date"))
    end = _parse_date(plan.get("trip_end") or plan.get("end_date")) or start
    if start is None or end is None:
        return []
    end_exclusive = end + timedelta(days=1)
    title = str(plan.get("title") or "Trip").strip() or "Trip"
    return [
        "BEGIN:VEVENT",
        f"UID:{_ics_text(str(plan.get('id') or title))}@travel-hub",
        f"DTSTAMP:{_stamp()}",
        f"DTSTART;VALUE=DATE:{start.strftime('%Y%m%d')}",
        f"DTEND;VALUE=DATE:{end_exclusive.strftime('%Y%m%d')}",
        f"SUMMARY:{_ics_text(title)}",
        "END:VEVENT",
    ]


def _parse_date(value: object) -> date | None:
    text = str(value or "")[:10]
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", " ").replace(",", "\\,").replace(";", "\\;")


def _stamp() -> str:
    return datetime.now().strftime("%Y%m%dT%H%M%SZ")
