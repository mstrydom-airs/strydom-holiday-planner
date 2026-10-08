"""
Strydom Travel Hub — Flask web application.

Trip plans are stored in SQLite (travel_hub.db). The session still holds
the Flask session cookie, things-to-do library, and shared checklist pairs.
"""

import copy
import io
import os
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from email import policy
from email.parser import BytesParser

from flask import Flask, Response, jsonify, redirect, render_template, request, session, url_for
from pypdf import PdfReader

from database import (
    count_trips,
    delete_trip as db_delete_trip,
    ensure_trips_schema,
    fetch_plan,
    fetch_plans_for_kind,
    get_db,
    register_db,
    upsert_trip,
)
from trip_planner.options import (
    ACCOMMODATION_CHECKBOXES,
    ACCOMMODATION_OPTIONS,
    BOOKING_CATEGORY_OPTIONS,
    GOING_PERSON_OPTIONS,
    HOLIDAY_TYPE_OPTIONS,
    PLANNER_PROFILE_OPTIONS,
    STANDARD_THINGS,
    STAY_SIZE_OPTIONS,
    THINGS_TO_DO_OPTIONS,
    TRANSPORT_OPTIONS,
    TRAVELER_LABELS,
    TRAVELER_OPTIONS,
    TRIP_CATEGORY_OPTIONS,
    TRIP_LENGTH_OPTIONS,
)
from trip_planner.services.calendar_feed import calendar_rows, trips_to_ics
from trip_planner.services.document_scan import apply_missing_booking_details, image_text
from trip_planner.services.households import (
    HOUSEHOLD_MARIO,
    HOUSEHOLD_REUBEN,
    assign_household,
    attach_copy_targets,
    copy_plan_for_household,
    describe_households,
    has_household_copy,
    households_for_plan,
    split_traveler_groups,
    trips_for_household_tab,
)
from trip_planner.services.place_lookup import fill_missing_place_contacts
from trip_planner.services.smart_trip import (
    append_suggestions_to_packing,
    assistant_suggestions,
    budget_items_from_bookings,
    budget_total,
    normalise_workspace_plan,
    packing_text,
    parse_booking_rows,
    parse_document_rows,
    parse_packing_text,
    parse_task_rows,
    previous_packing_items,
)

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or uuid.uuid4().hex
register_db(app)


PAIR_SEP = "|"
MIN_ITINERARY_LINE_LENGTH = 4
MAX_ACCOMMODATION_LINE_LENGTH = 90
SHORT_YEAR_LENGTH = 2

# Prepended to shared checklist text per pair; updated on each trip save (same for all trip types).
CHECKLIST_AUTO_MARKER = "--- Trip selections (auto) ---\n"


# Session keys for legacy import only (plans now live in SQLite).
PLANS_SESSION_KEYS = {
    "day_trip": "day_trip_plans",
    "weekend": "weekend_plans",
    "long_weekend": "long_weekend_plans",
    "extended": "extended_plans",
}
TRIP_KINDS = tuple(PLANS_SESSION_KEYS)
LEGACY_PLAN_KEYS = ("weekend", "long_weekend", "extended")


def _fmt_dmy_py(date_str):
    """Same as fmt_dmy template filter."""
    if not date_str:
        return ""
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return d.strftime("%d %b %y")
    except ValueError:
        return str(date_str)


def _new_trip_id():
    return uuid.uuid4().hex[:16]


def _migrate_legacy_trips():
    """Migrate session['weekend'] (single dict) -> session['weekend_plans'] (list)."""
    for old_k in LEGACY_PLAN_KEYS:
        new_k = PLANS_SESSION_KEYS[old_k]
        pl = session.get(new_k)
        # Skip only when we already have saved trips (non-empty list). Empty [] still migrates.
        if isinstance(pl, list) and len(pl) > 0:
            continue
        old = session.get(old_k)
        if old and isinstance(old, dict):
            if not old.get("id"):
                old["id"] = _new_trip_id()
            session[new_k] = [old]
            session.pop(old_k, None)
            session.modified = True


def _ensure_things_library():
    """Per-holiday-type lists for custom things to do (from previous trips + manual adds)."""
    if session.get("things_library_by_kind") is not None:
        return
    legacy = list(session.get("sticky_things") or [])
    lib = {}
    for kind in PLANS_SESSION_KEYS:
        lib[kind] = [x for x in legacy if isinstance(x, str) and x.strip()]
    session["things_library_by_kind"] = lib
    session.modified = True


def _session_plans_as_list(raw):
    if isinstance(raw, dict):
        return [raw]
    if isinstance(raw, list):
        return [p for p in raw if isinstance(p, dict)]
    return []


def _import_trip_if_new(conn, kind, plan, seen_ids):
    """Import one session trip if it has a fresh id."""
    tid = plan.get("id")
    if not tid or tid in seen_ids:
        return False
    seen_ids.add(tid)
    upsert_trip(conn, kind, plan)
    return True


def _iter_session_trip_candidates():
    """Yield ``(kind, plan)`` pairs from modern and legacy session storage."""
    for kind, session_key in PLANS_SESSION_KEYS.items():
        for plan in _session_plans_as_list(session.get(session_key)):
            yield kind, plan
    for kind in LEGACY_PLAN_KEYS:
        old = session.get(kind)
        if isinstance(old, dict):
            yield kind, old


def _import_session_trips_once(conn):
    """One-time copy from session lists into SQLite when DB is empty."""
    if count_trips(conn) > 0:
        return
    seen_ids = set()
    any_import = False

    for kind, plan in _iter_session_trip_candidates():
        if _import_trip_if_new(conn, kind, plan, seen_ids):
            any_import = True
    if any_import:
        for sk in PLANS_SESSION_KEYS.values():
            session.pop(sk, None)
        for old_k in LEGACY_PLAN_KEYS:
            session.pop(old_k, None)
        session.modified = True
    conn.commit()


@app.before_request
def _session_boot():
    _migrate_legacy_trips()
    _ensure_things_library()
    conn = get_db()
    ensure_trips_schema(conn)
    _import_session_trips_once(conn)


def _get_plans(kind):
    """Return list of trip dicts for this holiday type from SQLite."""
    return fetch_plans_for_kind(get_db(), kind)


def _find_plan(kind, trip_id):
    if not trip_id:
        return None
    return fetch_plan(get_db(), kind, trip_id)


def _replace_plan(kind, updated):
    conn = get_db()
    upsert_trip(conn, kind, updated)
    conn.commit()


def _delete_plan(kind, trip_id):
    conn = get_db()
    db_delete_trip(conn, trip_id)
    conn.commit()


def _default_title(kind):
    return {
        "day_trip": "Day trip",
        "weekend": "Weekend trip",
        "long_weekend": "Long weekend",
        "extended": "Extended trip",
    }[kind]


def _new_empty_plan(kind, title=None):
    base = {
        "id": _new_trip_id(),
        "title": (title or _default_title(kind)).strip() or _default_title(kind),
    }
    if kind in ("day_trip", "weekend", "long_weekend"):
        base["start_date"] = ""
        base["end_date"] = ""
    if kind == "extended":
        base["legs"] = [{}]
        base["trip_start"] = ""
        base["trip_end"] = ""
    return base


def _duplicate_plan_without_dates(kind, source):
    """Copy a saved plan with a new id; clear date fields and day planner."""
    p = copy.deepcopy(source)
    p["id"] = _new_trip_id()
    if kind in ("day_trip", "weekend", "long_weekend"):
        p["start_date"] = ""
        p["end_date"] = ""
    elif kind == "extended":
        p["trip_start"] = ""
        p["trip_end"] = ""
        legs = p.get("legs") or []
        new_legs = []
        for leg in legs:
            lg = copy.deepcopy(leg) if isinstance(leg, dict) else {}
            lg["start_date"] = ""
            lg["end_date"] = ""
            new_legs.append(lg)
        if not new_legs:
            new_legs = [{}]
        p["legs"] = new_legs
    pd = p.get("planner_days")
    if isinstance(pd, dict):
        p["planner_days"] = {}
    return p


def _get_things_library(kind):
    d = session.get("things_library_by_kind") or {}
    lst = d.get(kind)
    if not isinstance(lst, list):
        return []
    return list(lst)


def _merge_things_library_from_picks(kind, picks, new_text):
    lib = _get_things_library(kind)
    seen = set(lib)
    for p in picks:
        if p in STANDARD_THINGS or not (p and str(p).strip()):
            continue
        s = str(p).strip()
        if s not in seen:
            lib.append(s)
            seen.add(s)
    if new_text:
        s = new_text.strip()
        if s and s not in seen:
            lib.append(s)
    d = dict(session.get("things_library_by_kind") or {})
    d[kind] = lib
    session["things_library_by_kind"] = d
    session.modified = True


def _resolve_things_to_do_picks(trip_kind):
    lib = _get_things_library(trip_kind)
    sticky_legacy = list(session.get("sticky_things") or [])
    picked = []
    for p in _selected_list("things_to_do"):
        if not isinstance(p, str):
            continue
        if p.startswith("libidx:"):
            try:
                i = int(p.split(":", 1)[1])
                if 0 <= i < len(lib):
                    picked.append(lib[i])
            except ValueError:
                continue
        elif p.startswith("stickyidx:"):
            try:
                i = int(p.split(":", 1)[1])
                if 0 <= i < len(sticky_legacy):
                    picked.append(sticky_legacy[i])
            except (ValueError, IndexError):
                continue
        else:
            picked.append(p)
    return picked


def _date_group_key(kind, plan):
    if kind == "extended":
        start, end = _plan_date_window(kind, plan)
        return (
            start.isoformat() if start else "",
            end.isoformat() if end else "",
        )
    return (plan.get("start_date") or "", plan.get("end_date") or "")


def _plan_sort_start(plan, kind):
    """Earliest start date for sorting (closest holiday first). Missing dates sort last."""
    no_date = "9999-12-31"
    if not plan:
        return no_date
    if kind == "extended":
        ts = plan.get("trip_start")
        if ts:
            return str(ts)[:10]
        legs = plan.get("legs") or []
        dates = []
        for leg in legs:
            for k in ("start_date", "end_date"):
                if leg.get(k):
                    dates.append(str(leg[k])[:10])
        if dates:
            return min(dates)
        return no_date
    sd = plan.get("start_date")
    if sd:
        return str(sd)[:10]
    return no_date


def _parse_iso_date(value):
    """Parse a stored ISO date string and return ``None`` when it is blank or invalid."""
    if not value:
        return None
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _plan_date_window(kind, plan):
    """Return the visible trip date window used for home-page upcoming filtering."""
    if kind == "extended":
        start = _parse_iso_date(plan.get("trip_start"))
        end = _parse_iso_date(plan.get("trip_end"))
        if start or end:
            return start or end, end or start
        leg_dates = []
        for leg in plan.get("legs") or []:
            for key in ("start_date", "end_date"):
                parsed = _parse_iso_date(leg.get(key))
                if parsed:
                    leg_dates.append(parsed)
        if leg_dates:
            return min(leg_dates), max(leg_dates)
        return None, None
    start = _parse_iso_date(plan.get("start_date"))
    end = _parse_iso_date(plan.get("end_date")) or start
    return start, end


def _is_home_upcoming_trip(kind, plan, today, window_end):
    """True when a trip overlaps the home-page 12-month upcoming window."""
    start, end = _plan_date_window(kind, plan)
    if not start and not end:
        return False
    start = start or end
    end = end or start
    return start <= window_end and end >= today


HOLIDAY_LABEL_SHORT = {
    "day_trip": "Day trip",
    "weekend": "Weekend",
    "long_weekend": "Long weekend",
    "extended": "Extended trip",
}


def _destination_list_label(kind, p):
    """Destination + dates for Plan a Holiday (no holiday type prefix)."""
    title = p.get("title") or _default_title(kind)
    sd, ed = _date_group_key(kind, p)
    if sd or ed:
        dr = f"{_fmt_dmy_py(sd) if sd else '…'} → {_fmt_dmy_py(ed) if ed else '…'}"
    else:
        dr = "dates open"
    return f"{title} — {dr}"


def _group_plans_for_glance(kind, plans):
    """Subgroup when several trips share the same date window."""
    bucket = defaultdict(list)
    for p in plans:
        bucket[_date_group_key(kind, p)].append(p)
    groups = []
    for (sd, ed), plist in bucket.items():
        if sd or ed:
            label = f"{_fmt_dmy_py(sd) if sd else '…'} → {_fmt_dmy_py(ed) if ed else '…'}"
        else:
            label = "Dates not set"
        groups.append(
            {
                "label": label,
                "trips": plist,
                "multiple": len(plist) > 1,
            }
        )
    groups.sort(key=lambda g: _plan_sort_start(g["trips"][0], kind) if g["trips"] else "9999-12-31")
    return groups


def _all_glance_groups_sorted(today=None, window_days=365):
    """All glance subgroups from all holiday types, in date order (soonest first)."""
    today = today or datetime.now().date()
    window_end = today + timedelta(days=window_days)
    all_groups = []
    for kind in TRIP_KINDS:
        plans = [
            plan
            for plan in _get_plans(kind)
            if _is_home_upcoming_trip(kind, plan, today, window_end)
        ]
        for g in _group_plans_for_glance(kind, plans):
            if not g["trips"]:
                continue
            sk = min(_plan_sort_start(p, kind) for p in g["trips"])
            all_groups.append({"kind": kind, "group": g, "sort_key": sk})
    all_groups.sort(key=lambda x: (x["sort_key"], x["kind"]))
    return all_groups


def _unique_destination_titles_for_new_plans():
    """Distinct destination names from saved plans (ignore generic default titles)."""
    seen = set()
    out = []
    for kind in TRIP_KINDS:
        for p in _get_plans(kind):
            t = (p.get("title") or "").strip()
            if not t or t == _default_title(kind):
                continue
            key = t.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(t)
    out.sort(key=lambda s: s.lower())
    return out


def _plans_payload_for_holiday_json():
    """Saved plans for Holiday Details with metadata for filtering."""
    rows = []
    for kind in TRIP_KINDS:
        for p in _get_plans(kind):
            base = _destination_list_label(kind, p)
            start, end = _plan_date_window(kind, p)
            rows.append(
                {
                    "id": p.get("id"),
                    "kind": kind,
                    "title": p.get("title") or _default_title(kind),
                    "plan_category": p.get("plan_category") or "",
                    "holiday_types": p.get("holiday_types") or [],
                    "travelers": p.get("travelers") or [],
                    "who": describe_households(p),
                    "accommodation": p.get("accommodation") or [],
                    "accommodation_places": p.get("accommodation_places") or "",
                    "booking_import_text": p.get("booking_import_text") or "",
                    "booking_items": p.get("booking_items") or [],
                    "document_items": p.get("document_items") or [],
                    "start_date": start.isoformat() if start else "",
                    "end_date": end.isoformat() if end else "",
                    "_base": base,
                    "_sort": _plan_sort_start(p, kind),
                }
            )
    rows.sort(key=lambda r: (r["_sort"], r["kind"], r["_base"]))
    _label_holiday_rows(rows)
    return {
        "all_trips": rows,
        "destination_names": _unique_destination_titles_for_new_plans(),
    }


def _label_holiday_rows(rows):
    """Disambiguate Holiday Details labels when names and dates match."""
    counts = Counter(row["_base"] for row in rows)
    for row in rows:
        label = row["_base"]
        if counts[label] > 1:
            label = f"{label} · {HOLIDAY_LABEL_SHORT[row['kind']]}"
        row["label"] = label
    label_counts = Counter(row["label"] for row in rows)
    for row in rows:
        if label_counts[row["label"]] > 1:
            row["label"] = f"{row['label']} · {row['who'] or row['id']}"
        del row["_base"], row["_sort"], row["who"]


def _all_plans_by_kind():
    """Return all saved plans grouped by legacy trip kind."""
    return {kind: _get_plans(kind) for kind in TRIP_KINDS}


def _parse_important_links():
    """Parse helpful booking/document links from the smart workspace form."""
    labels = request.form.getlist("link_label")
    urls = request.form.getlist("link_url")
    rows = []
    for i in range(max(len(labels), len(urls), 0)):
        label = labels[i].strip() if i < len(labels) else ""
        url = urls[i].strip() if i < len(urls) else ""
        if label or url:
            rows.append({"label": label, "url": url})
    return rows


def _workspace_date_label(kind, plan):
    """Short human date label for a workspace header."""
    sd, ed = _date_group_key(kind, plan)
    if sd or ed:
        return f"{_fmt_dmy_py(sd) if sd else '…'} → {_fmt_dmy_py(ed) if ed else '…'}"
    return "Dates open"


def _workspace_planning_span(kind, plan):
    """Date list used by the smart workspace daily planner."""
    return _calendar_dates_for_plan(kind, plan)


def _compact_timeline_rows(plan, kind):
    """Return key trip details as compact rows sorted by date and time."""
    rows = []
    used_leg_keys = _add_timeline_booking_rows(rows, plan)
    _add_timeline_stay_rows(rows, plan, kind, used_leg_keys)
    _add_timeline_planner_rows(rows, plan)
    rows = _dedupe_timeline_rows(rows)
    rows.sort(key=lambda row: (row["sort_date"], row["sort_time"], row["category"], row["title"]))
    for row in rows:
        del row["sort_date"], row["sort_time"]
    return rows


def _compact_timeline_days(plan, kind):
    """Group compact timeline rows into expandable days."""
    days = []
    for row in _compact_timeline_rows(plan, kind):
        if not days or days[-1]["date"] != row["date"]:
            days.append({"date": row["date"], "title": row["title"], "rows": []})
        days[-1]["rows"].append(row)
    for day in days:
        day["title"] = _timeline_day_title(day["rows"])
    return days


def _timeline_day_title(rows):
    """Prefer a named event, then a daily activity, for a day's heading."""
    generic = {"Activity", "Stay", "Accommodation", "Caravan stand", "Flight"}
    named_event = next((row for row in rows if row["category"] not in generic), None)
    if named_event:
        return named_event["title"]
    activity = next((row for row in rows if row["category"] == "Activity"), None)
    if activity:
        return activity["title"]
    return rows[0]["title"] if rows else "Planned day"


def _workspace_booking_rows(plan, kind):
    """Include stay legs in Bookings when no imported booking exists for them."""
    rows = [dict(booking) for booking in (plan.get("booking_items") or [])]
    if kind != "extended":
        return rows
    used_leg_keys = {
        _leg_key(leg)
        for booking in rows
        if (leg := _matching_leg_for_booking(booking, plan.get("legs") or []))
    }
    for leg in plan.get("legs") or []:
        if not leg.get("destination") or _leg_key(leg) in used_leg_keys:
            continue
        rows.append(
            {
                "category": "Accommodation",
                "name": leg.get("destination") or "",
                "date": leg.get("start_date") or "",
                "end_date": leg.get("end_date") or "",
            }
        )
    return rows


def _missing_booking_categories(plan):
    """Return selected travel types that still have no booking details."""
    bookings = plan.get("booking_items") or []
    missing = []
    transport = plan.get("transport_overall") or plan.get("transport") or []
    if "Flights" in transport and not any(row.get("category") == "Flight" for row in bookings):
        missing.append("Flight")
    return missing


def _dedupe_timeline_rows(rows):
    """Drop stay lines that repeat a hotel check-in, and activity lines that repeat a stay."""
    stay_bits = []
    for row in rows:
        if row["category"] in {"Accommodation", "Stay", "Caravan stand"}:
            stay_bits.append(str(row["title"] or "").lower())
    kept = []
    seen = set()
    seen_activities = set()
    for row in rows:
        title = str(row["title"] or "").strip()
        lower = title.lower()
        key = (row.get("date") or "", lower, row.get("category") or "")
        if key in seen:
            continue
        if row["category"] == "Stay" and any(
            _stay_titles_match(lower, bit) and _timeline_is_check_event(bit) for bit in stay_bits
        ):
            continue
        activity_key = (row.get("date") or "", lower)
        if row["category"] == "Activity" and (
            activity_key in seen_activities
            or any(_stay_titles_match(lower, bit) for bit in stay_bits)
        ):
            continue
        if row["category"] == "Activity":
            seen_activities.add(activity_key)
        seen.add(key)
        kept.append(row)
    return kept


def _timeline_is_check_event(text):
    return bool(re.search(r"\bcheck[\s-]?in\b|\bcheck[\s-]?out\b|\bcheckout\b", text or "", re.I))


def _stay_titles_match(left, right):
    """True when two stay labels are the same place, ignoring the check-in prefix."""

    def norm(value):
        value = re.sub(
            r"^(check[\s-]?in|check[\s-]?out|checkout)\s*:\s*", "", value or "", flags=re.I
        )
        return re.sub(r"\s+", " ", value).strip()

    a, b = norm(left), norm(right)
    if not a or not b:
        return False
    return a == b or a in b or b in a


def _add_timeline_stay_rows(rows, plan, kind, used_leg_keys):
    """Add hotel/stay rows from extended legs or the named accommodation field."""
    if kind == "extended":
        for leg in plan.get("legs") or []:
            destination = (leg.get("destination") or "").strip()
            leg_key = _leg_key(leg)
            if not destination or leg_key in used_leg_keys:
                continue
            rows.append(
                _timeline_row(
                    date=leg.get("start_date") or "",
                    end_date=leg.get("end_date") or "",
                    time="",
                    category="Stay",
                    title=destination,
                    comments="",
                )
            )
        return
    places = (plan.get("accommodation_places") or "").strip()
    if places:
        rows.append(
            _timeline_row(
                date=plan.get("start_date") or "",
                end_date=plan.get("end_date") or "",
                time="",
                category="Stay",
                title=places,
                comments="",
            )
        )


def _add_timeline_booking_rows(rows, plan):
    """Add imported bookings such as hotels, flights, shows, and websites."""
    used_leg_keys = set()
    for booking in plan.get("booking_items") or []:
        title = (booking.get("name") or "").strip()
        matching_leg = _matching_leg_for_booking(booking, plan.get("legs") or [])
        if matching_leg:
            used_leg_keys.add(_leg_key(matching_leg))
        has_details = any(booking.get(key) for key in ("address", "reference", "website", "notes"))
        if title or has_details:
            end_date = booking.get("end_date") or (
                matching_leg.get("end_date") if matching_leg else ""
            )
            if booking.get("category") in {"Accommodation", "Caravan stand"} and end_date:
                _add_stay_checkin_checkout_rows(rows, booking, matching_leg, title)
                continue
            rows.append(
                _timeline_row(
                    date=booking.get("date")
                    or (matching_leg.get("start_date") if matching_leg else ""),
                    end_date="",
                    time=booking.get("time") or "",
                    category=booking.get("category") or "Booking",
                    title=title or "Booking",
                    comments=_booking_comments(booking),
                    address=booking.get("address") or "",
                    website=booking.get("website") or "",
                    reference=booking.get("reference") or "",
                    phone=_phone_from_text(booking.get("notes") or ""),
                )
            )
    return used_leg_keys


def _add_stay_checkin_checkout_rows(rows, booking, matching_leg, title):
    """Show one stay as check-in and check-out events on the right days."""
    start_date = booking.get("date") or (matching_leg.get("start_date") if matching_leg else "")
    end_date = booking.get("end_date") or (matching_leg.get("end_date") if matching_leg else "")
    comments = _booking_comments(booking)
    shared = {
        "category": booking.get("category") or "Accommodation",
        "address": booking.get("address") or "",
        "website": booking.get("website") or "",
        "reference": booking.get("reference") or "",
        "phone": _phone_from_text(booking.get("notes") or ""),
    }
    if start_date:
        rows.append(
            _timeline_row(
                date=start_date,
                end_date="",
                time=booking.get("time") or "",
                title=f"Check-in: {title or 'Stay'}",
                comments=comments,
                **shared,
            )
        )
    if end_date and end_date != start_date:
        rows.append(
            _timeline_row(
                date=end_date,
                end_date="",
                time=booking.get("checkout_time") or "",
                title=f"Check-out: {title or 'Stay'}",
                comments="Check out",
                **shared,
            )
        )


def _add_timeline_planner_rows(rows, plan):
    """Add one activity row per daily-planner line."""
    planner_days = plan.get("planner_days") or {}
    if not isinstance(planner_days, dict):
        return
    for date_key, text in planner_days.items():
        for line in str(text or "").splitlines():
            activity = line.strip().lstrip("-* ").strip()
            if activity:
                rows.append(
                    _timeline_row(
                        date=str(date_key),
                        end_date="",
                        time=_time_from_activity(activity),
                        category="Activity",
                        title=activity,
                        comments="",
                    )
                )


def _timeline_row(
    date,
    time,
    category,
    title,
    comments,
    end_date="",
    address="",
    website="",
    reference="",
    phone="",
):
    """Build one compact trip timeline row."""
    return {
        "date": date,
        "end_date": end_date,
        "date_label": _date_range_label(date, end_date),
        "time": time,
        "category": category,
        "title": title,
        "comments": comments,
        "address": address,
        "website": website,
        "reference": reference,
        "phone": phone,
        "has_details": any([address, website, reference, phone]),
        "sort_date": date or "9999-12-31",
        "sort_time": time or "99:99",
    }


def _leg_key(leg):
    """Stable key for matching imported accommodation bookings to stay legs."""
    return "|".join(
        [
            str(leg.get("destination") or "").strip().lower(),
            str(leg.get("start_date") or ""),
            str(leg.get("end_date") or ""),
        ]
    )


def _matching_leg_for_booking(booking, legs):
    """Find a stay leg that appears to describe the same accommodation booking."""
    booking_date = booking.get("date") or ""
    booking_name = str(booking.get("name") or "").lower()
    for leg in legs:
        if booking_date and booking_date != (leg.get("start_date") or ""):
            continue
        destination = str(leg.get("destination") or "").lower()
        if not booking_name or not destination:
            continue
        if any(word and word in destination for word in re.split(r"\W+", booking_name)):
            return leg
    return None


def _booking_comments(booking):
    """Short inline comment for compact timeline rows."""
    parts = []
    if booking.get("category") == "Flight" and booking.get("checkout_time"):
        parts.append(f"Scheduled arrival: {booking['checkout_time']}")
    notes = str(booking.get("notes") or "").strip()
    if notes:
        parts.append(notes)
    return " · ".join(parts)


def _phone_from_text(text):
    """Extract the first likely phone number from booking notes."""
    match = re.search(r"(?:\+?\d[\d\s().-]{7,}\d)", str(text or ""))
    return match.group(0).strip() if match else ""


def _date_range_label(start, end):
    """Human date range for compact trip rows."""
    if start and end and start != end:
        return f"{_fmt_dmy_py(start)} → {_fmt_dmy_py(end)}"
    if start:
        return _fmt_dmy_py(start)
    if end:
        return _fmt_dmy_py(end)
    return ""


def _time_from_activity(text):
    """Extract a leading HH:MM time from a planner activity line if present."""
    match = re.search(r"\b([01]?\d|2[0-3]):([0-5]\d)\b", text)
    if not match:
        return ""
    return f"{match.group(1).zfill(2)}:{match.group(2)}"


def _extract_pdf_text(upload) -> str:
    """Extract text from an uploaded PDF file."""
    reader = PdfReader(io.BytesIO(upload.read()))
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        if text.strip():
            pages.append(text)
    return "\n".join(pages).strip()


def _extract_document_text(upload) -> str:
    """Extract text from a supported uploaded travel document."""
    filename = str(upload.filename or "").lower()
    if filename.endswith(".pdf"):
        return _extract_pdf_text(upload)
    if filename.endswith((".txt", ".csv")):
        return upload.read().decode("utf-8", errors="ignore").strip()
    if filename.endswith(".eml"):
        return _extract_email_text(upload)
    if filename.endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")):
        return _extract_image_text(upload)
    return ""


def _extract_email_text(upload) -> str:
    """Extract useful text from an uploaded ``.eml`` email file."""
    message = BytesParser(policy=policy.default).parsebytes(upload.read())
    parts = [
        f"Subject: {message.get('subject', '')}",
        f"From: {message.get('from', '')}",
        f"To: {message.get('to', '')}",
        f"Date: {message.get('date', '')}",
        "",
        _email_body_text(message),
    ]
    return "\n".join(part for part in parts if str(part).strip()).strip()


def _email_body_text(message) -> str:
    """Return plain email body text, falling back to stripped HTML."""
    if message.is_multipart():
        plain_parts = []
        html_parts = []
        for part in message.walk():
            content_type = part.get_content_type()
            if content_type == "text/plain":
                plain_parts.append(str(part.get_content()))
            elif content_type == "text/html":
                html_parts.append(str(part.get_content()))
        if plain_parts:
            return "\n".join(plain_parts)
        return _strip_html("\n".join(html_parts))
    if message.get_content_type() == "text/html":
        return _strip_html(str(message.get_content()))
    return str(message.get_content())


def _strip_html(raw_html: str) -> str:
    """Convert simple email HTML into readable text."""
    without_tags = re.sub(r"<br\s*/?>", "\n", raw_html, flags=re.IGNORECASE)
    without_tags = re.sub(r"</p\s*>", "\n", without_tags, flags=re.IGNORECASE)
    without_tags = re.sub(r"<[^>]+>", " ", without_tags)
    return re.sub(r"\s+", " ", without_tags).strip()


def _extract_image_text(upload) -> str:
    """Extract text from an uploaded image."""
    return image_text(upload.read())


def _import_itinerary_text(plan, raw_text, filename, note):
    """Merge extracted itinerary text into booking, document, and planner fields."""
    if raw_text:
        existing = plan.get("booking_import_text") or ""
        plan["booking_import_text"] = (existing + "\n\n" + raw_text).strip()
    extracted = _rows_from_itinerary_text(raw_text, plan)
    _merge_booking_items(plan, extracted["bookings"])
    filled = apply_missing_booking_details(plan, raw_text, filename)
    _merge_planner_activities(plan, extracted["activities"])
    _apply_extracted_tab_details(plan, raw_text, extracted)
    _cleanup_workspace_lists(plan)
    _apply_budget_estimates(plan)
    _refresh_extraction_flags(plan)
    scanned_note = _scan_note(raw_text, filled)
    imported_document = _record_imported_document(plan, filename, note, scanned_note)
    message = " ".join(filled) if filled else scanned_note
    return {
        "bookings": len(extracted["bookings"]),
        "activities": len(extracted["activities"]),
        "document": 1,
        "imported_document": imported_document,
        "message": message,
    }


def _scan_note(raw_text, filled):
    """Short document note describing what the scan did."""
    if filled:
        return "Scanned. " + " ".join(filled)
    if raw_text:
        return "Scanned into the trip. No new booking number was found."
    return (
        "Uploaded. No text could be read from this file. "
        "Add it again if it is a photo of a booking."
    )


def _record_imported_document(plan, filename, note, scanned_note):
    """Store the upload once, updating the same file name on a later scan."""
    imported_document = {
        "label": note or filename or "Imported itinerary",
        "location": filename or "",
        "notes": scanned_note,
        "source": "upload",
    }
    documents = plan.setdefault("document_items", [])
    for item in documents:
        if item.get("source") == "upload" and item.get("location") == filename and filename:
            item.update(imported_document)
            return item
    documents.append(imported_document)
    return imported_document


def _merge_booking_items(plan, new_bookings):
    """Add extracted bookings without email-header noise or duplicates."""
    booking_items = plan.setdefault("booking_items", [])
    cleaned = [booking for booking in booking_items if not _is_noise_booking(booking)]
    stay_map = {
        _stay_key(booking): booking
        for booking in cleaned
        if booking.get("category") in {"Accommodation", "Caravan stand"}
    }
    existing = {
        _booking_key(booking)
        for booking in cleaned
        if booking.get("category") not in {"Accommodation", "Caravan stand"}
    }
    for booking in new_bookings:
        if _is_noise_booking(booking):
            continue
        if booking.get("category") in {"Accommodation", "Caravan stand"}:
            key = _stay_key(booking)
            if key in stay_map:
                _merge_stay_details(stay_map[key], booking)
                continue
            cleaned.append(booking)
            stay_map[key] = booking
            continue
        key = _booking_key(booking)
        if key in existing:
            continue
        cleaned.append(booking)
        existing.add(key)
    plan["booking_items"] = cleaned


def _stay_key(booking):
    """Stable key so each accommodation stay appears once."""
    name = str(booking.get("name") or "").lower()
    name = re.sub(r"\b(please take me to|hotel|resort|the|at|on|booking|reservation)\b", " ", name)
    name = re.sub(r"[^a-z0-9]+", " ", name)
    if "intercontinental" in name and ("hongqiao" in name or "necc" in name):
        return "intercontinental-shanghai-hongqiao-necc"
    if "fairmont" in name and ("bund" in name or "peace" in name):
        return "fairmont-peace-hotel-bund"
    return re.sub(r"\s+", " ", name).strip()[:80]


def _merge_stay_details(target, incoming):
    """Merge repeated accommodation details into one stay row."""
    if incoming.get("date"):
        dates = [d for d in [target.get("date"), incoming.get("date")] if d]
        target["date"] = min(dates) if dates else incoming.get("date", "")
    if incoming.get("end_date"):
        dates = [d for d in [target.get("end_date"), incoming.get("end_date")] if d]
        target["end_date"] = max(dates) if dates else incoming.get("end_date", "")
    for key in ("website", "reference", "address", "time", "checkout_time"):
        if not target.get(key) and incoming.get(key):
            target[key] = incoming[key]
    if incoming.get("notes") and incoming["notes"] not in str(target.get("notes") or ""):
        target["notes"] = (str(target.get("notes") or "") + "\n" + incoming["notes"]).strip()


def _booking_key(booking):
    """Stable key for imported booking dedupe."""
    name = re.sub(r"\s+", " ", str(booking.get("name") or "").lower()).strip()
    name = re.sub(r"\b(hotel|resort|the|at|on)\b", "", name).strip()
    return (
        str(booking.get("category") or "").lower(),
        name,
        str(booking.get("date") or ""),
        str(booking.get("reference") or "").lower(),
    )


def _is_noise_booking(booking):
    """True when an extracted row is email metadata or narrative text."""
    name = str(booking.get("name") or "").strip()
    lower = name.lower()
    is_header = bool(re.match(r"^(from|to|subject|date|dear|hello|you have received)\b", lower))
    if not name or is_header or ("<" in name and ">" in name):
        return True
    if booking.get("category") == "Flight":
        return not bool(re.search(r"\b[A-Z]{2}\s?\d{2,4}\b", name))
    if booking.get("category") in {"Accommodation", "Caravan stand"}:
        max_name_words = 10
        if len(name.split()) > max_name_words:
            return True
        if lower in {"hotel", "intercontinental hotels & resorts"}:
            return True
        narrative = (
            r"\b(please take me|luggage|airport check-in|every sailing|"
            r"ten-minute|booking that makes)\b"
        )
        return bool(re.search(narrative, lower))
    return False


def _apply_extracted_tab_details(plan, raw_text, extracted):
    """Populate workspace tabs with useful details found in imported text."""
    text = str(raw_text or "")
    _append_unique_links(plan, _links_from_text(text))
    _append_unique_documents(plan, _documents_from_text(text))
    _append_unique_tasks(plan, _tasks_from_text(text, plan, extracted))
    _append_unique_packing(plan, _packing_from_text(text, plan))
    _append_budget_hints(plan, text)


def _append_unique_links(plan, links):
    """Add imported web links once."""
    existing = {
        str(link.get("url") or "").strip().lower()
        for link in plan.setdefault("important_links", [])
    }
    for link in links:
        url = link["url"].strip()
        if url.lower() in existing:
            continue
        plan["important_links"].append(link)
        existing.add(url.lower())


def _links_from_text(text):
    """Return website links found in imported document text."""
    links = []
    for url in re.findall(r"https?://[^\s)]+", text):
        links.append({"label": "Imported link", "url": url.rstrip(".,")})
    return links


def _append_unique_documents(plan, documents):
    """Add important document reminders once."""
    existing = {
        str(item.get("label") or "").strip().lower()
        for item in plan.setdefault("document_items", [])
    }
    for document in documents:
        key = document["label"].lower()
        if key in existing:
            continue
        plan["document_items"].append(document)
        existing.add(key)


def _documents_from_text(text):
    """Create document tab rows from important document keywords."""
    lower = text.lower()
    documents = []
    if "passport" in lower:
        documents.append(
            {
                "label": "Passport",
                "location": "Check expiry",
                "notes": "Required for overseas travel.",
            }
        )
    if "visa" in lower:
        documents.append(
            {"label": "Visa", "location": "Confirm status", "notes": "Verify entry rules."}
        )
    if "insurance" in lower:
        documents.append(
            {
                "label": "Travel insurance",
                "location": "Policy email",
                "notes": "Check emergency number.",
            }
        )
    if re.search(r"\b(ticket|boarding pass)\b", lower):
        documents.append(
            {"label": "Tickets", "location": "Email / app", "notes": "Save offline copies."}
        )
    return documents


def _append_unique_tasks(plan, tasks):
    """Add extracted tasks once."""
    existing = {
        str(task.get("text") or "").strip().lower() for task in plan.setdefault("task_items", [])
    }
    for task_text in tasks:
        key = task_text.lower()
        if key in existing:
            continue
        plan["task_items"].append({"owner": "", "text": task_text, "due": "", "status": "To do"})
        existing.add(key)


def _tasks_from_text(text, plan, extracted):
    """Build practical Family Tasks from imported itinerary details."""
    lower = text.lower()
    tasks = ["Confirm bookings"]
    if "flight" in lower or extracted["bookings"]:
        tasks.extend(["Boarding pass", "Airport transfer"])
    if "hotel" in lower or "check-in" in lower:
        tasks.extend(["Check-in time", "Confirm hotel"])
    if "passport" in lower or plan.get("plan_category") == "Holiday overseas":
        tasks.extend(["Passport", "ID cards"])
    if "visa" in lower:
        tasks.append("Check visas")
    if "insurance" in lower:
        tasks.append("Insurance")
    if "restaurant" in lower or "dinner" in lower:
        tasks.append("Dinner booking")
    return tasks


def _append_unique_packing(plan, packing_items):
    """Add imported packing reminders once."""
    existing = {
        str(item.get("text") if isinstance(item, dict) else item).strip().lower()
        for item in plan.setdefault("packing_items", [])
    }
    for text in packing_items:
        key = text.lower()
        if key in existing:
            continue
        plan["packing_items"].append({"text": text, "packed": False, "source": "document"})
        existing.add(key)


def _packing_from_text(text, plan):
    """Build packing reminders from trip context and imported text."""
    lower = text.lower()
    items = ["Phone charger", "Medication"]
    if "passport" in lower or plan.get("plan_category") == "Holiday overseas":
        items.extend(["Passport", "Power adaptor"])
    if "swim" in lower or "beach" in lower:
        items.append("Swimwear")
    if "walk" in lower or "tour" in lower:
        items.append("Walking shoes")
    if "ticket" in lower or "boarding pass" in lower:
        items.append("Tickets")
    return items


def _append_budget_hints(plan, text):
    """Add obvious imported money amounts as budget review hints."""
    amounts = re.findall(r"(?:AUD|USD|CNY|RMB|\$)\s?([0-9][0-9,]*(?:\.\d{2})?)", text)
    if not amounts:
        return
    plan.setdefault("budget_items", [])
    existing = {str(item.get("description") or "").strip().lower() for item in plan["budget_items"]}
    for amount in amounts[:5]:
        description = "Imported cost"
        if description.lower() in existing:
            continue
        plan["budget_items"].append(
            {
                "category": "Imported",
                "description": description,
                "amount": amount.replace(",", ""),
                "paid": "No",
            }
        )
        existing.add(description.lower())


def _apply_budget_estimates(plan):
    """Add practical estimate rows when imports do not include actual prices."""
    plan.setdefault("budget_items", [])
    existing = {
        str(item.get("description") or "").strip().lower()
        for item in plan["budget_items"]
        if _row_has_content(item)
    }
    for row in _budget_estimate_rows(plan):
        key = row["description"].lower()
        if key in existing:
            continue
        plan["budget_items"].append(row)
        existing.add(key)


def _budget_estimate_rows(plan):
    """Build estimated budget rows from dates, stays, flights, and activities."""
    rows = []
    for booking in plan.get("booking_items") or []:
        if booking.get("category") not in {"Accommodation", "Caravan stand"}:
            continue
        nights = _booking_nights(booking)
        if nights <= 0:
            continue
        rate = _estimated_nightly_rate(booking)
        night_label = "night" if nights == 1 else "nights"
        rows.append(
            {
                "category": "Accommodation",
                "description": f"{booking.get('name') or 'Stay'} ({nights} {night_label} estimate)",
                "amount": f"{nights * rate:.2f}",
                "paid": "No",
                "source": "estimate",
            }
        )
    days = _trip_day_count(plan)
    if days:
        rows.append(
            {
                "category": "Food",
                "description": f"Meals ({days} days estimate)",
                "amount": f"{days * 100:.2f}",
                "paid": "No",
                "source": "estimate",
            }
        )
        rows.append(
            {
                "category": "Transport",
                "description": "Local transport estimate",
                "amount": f"{max(200, days * 45):.2f}",
                "paid": "No",
                "source": "estimate",
            }
        )
    activity_count = _planned_activity_count(plan)
    if activity_count:
        rows.append(
            {
                "category": "Activities",
                "description": "Activities estimate",
                "amount": f"{max(150, activity_count * 60):.2f}",
                "paid": "No",
                "source": "estimate",
            }
        )
    if plan.get("plan_category") == "Holiday overseas":
        rows.extend(
            [
                {
                    "category": "Documents",
                    "description": "Travel insurance estimate",
                    "amount": "180.00",
                    "paid": "No",
                    "source": "estimate",
                },
                {
                    "category": "Documents",
                    "description": "Visa / entry checks estimate",
                    "amount": "120.00",
                    "paid": "No",
                    "source": "estimate",
                },
            ]
        )
    if any(booking.get("category") == "Flight" for booking in plan.get("booking_items") or []):
        rows.append(
            {
                "category": "Flights",
                "description": "Flight fares - enter actual cost",
                "amount": "",
                "paid": "No",
                "source": "estimate",
            }
        )
    return rows


def _booking_nights(booking):
    """Return number of nights from check-in/check-out dates."""
    start = _parse_iso_date(booking.get("date"))
    end = _parse_iso_date(booking.get("end_date"))
    if not start or not end or end <= start:
        return 1 if start else 0
    return (end - start).days


def _estimated_nightly_rate(booking):
    """Simple nightly estimate in AUD when no imported price is available."""
    name = str(booking.get("name") or "").lower()
    if "fairmont" in name:
        return 450
    if "intercontinental" in name:
        return 280
    if booking.get("category") == "Caravan stand":
        return 80
    return 220


def _trip_day_count(plan):
    """Inclusive day count for meal/local transport estimates."""
    start, end = _generic_plan_date_window(plan)
    if not start or not end:
        return 0
    return max(1, (end - start).days + 1)


def _planned_activity_count(plan):
    """Count planned non-travel activities."""
    count = 0
    for text in (plan.get("planner_days") or {}).values():
        count += sum(1 for line in str(text).splitlines() if line.strip())
    return count


def _refresh_extraction_flags(plan):
    """Flag missing important details after document extraction."""
    flags = []
    for booking in plan.get("booking_items") or []:
        if _is_noise_booking(booking):
            continue
        missing = []
        if booking.get("category") in {"Accommodation", "Caravan stand"}:
            missing = _missing_accommodation_details(booking)
        elif booking.get("category") == "Flight":
            missing = _missing_flight_details(booking)
        if missing:
            booking["missing_info"] = ", ".join(missing)
            flags.append(
                f"{booking.get('name') or booking.get('category')}: missing {', '.join(missing)}."
            )
        else:
            booking.pop("missing_info", None)
    if plan.get("plan_category") == "Holiday overseas":
        _append_overseas_flags(plan, flags)
    plan["extraction_flags"] = flags[:8]


def _missing_accommodation_details(booking):
    """Important accommodation details not found in extracted text."""
    missing = []
    if not booking.get("address"):
        missing.append("address")
    if "phone:" not in str(booking.get("notes") or "").lower():
        missing.append("phone")
    if not booking.get("website"):
        missing.append("website")
    if not booking.get("reference"):
        missing.append("confirmation number")
    return missing


def _missing_flight_details(booking):
    """Important flight details not found in extracted text."""
    missing = []
    if not booking.get("date"):
        missing.append("date")
    if not booking.get("time"):
        missing.append("time")
    if not booking.get("reference"):
        missing.append("booking ref")
    if "terminal" not in str(booking.get("notes") or "").lower():
        missing.append("terminal")
    return missing


def _append_overseas_flags(plan, flags):
    """Add overseas travel warnings when critical documents are not recorded."""
    document_text = " ".join(
        str(item.get("label") or "") + " " + str(item.get("notes") or "")
        for item in plan.get("document_items") or []
    ).lower()
    for label, message in {
        "passport": "Passport details not confirmed.",
        "insurance": "Travel insurance details not confirmed.",
        "visa": "Visa/entry rules need checking online.",
    }.items():
        if label not in document_text:
            flags.append(message)


def _cleanup_workspace_lists(plan):
    """Remove duplicate/blank tab rows created by repeated imports."""
    _cleanup_task_items(plan)
    _cleanup_packing_items(plan)
    _cleanup_document_items(plan)
    plan["budget_items"] = [
        item for item in plan.get("budget_items") or [] if _row_has_content(item)
    ]


def _cleanup_task_items(plan):
    """Normalise short Family Tasks and remove duplicates."""
    aliases = {
        "bookings": "Confirm bookings",
        "contacts": "Save contacts",
        "ids": "ID cards",
        "visas": "Check visas",
        "emergency": "Emergency contacts",
        "travel insurance": "Insurance",
        "add apps to phone": "Phone apps",
        "add bank cards to apps": "Bank cards",
    }
    seen = set()
    cleaned = []
    for task in plan.get("task_items") or []:
        text = str(task.get("text") or "").strip()
        if not text:
            continue
        text = aliases.get(text.lower(), text)
        key = text.lower()
        if key in seen:
            continue
        row = dict(task)
        row["text"] = text
        cleaned.append(row)
        seen.add(key)
    plan["task_items"] = cleaned


def _cleanup_packing_items(plan):
    """Remove duplicate packing rows."""
    seen = set()
    cleaned = []
    for item in plan.get("packing_items") or []:
        text = str(item.get("text") if isinstance(item, dict) else item).strip()
        if not text or text.lower() in seen:
            continue
        cleaned.append(item if isinstance(item, dict) else {"text": text, "packed": False})
        seen.add(text.lower())
    plan["packing_items"] = cleaned


def _cleanup_document_items(plan):
    """Mark generated document reminders and remove duplicates."""
    suggestion_labels = {"passport", "visa", "travel insurance", "tickets"}
    seen = set()
    cleaned = []
    for item in plan.get("document_items") or []:
        label = str(item.get("label") or "").strip()
        location = str(item.get("location") or "").strip()
        if not label and not location:
            continue
        row = dict(item)
        if label.lower() in suggestion_labels and row.get("source") != "upload":
            row["source"] = "suggestion"
        key = (label.lower(), location.lower(), str(row.get("source") or "").lower())
        if key in seen:
            continue
        cleaned.append(row)
        seen.add(key)
    plan["document_items"] = cleaned


def _row_has_content(item):
    """True when a dynamic row contains useful user-facing content."""
    return any(
        str(value or "").strip()
        for key, value in dict(item).items()
        if key not in {"paid", "status", "source"}
    )


def _rows_from_itinerary_text(raw_text, plan):
    """Extract likely bookings and dated activities from itinerary text."""
    bookings = []
    activities = []
    current_date = ""
    trip_start, trip_end = _generic_plan_date_window(plan)
    for line in _useful_itinerary_lines(raw_text):
        line_date = _date_from_text(line)
        if line_date and _date_in_trip_window(line_date, trip_start, trip_end):
            current_date = line_date
        if _looks_like_accommodation(line):
            bookings.append(
                {
                    "category": "Accommodation",
                    "name": line,
                    "date": current_date,
                    "end_date": "",
                    "time": _time_from_activity(line),
                    "website": _first_url(line),
                    "reference": _reference_from_text(line),
                    "address": _address_from_text(line),
                    "notes": line,
                }
            )
            continue
        if _looks_like_flight(line):
            bookings.append(
                {
                    "category": "Flight",
                    "name": line,
                    "date": current_date,
                    "end_date": "",
                    "time": _time_from_activity(line),
                    "website": _first_url(line),
                    "reference": _reference_from_text(line),
                    "address": "",
                    "notes": line,
                }
            )
            continue
        if current_date and _looks_like_activity(line) and not _is_noise_activity(line):
            activities.append({"date": current_date, "text": line})
    return {"bookings": bookings[:30], "activities": activities[:80]}


def _date_in_trip_window(date_value, trip_start, trip_end):
    """Return true when an extracted date belongs to the selected trip."""
    parsed = _parse_iso_date(date_value)
    if not parsed:
        return False
    if trip_start and parsed < trip_start:
        return False
    return not (trip_end and parsed > trip_end)


def _generic_plan_date_window(plan):
    """Return a date window for either legacy or extended trip payloads."""
    start = _parse_iso_date(plan.get("trip_start") or plan.get("start_date"))
    end = _parse_iso_date(plan.get("trip_end") or plan.get("end_date")) or start
    if start or end:
        return start or end, end or start
    leg_dates = []
    for leg in plan.get("legs") or []:
        for key in ("start_date", "end_date"):
            parsed = _parse_iso_date(leg.get(key))
            if parsed:
                leg_dates.append(parsed)
    if leg_dates:
        return min(leg_dates), max(leg_dates)
    return None, None


def _useful_itinerary_lines(raw_text):
    """Return compact non-empty lines from extracted itinerary text."""
    lines = []
    for line in str(raw_text or "").splitlines():
        cleaned = re.sub(r"\s+", " ", line).strip()
        if len(cleaned) >= MIN_ITINERARY_LINE_LENGTH:
            lines.append(cleaned)
    return lines


def _date_from_text(text):
    """Parse common itinerary dates into ISO format."""
    iso = re.search(r"\b(\d{4})-(\d{2})-(\d{2})\b", text)
    if iso:
        return iso.group(0)
    numeric = re.search(r"\b(\d{1,2})[\/.-](\d{1,2})[\/.-](\d{2,4})\b", text)
    if numeric:
        year = numeric.group(3)
        if len(year) == SHORT_YEAR_LENGTH:
            year = "20" + year
        return f"{year}-{numeric.group(2).zfill(2)}-{numeric.group(1).zfill(2)}"
    named = re.search(
        r"\b(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(\d{2,4})\b",
        text,
        re.IGNORECASE,
    )
    if not named:
        return ""
    months = {
        "jan": "01",
        "feb": "02",
        "mar": "03",
        "apr": "04",
        "may": "05",
        "jun": "06",
        "jul": "07",
        "aug": "08",
        "sep": "09",
        "sept": "09",
        "oct": "10",
        "nov": "11",
        "dec": "12",
    }
    month_key = "sept" if named.group(2).lower().startswith("sept") else named.group(2)[:3].lower()
    year = named.group(3)
    if len(year) == SHORT_YEAR_LENGTH:
        year = "20" + year
    return f"{year}-{months[month_key]}-{named.group(1).zfill(2)}"


def _looks_like_accommodation(text):
    cleaned = text.strip()
    if len(cleaned) > MAX_ACCOMMODATION_LINE_LENGTH and not re.search(
        r"\b(check-?in|booking|reservation)\b", cleaned, re.IGNORECASE
    ):
        return False
    return bool(
        re.search(
            r"\b(fairmont|intercontinental|hilton|marriott|hyatt|sofitel|novotel)\b",
            cleaned,
            re.IGNORECASE,
        )
        or re.search(r"\b(hotel|resort|inn|suites?)\b$", cleaned, re.IGNORECASE)
        or re.search(r"\b(check-?in|accommodation booking|hotel booking)\b", cleaned, re.IGNORECASE)
    )


def _looks_like_flight(text):
    return bool(
        re.search(r"\b[A-Z]{2}\d{2,4}\b", text)
        or re.search(
            r"\b(airport|terminal|gate)\b.*\b(depart|departure|arrive|arrival)\b",
            text,
            re.IGNORECASE,
        )
    )


def _looks_like_activity(text):
    return bool(
        re.search(
            r"\b(tour|visit|show|museum|dinner|lunch|breakfast|transfer|walk|activity|robot|conference|event)\b",
            text,
            re.IGNORECASE,
        )
    )


def _is_noise_activity(text):
    """True for marketing, email footer, or cancellation-policy lines."""
    return bool(
        re.search(
            r"\b(customer care|book a tour|failing to show|charge equal|"
            r"reservation will result|unsubscribe)\b",
            text,
            re.IGNORECASE,
        )
    )


def _first_url(text):
    match = re.search(r"https?://[^\s)]+", text)
    return match.group(0) if match else ""


def _reference_from_text(text):
    match = re.search(
        r"\b(?:confirmation|reference|reservation|booking|pnr|ref)\s*(?:number|no|#|:)?\s*([A-Z0-9-]{4,})\b",
        text,
        re.IGNORECASE,
    )
    return match.group(1) if match else ""


def _address_from_text(text):
    return (
        text
        if re.search(
            r"\b(street|st\b|road|rd\b|avenue|ave\b|bund|centre|center|necc)\b", text, re.IGNORECASE
        )
        else ""
    )


def _merge_planner_activities(plan, activities):
    """Append extracted activities to daily planner notes."""
    planner_days = plan.setdefault("planner_days", {})
    for activity in activities:
        date_key = activity["date"]
        current = planner_days.get(date_key, "")
        line = f"- {activity['text']}"
        if line not in current:
            planner_days[date_key] = (current + "\n" + line).strip()


@app.template_filter("fmt_dmy")
def fmt_dmy_filter(date_str):
    """Format YYYY-MM-DD as '12 Dec 26'."""
    if not date_str:
        return ""
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return d.strftime("%d %b %y")
    except ValueError:
        return str(date_str)


@app.template_filter("fmt_weekday_dmy")
def fmt_weekday_dmy_filter(date_str):
    """Format YYYY-MM-DD as 'Wed, 12 Dec 26'."""
    if not date_str:
        return ""
    try:
        d = datetime.strptime(str(date_str)[:10], "%Y-%m-%d")
        return d.strftime("%a, %d %b %y")
    except ValueError:
        return str(date_str)


def _pair_key(transport, accommodation):
    return f"{transport}{PAIR_SEP}{accommodation}"


def _selected_list(form_key):
    return request.form.getlist(form_key)


def _daterange_inclusive(start_s, end_s):
    """Return list of ISO date strings from start to end inclusive."""
    if not start_s or not end_s:
        return []
    try:
        a = datetime.strptime(str(start_s)[:10], "%Y-%m-%d").date()
        b = datetime.strptime(str(end_s)[:10], "%Y-%m-%d").date()
    except ValueError:
        return []
    if b < a:
        a, b = b, a
    out = []
    cur = a
    while cur <= b:
        out.append(cur.isoformat())
        cur += timedelta(days=1)
    return out


def _calendar_dates_for_plan(trip_kind, plan):
    if not plan:
        return []
    if trip_kind in ("day_trip", "weekend", "long_weekend"):
        return _daterange_inclusive(plan.get("start_date"), plan.get("end_date"))
    if trip_kind == "extended":
        return _extended_calendar_dates(plan)
    return []


def _extended_calendar_dates(plan):
    """Return an extended trip date span from overall dates or leg dates."""
    trip_start, trip_end = plan.get("trip_start"), plan.get("trip_end")
    if trip_start and trip_end:
        return _daterange_inclusive(trip_start, trip_end)
    dates = _valid_leg_dates(plan.get("legs") or [])
    if not dates:
        return []
    return _daterange_inclusive(str(min(dates)), str(max(dates)))


def _valid_leg_dates(legs):
    """Extract parseable start/end dates from extended-trip legs."""
    dates = []
    for leg in legs:
        for key in ("start_date", "end_date"):
            if not leg.get(key):
                continue
            try:
                dates.append(datetime.strptime(leg[key][:10], "%Y-%m-%d").date())
            except ValueError:
                continue
    return dates


def _parse_planner_days_from_form():
    out = {}
    prefix = "planner_day_"
    for k in request.form:
        if k.startswith(prefix):
            date_key = k[len(prefix) :]
            out[date_key] = request.form.get(k, "")
    return out


def _accommodation_list_for_checklist(plan):
    acc = list(plan.get("accommodation") or [])
    if (plan.get("accommodation_places") or "").strip() and "Hotel" not in acc:
        acc.append("Hotel")
    return acc


def _get_checklist_pairs():
    direct = session.get("checklist_pairs")
    if isinstance(direct, dict) and direct:
        return dict(direct)
    merged = {}
    raw = session.get("checklist_matrix")
    if raw and isinstance(raw, dict):
        for hk in TRIP_KINDS:
            block = raw.get(hk) or {}
            for k, v in (block.get("pairs") or {}).items():
                if k not in merged and v is not None:
                    merged[k] = v
    if merged:
        session["checklist_pairs"] = merged
        session.modified = True
    return merged


def _checklist_pair_rows_for_plan(trip_kind, plan):
    """Editable rows: one per transport × accommodation pair ticked on this plan."""
    if not plan:
        return []
    acc_list = _accommodation_list_for_checklist(plan)
    if trip_kind == "extended":
        transport_list = plan.get("transport_overall") or []
    else:
        transport_list = plan.get("transport") or []
    if not transport_list or not acc_list:
        return []
    pairs_dict = _get_checklist_pairs()
    rows = []
    for t in transport_list:
        for acc in acc_list:
            key = _pair_key(t, acc)
            rows.append(
                {
                    "transport": t,
                    "accommodation": acc,
                    "content": _normalize_checklist_text(pairs_dict.get(key, "") or ""),
                }
            )
    return rows


def _split_checklist_auto_header(text):
    """Return the auto header and editable checklist body separately."""
    if not text:
        return "", ""
    lines = str(text).splitlines()
    marker = CHECKLIST_AUTO_MARKER.strip()
    if not lines or lines[0].strip() != marker:
        return "", str(text).strip()
    body_start = 1
    while body_start < len(lines) and lines[body_start].strip():
        body_start += 1
    if body_start < len(lines):
        body_start += 1
    header = "\n".join(lines[:body_start]).rstrip()
    body = "\n".join(lines[body_start:]).strip()
    return header, body


def _strip_checklist_auto_header(text):
    """Remove auto transport/accommodation block from saved checklist text."""
    _, body = _split_checklist_auto_header(text)
    return body


def _number_checklist_body(text):
    """Number each checklist item, avoiding duplicate numbering when re-saved."""
    items = []
    for line in str(text or "").splitlines():
        item = line.strip()
        if not item:
            continue
        item = re.sub(r"^(\d+[\.)]|[-*])\s*", "", item).strip()
        if item:
            items.append(item)
    return "\n".join(f"{i}. {item}" for i, item in enumerate(items, start=1))


def _normalize_checklist_text(text):
    """Keep the auto header, but make the checklist items numbered."""
    header, body = _split_checklist_auto_header(text)
    numbered = _number_checklist_body(body)
    if header and numbered:
        return f"{header}\n\n{numbered}"
    if header:
        return header
    return numbered


def _build_checklist_auto_header(plan, trip_kind):
    """Lines listing trip selections for this shared checklist."""
    if not plan:
        return ""
    if trip_kind == "extended":
        tlist = plan.get("transport_overall") or []
    else:
        tlist = plan.get("transport") or []
    acc_list = _accommodation_list_for_checklist(plan)
    holiday_types = plan.get("holiday_types") or []
    if not tlist or not acc_list:
        return ""
    lines = [
        CHECKLIST_AUTO_MARKER.rstrip(),
        "Transport: " + ", ".join(tlist),
        "Accommodation: " + ", ".join(acc_list),
    ]
    if holiday_types:
        lines.append("Activity Type: " + ", ".join(holiday_types))
    lines.append("")
    return "\n".join(lines)


def _sync_checklist_auto_headers(plan, trip_kind):
    """Merge selected transport and accommodation into shared checklist text."""
    header = _build_checklist_auto_header(plan, trip_kind)
    if not header:
        return
    if trip_kind == "extended":
        tlist = plan.get("transport_overall") or []
    else:
        tlist = plan.get("transport") or []
    acc_list = _accommodation_list_for_checklist(plan)
    pairs = _get_checklist_pairs()
    for t in tlist:
        for acc in acc_list:
            k = _pair_key(t, acc)
            text = pairs.get(k, "") or ""
            user = _number_checklist_body(_strip_checklist_auto_header(text))
            pairs[k] = header + user
    session["checklist_pairs"] = pairs
    session.modified = True


def _transport_list_for_form(plan):
    """Which transport checkboxes are on for weekend/long_weekend vs extended."""
    if not plan:
        return []
    return list(plan.get("transport_overall") or plan.get("transport") or [])


def _travelers_display(plan):
    if not plan:
        return ""
    names = []
    for v in plan.get("travelers") or []:
        names.append(TRAVELER_LABELS.get(v, v.replace("_", " ").title()))
    other = (plan.get("travelers_other") or "").strip()
    if other:
        names.append(other)
    if not names:
        return ""
    return ", ".join(names)


@app.template_filter("glance_travelers")
def glance_travelers_filter(plan):
    """Jinja: travellers string for a plan dict."""
    return _travelers_display(plan)


def _parse_extended_legs():
    destinations = request.form.getlist("leg_destination")
    starts = request.form.getlist("leg_start")
    ends = request.form.getlist("leg_end")
    transports = request.form.getlist("leg_transport")
    n = max(len(destinations), len(starts), len(ends), len(transports), 1)
    legs = []
    for i in range(n):
        dest = destinations[i].strip() if i < len(destinations) else ""
        sd = starts[i] if i < len(starts) else ""
        ed = ends[i] if i < len(ends) else ""
        mode = transports[i] if i < len(transports) else ""
        if dest or sd or ed or mode:
            legs.append(
                {
                    "destination": dest,
                    "start_date": sd,
                    "end_date": ed,
                    "transport": mode,
                }
            )
    return legs


def _trip_payload_common(trip_kind):
    """Shared fields for all trip POST bodies (transport added per route)."""
    new_todo = request.form.get("things_to_do_new", "").strip()
    picks = _resolve_things_to_do_picks(trip_kind)
    _merge_things_library_from_picks(trip_kind, picks, new_todo)
    return {
        "travelers": _selected_list("travelers"),
        "travelers_other": request.form.get("travelers_other", "").strip(),
        "holiday_types": [x for x in _selected_list("holiday_types") if x],
        "accommodation": _selected_list("accommodation"),
        "accommodation_places": request.form.get("accommodation_places", "").strip(),
        "transport_extra": _number_checklist_body(request.form.get("transport_extra", "")),
        "things_to_do_picks": picks,
        "notes": request.form.get("notes", ""),
        "planner_days": _parse_planner_days_from_form(),
    }


def _upcoming_trip_rows(today=None):
    """Every saved trip. Ones still ahead come first, then finished trips."""
    today = today or datetime.now().date()
    rows = []
    for kind in TRIP_KINDS:
        for plan in _get_plans(kind):
            _start, end = _plan_date_window(kind, plan)
            rows.append(
                {
                    "kind": kind,
                    "plan": plan,
                    "sort": _plan_sort_start(plan, kind),
                    "date_label": _workspace_date_label(kind, plan),
                    "households": households_for_plan(plan),
                    "finished": end is not None and end < today,
                }
            )
    rows.sort(
        key=lambda row: (row["finished"], row["sort"], row["kind"], row["plan"].get("title") or "")
    )
    attach_copy_targets(rows)
    return rows


@app.route("/")
def home():
    today = datetime.now().date()
    upcoming = _upcoming_trip_rows(today=today)
    return render_template(
        "index.html",
        mario_trips=trips_for_household_tab(upcoming, HOUSEHOLD_MARIO),
        reuben_trips=trips_for_household_tab(upcoming, HOUSEHOLD_REUBEN),
        trip_category_options=TRIP_CATEGORY_OPTIONS,
        trip_length_options=TRIP_LENGTH_OPTIONS,
        planner_profile_options=PLANNER_PROFILE_OPTIONS,
        going_person_options=GOING_PERSON_OPTIONS,
        stay_size_options=STAY_SIZE_OPTIONS,
        today_iso=today.isoformat(),
    )


_CALENDAR_SLUGS = {
    "mario-esme": (HOUSEHOLD_MARIO, "Mario & Esme"),
    "reuben-vanessa": (HOUSEHOLD_REUBEN, "Reuben & Vanessa"),
    "all": (None, "Strydom Travel Hub"),
}


@app.route("/calendar/<slug>.ics")
def household_calendar(slug):
    """iCalendar feed for Home Assistant. Trips stay in Travel Hub."""
    chosen = _CALENDAR_SLUGS.get(slug)
    if chosen is None:
        return "Unknown calendar", 404
    household, name = chosen
    body = trips_to_ics(calendar_rows(_all_plans_by_kind()), name, household)
    return Response(body, mimetype="text/calendar; charset=utf-8")


@app.route("/trip/<kind>/<trip_id>/household", methods=["POST"])
def set_trip_household(kind, trip_id):
    """Mark a trip for one household. Pressing the active household clears it."""
    if kind not in TRIP_KINDS:
        return redirect(url_for("home"))
    plan = _find_plan(kind, trip_id)
    choice = request.form.get("household", "").strip()
    if not plan or choice not in {HOUSEHOLD_MARIO, HOUSEHOLD_REUBEN}:
        return redirect(url_for("home"))
    assign_household(plan, choice)
    _replace_plan(kind, plan)
    return redirect(url_for("home"))


@app.route("/trip/<kind>/<trip_id>/copy-for-household", methods=["POST"])
def copy_trip_for_household(kind, trip_id):
    """Save a second copy of a trip for the other family, with the same name."""
    if kind not in TRIP_KINDS:
        return redirect(url_for("home"))
    plan = _find_plan(kind, trip_id)
    target = request.form.get("household", "").strip()
    if not plan or target not in {HOUSEHOLD_MARIO, HOUSEHOLD_REUBEN}:
        return redirect(url_for("home"))
    rows = _household_rows_for_kind(kind)
    source_row = {
        "plan": plan,
        "date_label": _workspace_date_label(kind, plan),
        "households": households_for_plan(plan),
    }
    if not has_household_copy(rows, source_row, target):
        _replace_plan(kind, copy_plan_for_household(plan, target, _new_trip_id()))
        if target in source_row["households"]:
            assign_household(plan, target)
            _replace_plan(kind, plan)
    return redirect(url_for("home"))


def _household_rows_for_kind(kind):
    """All saved plans of one kind, shaped for the household copy check."""
    rows = []
    for plan in _get_plans(kind):
        rows.append(
            {
                "plan": plan,
                "date_label": _workspace_date_label(kind, plan),
                "households": households_for_plan(plan),
            }
        )
    return rows


@app.route("/smart-trip/new", methods=["POST"])
def smart_trip_new():
    """Create a new smart trip shell and open the unified workspace."""
    category = request.form.get("plan_category", "").strip()
    kind = request.form.get("trip_kind", "").strip() or _trip_kind_for_category(category)
    if kind not in TRIP_KINDS:
        kind = "weekend"
    title = request.form.get("title", "").strip()
    plan = _new_empty_plan(kind, title or None)
    normalise_workspace_plan(plan, kind)
    _apply_smart_start_dates(plan, kind)
    if category in TRIP_CATEGORY_OPTIONS:
        plan["plan_category"] = category
    stay_size = request.form.get("stay_unit_size", "").strip()
    if stay_size in STAY_SIZE_OPTIONS:
        plan["stay_unit_size"] = stay_size
    profile = request.form.get("planner_profile", "").strip()
    if profile in dict(PLANNER_PROFILE_OPTIONS):
        plan["planner_profile"] = profile
    selected_people = _selected_list("travelers")
    legacy_people = {"mario", "esme", "reuben", "vanessa", "noah", "family", "friends"}
    valid_people = (
        set(TRAVELER_LABELS) | {value for value, _label in GOING_PERSON_OPTIONS} | legacy_people
    )
    plan["travelers"] = [person for person in selected_people if person in valid_people]
    plan["travelers_other"] = request.form.get("travelers_other", "").strip()
    saved = _save_household_copies(kind, plan, split_traveler_groups(plan["travelers"]))
    return redirect(url_for("trip_workspace", kind=kind, trip_id=saved["id"]))


def _save_household_copies(kind, plan, traveler_groups):
    """Persist one plan per family when both families are selected."""
    saved = None
    for travelers in traveler_groups:
        item = plan if saved is None else copy.deepcopy(plan)
        if saved is not None:
            item["id"] = _new_trip_id()
        item["travelers"] = travelers
        _replace_plan(kind, item)
        saved = saved or item
    return saved


def _apply_smart_start_dates(plan, kind):
    """Apply home-page start/end date fields to a new smart trip."""
    start_date = request.form.get("start_date", "")
    end_date = request.form.get("end_date", "")
    if kind == "extended":
        plan["trip_start"] = start_date
        plan["trip_end"] = end_date
        return
    plan["start_date"] = start_date
    plan["end_date"] = start_date if kind == "day_trip" else end_date


def _trip_kind_for_category(category):
    """Map the smart planner category to the legacy storage kind."""
    return {
        "Day trip": "day_trip",
        "Movie": "day_trip",
        "Theatre / show": "day_trip",
        "Restaurant booking": "day_trip",
        "Tour / activity": "day_trip",
        "Other booking": "day_trip",
        "Weekend away": "weekend",
        "Long weekend": "long_weekend",
        "Holiday overseas": "extended",
        "Caravan trip": "extended",
    }.get(category, "weekend")


@app.route("/holiday-planning")
def holiday_planning():
    return render_template(
        "holiday_planning.html",
        booking_category_options=BOOKING_CATEGORY_OPTIONS,
        plans_by_kind=_plans_payload_for_holiday_json(),
        going_person_options=GOING_PERSON_OPTIONS,
        holiday_type_options=HOLIDAY_TYPE_OPTIONS,
        trip_category_options=TRIP_CATEGORY_OPTIONS,
        trip_length_options=TRIP_LENGTH_OPTIONS,
    )


@app.route("/save-checklist", methods=["POST"])
def save_checklist():
    transport = request.form.get("pair_transport", "").strip()
    accommodation = request.form.get("pair_accommodation", "").strip()
    content = request.form.get("checklist_content", "")
    return_to = request.form.get("return_to", "").strip()
    trip_id = request.form.get("trip_id", "").strip()
    if return_to in TRIP_KINDS and trip_id:
        after = url_for(return_to, trip=trip_id)
    elif return_to in TRIP_KINDS:
        after = url_for(return_to)
    else:
        after = url_for("holiday_planning")
    if transport not in TRANSPORT_OPTIONS or accommodation not in ACCOMMODATION_OPTIONS:
        return redirect(after)
    pairs = _get_checklist_pairs()
    pairs[_pair_key(transport, accommodation)] = _normalize_checklist_text(content)
    session["checklist_pairs"] = pairs
    session.modified = True
    return redirect(after)


def _flatten_for_search(obj, prefix=""):
    """Yield (field_path, text) for every string value in nested dicts/lists."""
    if obj is None:
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            yield from _flatten_for_search(v, p)
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            p = f"{prefix}[{i}]" if prefix else f"[{i}]"
            yield from _flatten_for_search(item, p)
    else:
        s = str(obj).strip()
        if s:
            yield (prefix or "value", s)
            for variant in _date_search_variants(s):
                yield (prefix or "date_variant", variant)


def _date_search_variants(value):
    """Return human date forms for stored ISO dates so search can match them."""
    parsed = _parse_iso_date(value)
    if not parsed:
        return []
    return [
        parsed.strftime("%d %b %y"),
        parsed.strftime("%d %B %y"),
        parsed.strftime("%d %b %Y"),
        parsed.strftime("%d %B %Y"),
        parsed.strftime("%-d %B %y") if os.name != "nt" else parsed.strftime("%#d %B %y"),
        parsed.strftime("%-d %B %Y") if os.name != "nt" else parsed.strftime("%#d %B %Y"),
    ]


def _trip_matches(plan, q_lower):
    """True if any text in the saved trip contains the query (case-insensitive)."""
    if not plan:
        return False
    return any(q_lower in text.lower() for _, text in _flatten_for_search(plan))


def _non_trip_search_matches(q_lower):
    """True if query matches checklist pairs or sticky things-to-do (for helper text)."""
    pairs = _get_checklist_pairs()
    for key, body in pairs.items():
        body_text = body or ""
        if q_lower in key.lower() or q_lower in body_text.lower():
            return True
    for item in session.get("sticky_things") or []:
        if isinstance(item, str) and q_lower in item.lower():
            return True
    for kind in PLANS_SESSION_KEYS:
        for item in _get_things_library(kind):
            if isinstance(item, str) and q_lower in item.lower():
                return True
    return False


def _search_match_rows(kind, q_lower):
    """List of {plan, travelers} for plans that match."""
    rows = []
    for p in _get_plans(kind):
        if _trip_matches(p, q_lower):
            rows.append({"plan": p, "travelers": _travelers_display(p)})
    return rows


def _apply_workspace_overview(plan, kind):
    """Save overview fields from the smart workspace form."""
    plan["title"] = request.form.get("title", "").strip() or _default_title(kind)
    category = request.form.get("plan_category", "").strip()
    if category in TRIP_CATEGORY_OPTIONS:
        plan["plan_category"] = category
    stay_size = request.form.get("stay_unit_size", "").strip()
    if stay_size in STAY_SIZE_OPTIONS:
        plan["stay_unit_size"] = stay_size
    profile = request.form.get("planner_profile", "").strip()
    if profile in dict(PLANNER_PROFILE_OPTIONS):
        plan["planner_profile"] = profile


def _apply_workspace_dates(plan, kind):
    """Save date fields for the smart workspace form."""
    if kind == "extended":
        plan["trip_start"] = request.form.get("trip_start", "")
        plan["trip_end"] = request.form.get("trip_end", "")
        return
    start_date = request.form.get("start_date", "")
    plan["start_date"] = start_date
    plan["end_date"] = start_date if kind == "day_trip" else request.form.get("end_date", "")


def _apply_workspace_people_and_picks(plan):
    """Save travellers, transport, accommodation, and activity picks."""
    plan["travelers"] = _selected_list("travelers")
    plan["travelers_other"] = request.form.get("travelers_other", "").strip()
    plan["holiday_types"] = [x for x in _selected_list("holiday_types") if x]
    plan["transport"] = _selected_list("transport")
    plan["transport_overall"] = _selected_list("transport")
    plan["accommodation"] = _selected_list("accommodation")
    plan["accommodation_places"] = request.form.get("accommodation_places", "").strip()
    plan["things_to_do_picks"] = [x for x in _selected_list("things_to_do") if x]
    custom_activity = request.form.get("things_to_do_new", "").strip()
    if custom_activity:
        plan["things_to_do_picks"].append(custom_activity)


def _apply_workspace_sections(plan):
    """Save bookings, tasks, budget, documents, packing, and notes."""
    plan["booking_items"] = parse_booking_rows(request.form)
    if "booking_import_text" in request.form:
        plan["booking_import_text"] = request.form.get("booking_import_text", "")
    plan["task_items"] = parse_task_rows(request.form)
    _append_selected_checklist_tasks(plan)
    plan["budget_items"] = budget_items_from_bookings(plan["booking_items"])
    plan["document_items"] = parse_document_rows(request.form)
    plan["important_links"] = _parse_important_links()
    plan["packing_items"] = parse_packing_text(
        request.form.get("packing_text", ""),
        _selected_list("packing_done"),
    )
    if request.form.get("apply_assistant") == "1":
        append_suggestions_to_packing(plan, _selected_list("assistant_packing"))
    plan["notes"] = request.form.get("notes", "")
    plan["assistant_notes"] = request.form.get("assistant_notes", "")
    plan["planner_days"] = _parse_planner_days_from_form()


def _append_selected_checklist_tasks(plan):
    """Append selected timed checklist suggestions to the task list."""
    selected = [
        item.strip() for item in request.form.getlist("checklist_suggestion") if item.strip()
    ]
    if not selected:
        return
    existing = {str(task.get("text") or "").strip().lower() for task in plan["task_items"]}
    for text in selected:
        if text.lower() in existing:
            continue
        plan["task_items"].append({"owner": "", "text": text, "due": "", "status": "To do"})
        existing.add(text.lower())


def _workspace_template_context(plan, kind, trip_id):
    """Build template context for the smart workspace."""
    all_plans = _all_plans_by_kind()
    _refresh_extraction_flags(plan)
    suggestions = assistant_suggestions(
        plan,
        kind,
        previous_packing_items(all_plans, trip_id),
    )
    return {
        "plan": plan,
        "trip_kind": kind,
        "trip_kind_label": HOLIDAY_LABEL_SHORT[kind],
        "trip_id": trip_id,
        "date_label": _workspace_date_label(kind, plan),
        "calendar_dates": _workspace_planning_span(kind, plan),
        "key_timeline_rows": _compact_timeline_rows(plan, kind),
        "key_timeline_days": _compact_timeline_days(plan, kind),
        "workspace_booking_rows": _workspace_booking_rows(plan, kind),
        "missing_booking_categories": _missing_booking_categories(plan),
        "packing_text": packing_text(plan),
        "suggestions": suggestions,
        "checklist_suggestions": _trip_checklist_suggestions(plan, kind),
        "budget_total": budget_total(budget_items_from_bookings(plan.get("booking_items") or [])),
        "trip_category_options": TRIP_CATEGORY_OPTIONS,
        "planner_profile_options": PLANNER_PROFILE_OPTIONS,
        "stay_size_options": STAY_SIZE_OPTIONS,
        "booking_category_options": BOOKING_CATEGORY_OPTIONS,
        "accommodation_checkboxes": ACCOMMODATION_CHECKBOXES,
        "transport_options": TRANSPORT_OPTIONS,
        "traveler_options": TRAVELER_OPTIONS,
        "holiday_type_options": HOLIDAY_TYPE_OPTIONS,
        "things_to_do_options": THINGS_TO_DO_OPTIONS,
        "travelers_display": _travelers_display(plan),
    }


def _trip_checklist_suggestions(plan, kind):
    """Timed checklist suggestions for the Family Tasks tab."""
    rows = _base_checklist_rows(plan, kind)
    rows.extend(_booking_checklist_rows(plan))
    rows.extend(_activity_checklist_rows(plan))
    rows.extend(
        [
            ("Day before", "Charge devices"),
            ("Travel day", "ID cards"),
            ("Return", "Check out"),
        ]
    )
    return _filter_existing_checklist_rows(rows, plan)


def _base_checklist_rows(plan, kind):
    """Base checklist suggestions from trip type."""
    category = str(plan.get("plan_category") or "")
    rows = [
        ("Now", "Confirm bookings"),
        ("Now", "Save contacts"),
        ("1 week", "Check weather"),
    ]
    if category == "Holiday overseas" or kind == "extended":
        rows.extend(
            [
                ("Now", "Passport"),
                ("Now", "Emergency contacts"),
                ("Now", "Insurance"),
                ("1 week", "Buy eSIM"),
                ("1 week", "Currency"),
                ("Travel day", "Check visas"),
                ("Travel day", "Power adaptor"),
                ("Safety", "Doc copies"),
            ]
        )
    if category == "Caravan trip":
        rows.extend(
            [
                ("1 week", "Check tyres"),
                ("1 week", "Gas bottle"),
                ("1 week", "Water hose"),
                ("1 week", "Power lead"),
                ("1 week", "Confirm site"),
                ("Travel day", "Plan route"),
            ]
        )
    return rows


def _booking_checklist_rows(plan):
    """Checklist suggestions from imported bookings."""
    rows = []
    for booking in plan.get("booking_items") or []:
        booking_category = str(booking.get("category") or "")
        booking_name = str(booking.get("name") or "").lower()
        if booking_category == "Flight":
            rows.extend(
                [
                    ("Travel day", "Boarding pass"),
                    ("Travel day", "Check seats"),
                    ("Travel day", "Airport transfer"),
                ]
            )
        if booking_category == "Accommodation":
            rows.extend([("1 week", "Confirm hotel"), ("Arrival", "Check-in time")])
        if "robot" in booking_name:
            rows.append(("There", "Robot show"))
        if "fairmont" in booking_name or "bund" in booking_name:
            rows.append(("There", "Jazz booking"))
    return rows


def _activity_checklist_rows(plan):
    """Checklist suggestions from selected activity types."""
    rows = []
    selected_types = " ".join(plan.get("holiday_types") or []).lower()
    if "show" in selected_types:
        rows.append(("1 week", "Show tickets"))
    if "movie" in selected_types:
        rows.append(("1 week", "Movie tickets"))
    if "restaurant" in selected_types:
        rows.append(("1 week", "Dinner booking"))
    return rows


def _filter_existing_checklist_rows(rows, plan):
    """Remove checklist suggestions already in the task list."""
    existing = {
        str(task.get("text") or "").strip().lower()
        for task in plan.get("task_items") or []
        if str(task.get("text") or "").strip()
    }
    seen = set()
    filtered = []
    for timing, item in rows:
        key = item.lower()
        if key in existing or key in seen:
            continue
        seen.add(key)
        filtered.append((timing, item))
    return filtered


@app.post("/trip/<kind>/<trip_id>/task-status")
def update_task_status(kind, trip_id):
    """Autosave a Family Tasks checkbox change from the trip workspace.

    Needs: REQ-006, TEST-019
    """
    if kind not in TRIP_KINDS:
        return jsonify({"ok": False, "error": "Unknown trip type"}), 404
    plan = _find_plan(kind, trip_id)
    if not plan:
        return jsonify({"ok": False, "error": "Trip not found"}), 404

    normalise_workspace_plan(plan, kind)
    payload = request.get_json(silent=True) or {}
    task_text = str(payload.get("text") or "").strip()
    task_index_raw = payload.get("index")
    status = "Done" if payload.get("done") else "To do"
    if not task_text:
        return jsonify({"ok": False, "error": "Task text is required"}), 400

    task_items = plan.setdefault("task_items", [])
    task_index = _matching_task_index(task_items, task_index_raw, task_text)
    if task_index is None:
        task_items.append({"owner": "", "text": task_text, "due": "", "status": status})
        task_index = len(task_items) - 1
    else:
        task_items[task_index]["status"] = status

    _replace_plan(kind, plan)
    return jsonify({"ok": True, "status": status, "index": task_index})


def _matching_task_index(task_items, task_index_raw, task_text):
    """Find a task by row number first, then by text as a fallback.

    Needs: REQ-006, TEST-019
    """
    try:
        task_index = int(task_index_raw)
    except (TypeError, ValueError):
        task_index = None
    if task_index is not None and 0 <= task_index < len(task_items):
        saved_text = str(task_items[task_index].get("text") or "").strip()
        if saved_text == task_text:
            return task_index

    wanted_text = task_text.lower()
    for index, task in enumerate(task_items):
        saved_text = str(task.get("text") or "").strip().lower()
        if saved_text == wanted_text:
            return index
    return None


@app.route("/search")
def search():
    q = request.args.get("q", "").strip()
    if not q:
        return render_template(
            "search.html",
            query="",
            has_query=False,
            day_trip_matches=[],
            weekend_matches=[],
            long_weekend_matches=[],
            extended_matches=[],
            other_matches=False,
            trip_any=False,
        )
    q_lower = q.lower()
    day_trip_matches = _search_match_rows("day_trip", q_lower)
    weekend_matches = _search_match_rows("weekend", q_lower)
    long_weekend_matches = _search_match_rows("long_weekend", q_lower)
    extended_matches = _search_match_rows("extended", q_lower)
    trip_any = bool(day_trip_matches or weekend_matches or long_weekend_matches or extended_matches)
    other_matches = _non_trip_search_matches(q_lower)
    return render_template(
        "search.html",
        query=q,
        has_query=True,
        day_trip_matches=day_trip_matches,
        weekend_matches=weekend_matches,
        long_weekend_matches=long_weekend_matches,
        extended_matches=extended_matches,
        other_matches=other_matches,
        trip_any=trip_any,
    )


@app.route("/trip/<kind>/<trip_id>", methods=["GET", "POST"])
def trip_workspace(kind, trip_id):
    """Unified workspace for plans, bookings, packing, and assistant suggestions."""
    if kind not in TRIP_KINDS:
        return redirect(url_for("home"))
    plan = _find_plan(kind, trip_id)
    if not plan:
        return redirect(url_for("holiday_planning"))
    normalise_workspace_plan(plan, kind)

    if request.method == "POST":
        _apply_workspace_overview(plan, kind)
        _apply_workspace_dates(plan, kind)
        _apply_workspace_people_and_picks(plan)
        _apply_workspace_sections(plan)
        _cleanup_workspace_lists(plan)
        _refresh_extraction_flags(plan)
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        active_tab = request.form.get("active_tab", "overview").strip() or "overview"
        if active_tab not in {
            "overview",
            "bookings",
            "tasks",
            "packing",
            "budget",
            "documents",
            "planner",
            "assistant",
        }:
            active_tab = "overview"
        if request.form.get("autosave") == "1":
            return jsonify({"ok": True})
        return redirect(url_for("trip_workspace", kind=kind, trip_id=trip_id) + f"#{active_tab}")

    return render_template(
        "trip_workspace.html", **_workspace_template_context(plan, kind, trip_id)
    )


@app.route("/trip/<kind>/<trip_id>/lookup-places", methods=["POST"])
def lookup_places(kind, trip_id):
    """Look up public phone numbers and websites for stays on this trip."""
    if kind not in TRIP_KINDS:
        return jsonify({"ok": False, "error": "Unknown trip type"}), 400
    plan = _find_plan(kind, trip_id)
    if not plan:
        return jsonify({"ok": False, "error": "Trip not found"}), 404
    normalise_workspace_plan(plan, kind)
    messages = fill_missing_place_contacts(plan.get("booking_items") or [])
    _refresh_extraction_flags(plan)
    _replace_plan(kind, plan)
    return jsonify(
        {
            "ok": True,
            "messages": messages,
            "redirect": url_for("trip_workspace", kind=kind, trip_id=trip_id) + "#bookings",
        }
    )


@app.route("/trip/<kind>/<trip_id>/import-itinerary", methods=["POST"])
def import_itinerary(kind, trip_id):
    """Import and scan a travel document into every workspace tab."""
    if kind not in TRIP_KINDS:
        return jsonify({"ok": False, "error": "Unknown trip type"}), 400
    plan = _find_plan(kind, trip_id)
    if not plan:
        return jsonify({"ok": False, "error": "Trip not found"}), 404
    upload = request.files.get("file")
    if not upload or not upload.filename:
        return jsonify({"ok": False, "error": "Choose a file first"}), 400
    normalise_workspace_plan(plan, kind)
    raw_text = _extract_document_text(upload)
    summary = _import_itinerary_text(
        plan,
        raw_text,
        upload.filename,
        request.form.get("note", "").strip(),
    )
    _replace_plan(kind, plan)
    return jsonify(
        {
            "ok": True,
            "summary": summary,
            "document": summary.get("imported_document"),
            "redirect": url_for("trip_workspace", kind=kind, trip_id=trip_id),
        }
    )


@app.route("/trip/<kind>/<trip_id>/pack")
def trip_pack(kind, trip_id):
    """Printable family trip pack with bookings, tasks, packing, and notes."""
    if kind not in TRIP_KINDS:
        return redirect(url_for("home"))
    plan = _find_plan(kind, trip_id)
    if not plan:
        return redirect(url_for("holiday_planning"))
    normalise_workspace_plan(plan, kind)
    return render_template(
        "trip_pack.html",
        plan=plan,
        trip_kind=kind,
        trip_id=trip_id,
        date_label=_workspace_date_label(kind, plan),
        travelers_display=_travelers_display(plan),
        packing_text=packing_text(plan),
        budget_total=budget_total(budget_items_from_bookings(plan.get("booking_items") or [])),
    )


@app.route("/delete-trip", methods=["POST"])
def delete_trip():
    kind = request.form.get("trip_kind", "")
    trip_id = request.form.get("trip_id", "").strip()
    if kind in PLANS_SESSION_KEYS and trip_id:
        _delete_plan(kind, trip_id)
    return redirect(url_for("home"))


TRIP_ENDPOINTS = {
    "day_trip": "day_trip",
    "weekend": "weekend",
    "long_weekend": "long_weekend",
    "extended": "extended",
}


def _redirect_to_trip(kind, trip_id):
    """Redirect to the classic form for a saved trip."""
    return redirect(url_for(TRIP_ENDPOINTS[kind], trip=trip_id))


def _save_trip_and_redirect(kind, plan):
    """Persist a classic trip form payload and redirect back to it."""
    _replace_plan(kind, plan)
    _sync_checklist_auto_headers(plan, kind)
    return _redirect_to_trip(kind, plan["id"])


def _handle_new_or_duplicate_request(kind):
    """Handle classic ``?new=1`` and ``?duplicate=1`` route branches."""
    if request.args.get("new") == "1":
        title = request.args.get("title", "").strip()
        plan = _new_empty_plan(kind, title or None)
        _replace_plan(kind, plan)
        return _redirect_to_trip(kind, plan["id"])

    if request.args.get("duplicate") != "1":
        return None
    source = _find_plan(kind, request.args.get("from", "").strip())
    if not source:
        return redirect(url_for("holiday_planning"))
    plan = _duplicate_plan_without_dates(kind, source)
    return _save_trip_and_redirect(kind, plan)


def _resolve_classic_route_plan(kind):
    """Return ``(plan, trip_id, redirect_response)`` for classic route GETs."""
    trip_id = request.args.get("trip")
    plans = _get_plans(kind)
    if trip_id:
        plan = _find_plan(kind, trip_id)
        if plan:
            return plan, trip_id, None
        return None, None, redirect(url_for("holiday_planning"))
    if not plans:
        return None, None, None
    if len(plans) == 1:
        plan = plans[0]
        return plan, plan.get("id"), None
    return None, None, redirect(url_for("holiday_planning"))


def _classic_template_context(kind, plan, trip_id):
    """Shared context for classic trip templates."""
    return {
        "plan": plan,
        "trip_id": trip_id,
        "trip_kind": kind,
        "accommodation_checkboxes": ACCOMMODATION_CHECKBOXES,
        "transport_options": TRANSPORT_OPTIONS,
        "traveler_options": TRAVELER_OPTIONS,
        "holiday_type_options": HOLIDAY_TYPE_OPTIONS,
        "travelers_display": _travelers_display(plan),
        "checklist_pair_rows": _checklist_pair_rows_for_plan(kind, plan),
        "things_to_do_options": THINGS_TO_DO_OPTIONS,
        "things_library": _get_things_library(kind),
        "calendar_dates": _calendar_dates_for_plan(kind, plan),
        "plan_transport_list": _transport_list_for_form(plan),
    }


def _render_classic_trip(kind, template_name, plan, trip_id, **extra_context):
    """Render one of the legacy trip forms with shared context."""
    context = _classic_template_context(kind, plan, trip_id)
    context.update(extra_context)
    return render_template(template_name, **context)


def _date_trip_payload(kind, trip_id):
    """Build a classic day/weekend/long-weekend trip payload from the form."""
    common = _trip_payload_common(kind)
    start_date = request.form.get("start_date", "")
    end_date = start_date if kind == "day_trip" else request.form.get("end_date", "")
    return {
        "id": trip_id,
        "title": request.form.get("title", "").strip() or _default_title(kind),
        "start_date": start_date,
        "end_date": end_date,
        "transport": _selected_list("transport"),
        **common,
    }


def _date_trip_route(kind, template_name):
    """Shared classic route for day/weekend/long-weekend plans."""
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        return _save_trip_and_redirect(kind, _date_trip_payload(kind, trip_id))

    requested = _handle_new_or_duplicate_request(kind)
    if requested:
        return requested
    plan, trip_id, route_redirect = _resolve_classic_route_plan(kind)
    if route_redirect:
        return route_redirect
    return _render_classic_trip(kind, template_name, plan, trip_id)


def _extended_trip_payload(trip_id):
    """Build a classic extended trip payload from the form."""
    common = _trip_payload_common("extended")
    return {
        "id": trip_id,
        "title": request.form.get("title", "").strip() or _default_title("extended"),
        "trip_start": request.form.get("trip_start", ""),
        "trip_end": request.form.get("trip_end", ""),
        "legs": _parse_extended_legs(),
        "transport_overall": _selected_list("transport"),
        **common,
    }


def _extended_trip_route():
    """Shared route body for the classic extended trip form."""
    kind = "extended"
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        return _save_trip_and_redirect(kind, _extended_trip_payload(trip_id))

    requested = _handle_new_or_duplicate_request(kind)
    if requested:
        return requested
    plan, trip_id, route_redirect = _resolve_classic_route_plan(kind)
    if route_redirect:
        return route_redirect
    legs = plan.get("legs") if plan else None
    return _render_classic_trip(kind, "extended.html", plan, trip_id, legs=legs or [{}])


@app.route("/day-trip", methods=["GET", "POST"])
def day_trip():
    return _date_trip_route("day_trip", "day_trip.html")


@app.route("/weekend", methods=["GET", "POST"])
def weekend():
    return _date_trip_route("weekend", "weekend.html")


@app.route("/long-weekend", methods=["GET", "POST"])
def long_weekend():
    return _date_trip_route("long_weekend", "long_weekend.html")


@app.route("/extended", methods=["GET", "POST"])
def extended():
    return _extended_trip_route()


@app.route("/clear-session", methods=["GET", "POST"])
def clear_session():
    """Old wipe-all address. It opens the chooser and does not delete plans."""
    return redirect(url_for("clear_plans"))


@app.route("/clear-plans", methods=["GET", "POST"])
def clear_plans():
    """Delete only the saved plans the user ticks. Leave the rest in place."""
    plans = _saved_plan_rows()
    if request.method == "POST":
        known = {row["plan"]["id"] for row in plans}
        chosen = [trip_id for trip_id in request.form.getlist("trip_id") if trip_id in known]
        if not chosen:
            return render_template(
                "clear_plans.html",
                plans=plans,
                error="Choose at least one plan.",
            )
        conn = get_db()
        for trip_id in chosen:
            db_delete_trip(conn, trip_id)
        conn.commit()
        return redirect(url_for("home"))
    return render_template("clear_plans.html", plans=plans, error="")


def _saved_plan_rows():
    """Every saved plan, with a date and family label for the delete chooser."""
    rows = []
    for kind in TRIP_KINDS:
        for plan in _get_plans(kind):
            rows.append(
                {
                    "kind": kind,
                    "plan": plan,
                    "sort": _plan_sort_start(plan, kind),
                    "date_label": _workspace_date_label(kind, plan),
                    "who": describe_households(plan) or "Not assigned",
                }
            )
    rows.sort(key=lambda row: (row["sort"], row["kind"], row["plan"].get("title") or ""))
    return rows


if __name__ == "__main__":
    debug_enabled = os.environ.get("FLASK_DEBUG", "").lower() in {"1", "true", "yes"}
    # Listen on the home network so Home Assistant can read the calendar feeds.
    app.run(debug=debug_enabled, host="0.0.0.0", port=5000)  # noqa: S104
