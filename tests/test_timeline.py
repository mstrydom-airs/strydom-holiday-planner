"""Unit tests for ``app.services.timeline`` (At a glance month rail).

Needs: REQ-005, TEST-016
"""

from __future__ import annotations

from trip_planner.services.timeline import (
    SORT_KEY_UNDATED,
    GlanceRailItem,
    enrich_glance_timeline,
    glance_section_meta,
)


def test_glance_section_meta__undated_sentinel__is_undated() -> None:
    """Parse the app-wide no-date sort sentinel as an Undated section.

    Pytest node: tests/test_timeline.py::test_glance_section_meta__undated_sentinel__is_undated
    """

    m = glance_section_meta(SORT_KEY_UNDATED)
    assert m.is_undated is True
    assert m.section_key == "undated"
    assert m.dom_id == "glance-undated"
    assert m.month_heading == "Undated"


def test_glance_section_meta__iso_date__month_bucket_and_label() -> None:
    """Map an ISO start date to ``YYYY-MM`` and an English month heading.

    Pytest node: tests/test_timeline.py::test_glance_section_meta__iso_date__month_bucket_and_label
    """

    m = glance_section_meta("2026-04-12")
    assert m.is_undated is False
    assert m.section_key == "2026-04"
    assert m.dom_id == "glance-section-2026-04"
    assert m.month_heading == "April 2026"


def test_glance_section_meta__invalid__falls_back_to_undated() -> None:
    """Non-ISO values must not raise; we fall back to the Undated bucket.

    Pytest node: tests/test_timeline.py::test_glance_section_meta__invalid__falls_back_to_undated
    """

    m = glance_section_meta("not-a-date")
    assert m.is_undated is True
    assert m.dom_id == "glance-undated"


def test_enrich_glance_timeline__two_months__headings_and_rail_order() -> None:
    """First row of each new month shows a heading; rail lists months in order.

    Pytest node:
    ``tests/test_timeline.py::test_enrich_glance_timeline__two_months__headings_and_rail_order``
    """

    group_a = {
        "label": "a",
        "trips": [{"id": "1", "start_date": "2026-03-10"}],
        "multiple": False,
    }
    group_b = {
        "label": "b",
        "trips": [{"id": "2", "start_date": "2026-04-20"}],
        "multiple": False,
    }
    raw = [
        {"kind": "day_trip", "group": group_a, "sort_key": "2026-03-10"},
        {"kind": "day_trip", "group": group_b, "sort_key": "2026-04-20"},
    ]
    rows, rail = enrich_glance_timeline(raw)
    assert len(rows) == 2
    assert rows[0]["glance_show_month_heading"] is True
    assert rows[0]["glance_section_dom_id"] == "glance-section-2026-03"
    assert rows[1]["glance_show_month_heading"] is True
    assert [r.label for r in rail] == ["March 2026", "April 2026"]


def test_enrich_glance_timeline__same_month_shows_one_heading() -> None:
    """Consecutive groups in the same month only emit one month heading.

    Pytest node: tests/test_timeline.py::test_enrich_glance_timeline__same_month_shows_one_heading
    """

    g1 = {
        "label": "x",
        "trips": [{"id": "1", "start_date": "2026-01-01"}],
        "multiple": False,
    }
    g2 = {
        "label": "y",
        "trips": [{"id": "2", "start_date": "2026-01-20"}],
        "multiple": False,
    }
    raw = [
        {"kind": "day_trip", "group": g1, "sort_key": "2026-01-01"},
        {"kind": "weekend", "group": g2, "sort_key": "2026-01-20"},
    ]
    rows, rail = enrich_glance_timeline(raw)
    assert rows[0]["glance_show_month_heading"] is True
    assert rows[1]["glance_show_month_heading"] is False
    assert len(rail) == 1
    assert rail[0] == GlanceRailItem(dom_id="glance-section-2026-01", label="January 2026")


def test_enrich_glance_timeline__undated_appears_last_on_rail() -> None:
    """Undated sort keys are grouped and listed last on the month rail.

    Pytest node: tests/test_timeline.py::test_enrich_glance_timeline__undated_appears_last_on_rail
    """

    g1 = {
        "label": "a",
        "trips": [{"id": "1", "start_date": "2026-02-01"}],
        "multiple": False,
    }
    g2 = {
        "label": "Dates not set",
        "trips": [{"id": "2", "start_date": ""}],
        "multiple": False,
    }
    raw = [
        {"kind": "day_trip", "group": g1, "sort_key": "2026-02-01"},
        {"kind": "day_trip", "group": g2, "sort_key": SORT_KEY_UNDATED},
    ]
    _rows, rail = enrich_glance_timeline(raw)
    assert [r.label for r in rail] == ["February 2026", "Undated"]


def test_enrich_glance_timeline__empty__empty_rail() -> None:
    """With no plans, the template receives no row or rail data.

    Pytest node: tests/test_timeline.py::test_enrich_glance_timeline__empty__empty_rail
    """

    rows, rail = enrich_glance_timeline([])
    assert rows == []
    assert rail == []
