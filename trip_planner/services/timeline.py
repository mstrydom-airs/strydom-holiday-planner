"""At-a-glance timeline sections and right-hand month rail (Google Photos style).

Converts each glance row's sort key into a stable month bucket, supplies DOM ids
for scroll targets, and builds the ordered rail (deduplicated, undated last).

Needs: REQ-005, SPEC-005, IMPL-005, TEST-016, TEST-017, UC-002
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date
from typing import Any


@dataclass(frozen=True, slots=True)
class GlanceSectionMeta:
    """One calendar (or undated) bucket for the At a glance list.

    Needs: REQ-005, TEST-016
    """

    section_key: str
    """Stable key, e.g. ``2025-04`` or ``undated``."""

    dom_id: str
    """HTML id for the month heading anchor, e.g. ``glance-section-2025-04``."""

    month_heading: str
    """Human label for the month rail, e.g. ``April 2025`` or ``Undated``."""

    is_undated: bool


SORT_KEY_UNDATED: str = "9999-12-31"
"""Sort sentinel used by ``_plan_sort_start`` in ``app.py`` for plans without a start."""


@dataclass(frozen=True, slots=True)
class GlanceRailItem:
    """One button on the sticky month / year rail.

    Needs: REQ-005, TEST-016
    """

    dom_id: str
    label: str


def glance_section_meta(sort_key: str) -> GlanceSectionMeta:
    """Map a YYYY-MM-DD (or undated) sort key to section metadata.

    Args:
        sort_key: ISO date prefix, or the undated sentinel ``9999-12-31``.

    Returns:
        ``GlanceSectionMeta`` for the list heading and the rail.

    Needs: REQ-005, SPEC-005, TEST-016, UC-002
    """
    sk = (sort_key or "")[:10]
    if not sk or sk in {SORT_KEY_UNDATED, "9999-12-31"}:
        return GlanceSectionMeta(
            section_key="undated",
            dom_id="glance-undated",
            month_heading="Undated",
            is_undated=True,
        )
    try:
        day = date.fromisoformat(sk)
    except ValueError:
        return GlanceSectionMeta(
            section_key="undated",
            dom_id="glance-undated",
            month_heading="Undated",
            is_undated=True,
        )
    y, m = day.year, day.month
    section_key = f"{y:04d}-{m:02d}"
    name = calendar.month_name[m]
    heading = f"{name} {y}"
    return GlanceSectionMeta(
        section_key=section_key,
        dom_id=f"glance-section-{section_key}",
        month_heading=heading,
        is_undated=False,
    )


def _rail_items_from_enriched(
    first_meta_per_section: list[tuple[str, GlanceSectionMeta]],
) -> list[GlanceRailItem]:
    out: list[GlanceRailItem] = []
    for _sk, meta in first_meta_per_section:
        out.append(GlanceRailItem(dom_id=meta.dom_id, label=meta.month_heading))
    return out


def enrich_glance_timeline(
    glance_groups_sorted: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[GlanceRailItem]]:
    """Attach month headings and build the right-hand rail in list order.

    The input order must match ``_all_glance_groups_sorted`` (soonest first;
    undated rows sort last). The first row in each month shows a heading; the
    rail lists each month once, in that order, with ``undated`` last if present.

    Args:
        glance_groups_sorted: List of ``{ "kind", "group", "sort_key" }`` rows.

    Returns:
        (enriched rows for the template, rail buttons in visual order)

    Needs: REQ-005, SPEC-005, TEST-016, TEST-017, IMPL-005
    """
    prev_section: str | None = None
    enriched: list[dict[str, Any]] = []
    first_metas: list[tuple[str, GlanceSectionMeta]] = []
    seen_sections: set[str] = set()

    for item in glance_groups_sorted:
        sk = str(item.get("sort_key", "") or "")
        meta = glance_section_meta(sk)
        show_heading = meta.section_key != prev_section
        prev_section = meta.section_key

        row = dict(item)
        row["glance_show_month_heading"] = show_heading
        row["glance_section_dom_id"] = meta.dom_id
        row["glance_month_heading"] = meta.month_heading
        row["glance_is_undated"] = meta.is_undated
        enriched.append(row)

        if meta.section_key not in seen_sections:
            seen_sections.add(meta.section_key)
            first_metas.append((meta.section_key, meta))

    return enriched, _rail_items_from_enriched(first_metas)
