"""
Strydom Travel Hub — Flask web application.

Trip plans are stored in SQLite (travel_hub.db). The session still holds
the Flask session cookie, things-to-do library, and shared checklist pairs.
"""

import copy
import re
import uuid
from collections import Counter, defaultdict
from datetime import datetime, timedelta

from flask import Flask, render_template, request, redirect, url_for, session

from database import (
    count_trips,
    delete_all_trips,
    delete_trip as db_delete_trip,
    ensure_trips_schema,
    fetch_plan,
    fetch_plans_for_kind,
    get_db,
    register_db,
    upsert_trip,
)


app = Flask(__name__)
# Needed so Flask can sign session cookies (change in production).
app.secret_key = "dev-strydom-travel-hub-change-me"
register_db(app)


# Checkboxes on trip forms (no Hotel — use named places field instead).
ACCOMMODATION_CHECKBOXES = ["Caravan", "Tent", "Timeshares", "Accor"]
# Full list for checklist pairing (includes Hotel when named places are filled).
ACCOMMODATION_OPTIONS = ACCOMMODATION_CHECKBOXES + ["Hotel"]
TRANSPORT_OPTIONS = ["Flights", "train", "Ute", "Car", "Boat Trip"]
HOLIDAY_TYPE_OPTIONS = [
    "Show",
    "Movie",
    "Walk",
    "Bike ride",
    "Camping",
    "Caravan trip",
    "Timeshare",
    "Accor",
    "Hotel",
]

THINGS_TO_DO_OPTIONS = [
    "Swimming",
    "Beach",
    "Hiking",
    "Walk",
    "Bike ride",
    "Shopping",
    "Restaurants",
    "Sightseeing",
    "Museums / galleries",
    "Events / shows",
    "Show",
    "Movie",
    "Camping",
    "Caravan trip",
    "Timeshare",
    "Accor",
    "Hotel",
    "Relaxing",
]
STANDARD_THINGS = frozenset(THINGS_TO_DO_OPTIONS)

# Who travels — checkbox values and labels for templates.
TRAVELER_OPTIONS = [
    ("mario_esme", "Mario & Esme"),
    ("reuben_vanessa", "Reuben & Vanessa"),
    ("noah", "Noah"),
    ("family", "Family"),
    ("friends", "Friends"),
]

TRAVELER_LABELS = dict(TRAVELER_OPTIONS)

PAIR_SEP = "|"

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


def _import_session_trips_once(conn):
    """One-time copy from session lists into SQLite when DB is empty."""
    if count_trips(conn) > 0:
        return
    seen_ids = set()
    any_import = False

    def _add(kind, plan):
        tid = plan.get("id")
        if not tid or tid in seen_ids:
            return False
        seen_ids.add(tid)
        upsert_trip(conn, kind, plan)
        return True

    for kind, sk in PLANS_SESSION_KEYS.items():
        for p in _session_plans_as_list(session.get(sk)):
            if p.get("id") and _add(kind, p):
                any_import = True
    for kind in LEGACY_PLAN_KEYS:
        old = session.get(kind)
        if isinstance(old, dict) and old.get("id") and _add(kind, old):
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
    """Copy a saved plan with a new id; clear date fields and day planner so new dates can be set."""
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
        return (plan.get("trip_start") or "", plan.get("trip_end") or "")
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
    groups.sort(
        key=lambda g: _plan_sort_start(g["trips"][0], kind) if g["trips"] else "9999-12-31"
    )
    return groups


def _all_glance_groups_sorted():
    """All glance subgroups from all holiday types, in date order (soonest first)."""
    all_groups = []
    for kind in TRIP_KINDS:
        for g in _group_plans_for_glance(kind, _get_plans(kind)):
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
    """All saved plans for Plan a Holiday: destination + dates; duplicate lines get a type suffix."""
    rows = []
    for kind in TRIP_KINDS:
        for p in _get_plans(kind):
            base = _destination_list_label(kind, p)
            rows.append(
                {
                    "id": p.get("id"),
                    "kind": kind,
                    "_base": base,
                    "_sort": _plan_sort_start(p, kind),
                }
            )
    rows.sort(key=lambda r: (r["_sort"], r["kind"], r["_base"]))
    counts = Counter(r["_base"] for r in rows)
    for r in rows:
        lbl = r["_base"]
        if counts[lbl] > 1:
            lbl = f"{lbl} · {HOLIDAY_LABEL_SHORT[r['kind']]}"
        r["label"] = lbl
        del r["_base"], r["_sort"]
    return {
        "all_trips": rows,
        "destination_names": _unique_destination_titles_for_new_plans(),
    }


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
        ts, te = plan.get("trip_start"), plan.get("trip_end")
        if ts and te:
            return _daterange_inclusive(ts, te)
        legs = plan.get("legs") or []
        raw = []
        for leg in legs:
            for k in ("start_date", "end_date"):
                if leg.get(k):
                    raw.append(leg[k][:10])
        if not raw:
            return []
        ds = []
        for d in raw:
            try:
                ds.append(datetime.strptime(d[:10], "%Y-%m-%d").date())
            except ValueError:
                continue
        if not ds:
            return []
        return _daterange_inclusive(str(min(ds)), str(max(ds)))
    return []


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
    if (plan.get("accommodation_places") or "").strip():
        if "Hotel" not in acc:
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
    """Merge current transport & accommodation into shared checklist for each ticked pair (global)."""
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


@app.route("/")
def home():
    glance = _all_glance_groups_sorted()
    return render_template("index.html", glance_groups_sorted=glance)


@app.route("/holiday-planning")
def holiday_planning():
    return render_template(
        "holiday_planning.html",
        plans_by_kind=_plans_payload_for_holiday_json(),
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


def _trip_matches(plan, q_lower):
    """True if any text in the saved trip contains the query (case-insensitive)."""
    if not plan:
        return False
    for _, text in _flatten_for_search(plan):
        if q_lower in text.lower():
            return True
    return False


def _non_trip_search_matches(q_lower):
    """True if query matches checklist pairs or sticky things-to-do (for helper text)."""
    pairs = _get_checklist_pairs()
    for key, body in pairs.items():
        body = body or ""
        if q_lower in key.lower() or q_lower in body.lower():
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


@app.route("/delete-trip", methods=["POST"])
def delete_trip():
    kind = request.form.get("trip_kind", "")
    trip_id = request.form.get("trip_id", "").strip()
    if kind in PLANS_SESSION_KEYS and trip_id:
        _delete_plan(kind, trip_id)
    return redirect(url_for("home"))


@app.route("/day-trip", methods=["GET", "POST"])
def day_trip():
    kind = "day_trip"
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        common = _trip_payload_common(kind)
        start_date = request.form.get("start_date", "")
        plan = {
            "id": trip_id,
            "title": request.form.get("title", "").strip() or _default_title(kind),
            "start_date": start_date,
            "end_date": start_date,
            "transport": _selected_list("transport"),
            **common,
        }
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("day_trip", trip=trip_id))

    if request.args.get("new") == "1":
        title = request.args.get("title", "").strip()
        plan = _new_empty_plan(kind, title or None)
        _replace_plan(kind, plan)
        return redirect(url_for("day_trip", trip=plan["id"]))

    if request.args.get("duplicate") == "1":
        src_id = request.args.get("from", "").strip()
        if not src_id:
            return redirect(url_for("holiday_planning"))
        source = _find_plan(kind, src_id)
        if not source:
            return redirect(url_for("holiday_planning"))
        plan = _duplicate_plan_without_dates(kind, source)
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("day_trip", trip=plan["id"]))

    trip_id = request.args.get("trip")
    plans = _get_plans(kind)
    if trip_id:
        plan = _find_plan(kind, trip_id)
        if not plan:
            return redirect(url_for("holiday_planning"))
    elif len(plans) == 0:
        plan = None
        trip_id = None
    elif len(plans) == 1:
        plan = plans[0]
        trip_id = plan.get("id")
    else:
        return redirect(url_for("holiday_planning"))

    return render_template(
        "day_trip.html",
        plan=plan,
        trip_id=trip_id,
        trip_kind=kind,
        accommodation_checkboxes=ACCOMMODATION_CHECKBOXES,
        transport_options=TRANSPORT_OPTIONS,
        traveler_options=TRAVELER_OPTIONS,
        holiday_type_options=HOLIDAY_TYPE_OPTIONS,
        travelers_display=_travelers_display(plan),
        checklist_pair_rows=_checklist_pair_rows_for_plan(kind, plan),
        things_to_do_options=THINGS_TO_DO_OPTIONS,
        things_library=_get_things_library(kind),
        calendar_dates=_calendar_dates_for_plan(kind, plan),
        plan_transport_list=_transport_list_for_form(plan),
    )


@app.route("/weekend", methods=["GET", "POST"])
def weekend():
    kind = "weekend"
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        common = _trip_payload_common(kind)
        plan = {
            "id": trip_id,
            "title": request.form.get("title", "").strip() or _default_title(kind),
            "start_date": request.form.get("start_date", ""),
            "end_date": request.form.get("end_date", ""),
            "transport": _selected_list("transport"),
            **common,
        }
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("weekend", trip=trip_id))

    if request.args.get("new") == "1":
        title = request.args.get("title", "").strip()
        plan = _new_empty_plan(kind, title or None)
        _replace_plan(kind, plan)
        return redirect(url_for("weekend", trip=plan["id"]))

    if request.args.get("duplicate") == "1":
        src_id = request.args.get("from", "").strip()
        if not src_id:
            return redirect(url_for("holiday_planning"))
        source = _find_plan(kind, src_id)
        if not source:
            return redirect(url_for("holiday_planning"))
        plan = _duplicate_plan_without_dates(kind, source)
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("weekend", trip=plan["id"]))

    trip_id = request.args.get("trip")
    plans = _get_plans(kind)
    if trip_id:
        plan = _find_plan(kind, trip_id)
        if not plan:
            return redirect(url_for("holiday_planning"))
    elif len(plans) == 0:
        plan = None
        trip_id = None
    elif len(plans) == 1:
        plan = plans[0]
        trip_id = plan.get("id")
    else:
        return redirect(url_for("holiday_planning"))

    return render_template(
        "weekend.html",
        plan=plan,
        trip_id=trip_id,
        trip_kind=kind,
        accommodation_checkboxes=ACCOMMODATION_CHECKBOXES,
        transport_options=TRANSPORT_OPTIONS,
        traveler_options=TRAVELER_OPTIONS,
        holiday_type_options=HOLIDAY_TYPE_OPTIONS,
        travelers_display=_travelers_display(plan),
        checklist_pair_rows=_checklist_pair_rows_for_plan(kind, plan),
        things_to_do_options=THINGS_TO_DO_OPTIONS,
        things_library=_get_things_library(kind),
        calendar_dates=_calendar_dates_for_plan(kind, plan),
        plan_transport_list=_transport_list_for_form(plan),
    )


@app.route("/long-weekend", methods=["GET", "POST"])
def long_weekend():
    kind = "long_weekend"
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        common = _trip_payload_common(kind)
        plan = {
            "id": trip_id,
            "title": request.form.get("title", "").strip() or _default_title(kind),
            "start_date": request.form.get("start_date", ""),
            "end_date": request.form.get("end_date", ""),
            "transport": _selected_list("transport"),
            **common,
        }
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("long_weekend", trip=trip_id))

    if request.args.get("new") == "1":
        title = request.args.get("title", "").strip()
        plan = _new_empty_plan(kind, title or None)
        _replace_plan(kind, plan)
        return redirect(url_for("long_weekend", trip=plan["id"]))

    if request.args.get("duplicate") == "1":
        src_id = request.args.get("from", "").strip()
        if not src_id:
            return redirect(url_for("holiday_planning"))
        source = _find_plan(kind, src_id)
        if not source:
            return redirect(url_for("holiday_planning"))
        plan = _duplicate_plan_without_dates(kind, source)
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("long_weekend", trip=plan["id"]))

    trip_id = request.args.get("trip")
    plans = _get_plans(kind)
    if trip_id:
        plan = _find_plan(kind, trip_id)
        if not plan:
            return redirect(url_for("holiday_planning"))
    elif len(plans) == 0:
        plan = None
        trip_id = None
    elif len(plans) == 1:
        plan = plans[0]
        trip_id = plan.get("id")
    else:
        return redirect(url_for("holiday_planning"))

    return render_template(
        "long_weekend.html",
        plan=plan,
        trip_id=trip_id,
        trip_kind=kind,
        accommodation_checkboxes=ACCOMMODATION_CHECKBOXES,
        transport_options=TRANSPORT_OPTIONS,
        traveler_options=TRAVELER_OPTIONS,
        holiday_type_options=HOLIDAY_TYPE_OPTIONS,
        travelers_display=_travelers_display(plan),
        checklist_pair_rows=_checklist_pair_rows_for_plan(kind, plan),
        things_to_do_options=THINGS_TO_DO_OPTIONS,
        things_library=_get_things_library(kind),
        calendar_dates=_calendar_dates_for_plan(kind, plan),
        plan_transport_list=_transport_list_for_form(plan),
    )


@app.route("/extended", methods=["GET", "POST"])
def extended():
    kind = "extended"
    if request.method == "POST":
        trip_id = request.form.get("trip_id", "").strip()
        if not trip_id:
            return redirect(url_for("holiday_planning"))
        common = _trip_payload_common(kind)
        legs = _parse_extended_legs()
        plan = {
            "id": trip_id,
            "title": request.form.get("title", "").strip() or _default_title(kind),
            "trip_start": request.form.get("trip_start", ""),
            "trip_end": request.form.get("trip_end", ""),
            "legs": legs,
            "transport_overall": _selected_list("transport"),
            **common,
        }
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("extended", trip=trip_id))

    if request.args.get("new") == "1":
        title = request.args.get("title", "").strip()
        plan = _new_empty_plan(kind, title or None)
        _replace_plan(kind, plan)
        return redirect(url_for("extended", trip=plan["id"]))

    if request.args.get("duplicate") == "1":
        src_id = request.args.get("from", "").strip()
        if not src_id:
            return redirect(url_for("holiday_planning"))
        source = _find_plan(kind, src_id)
        if not source:
            return redirect(url_for("holiday_planning"))
        plan = _duplicate_plan_without_dates(kind, source)
        _replace_plan(kind, plan)
        _sync_checklist_auto_headers(plan, kind)
        return redirect(url_for("extended", trip=plan["id"]))

    trip_id = request.args.get("trip")
    plans = _get_plans(kind)
    if trip_id:
        plan = _find_plan(kind, trip_id)
        if not plan:
            return redirect(url_for("holiday_planning"))
    elif len(plans) == 0:
        plan = None
        trip_id = None
    elif len(plans) == 1:
        plan = plans[0]
        trip_id = plan.get("id")
    else:
        return redirect(url_for("holiday_planning"))

    legs = plan.get("legs") if plan else None
    if not legs:
        legs = [{}]

    return render_template(
        "extended.html",
        plan=plan,
        legs=legs,
        trip_id=trip_id,
        trip_kind=kind,
        accommodation_checkboxes=ACCOMMODATION_CHECKBOXES,
        transport_options=TRANSPORT_OPTIONS,
        traveler_options=TRAVELER_OPTIONS,
        holiday_type_options=HOLIDAY_TYPE_OPTIONS,
        travelers_display=_travelers_display(plan),
        checklist_pair_rows=_checklist_pair_rows_for_plan(kind, plan),
        things_to_do_options=THINGS_TO_DO_OPTIONS,
        things_library=_get_things_library(kind),
        calendar_dates=_calendar_dates_for_plan(kind, plan),
        plan_transport_list=_transport_list_for_form(plan),
    )


@app.route("/clear-session", methods=["POST"])
def clear_session():
    conn = get_db()
    delete_all_trips(conn)
    conn.commit()
    for key in list(PLANS_SESSION_KEYS.values()) + list(LEGACY_PLAN_KEYS):
        session.pop(key, None)
    session.pop("sticky_things", None)
    return redirect(url_for("home"))


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
