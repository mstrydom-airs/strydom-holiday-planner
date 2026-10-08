"""Trip merge and files published to the Home Assistant planner.

Needs: SPEC-007
"""

from __future__ import annotations

from pathlib import Path

from scripts.sync_ha_planner import (
    TripRow,
    collect_deploy_files,
    merge_trips,
    sync_is_stale,
)


def _row(trip_id: str, updated_at: str, title: str, **extra: object) -> TripRow:
    data: dict[str, object] = {"id": trip_id, "title": title, **extra}
    return TripRow(trip_id, "extended", updated_at, data)


def test_collect_deploy_files__includes_trip_database__skips_backup_and_cache(
    tmp_path: Path,
) -> None:
    """The live database is copied. Backups and bytecode stay behind."""
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")
    (tmp_path / "travel_hub.db").write_bytes(b"sqlite")
    (tmp_path / "travel_hub.db.bak-last").write_bytes(b"old")
    cache = tmp_path / "trip_planner" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "options.cpython-314.pyc").write_bytes(b"pyc")
    (tmp_path / "trip_planner" / "options.py").write_text("x = 1\n", encoding="utf-8")

    relative = {path.relative_to(tmp_path).as_posix() for path in collect_deploy_files(tmp_path)}

    assert relative == {"app.py", "travel_hub.db", "trip_planner/options.py"}


def test_sync_is_stale__missing_stamp__true(tmp_path: Path) -> None:
    """A first sync runs when no stamp has been written."""
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")

    assert sync_is_stale(tmp_path, tmp_path / ".cursor" / "ha-sync-stamp") is True


def test_sync_is_stale__stamp_after_source__false(tmp_path: Path) -> None:
    """Unchanged source does not trigger another copy."""
    (tmp_path / "app.py").write_text("print('app')\n", encoding="utf-8")
    stamp = tmp_path / ".cursor" / "ha-sync-stamp"
    stamp.parent.mkdir()
    stamp.write_text("9999999999\n", encoding="utf-8")

    assert sync_is_stale(tmp_path, stamp) is False


def test_merge_trips__newer_nuc_save__replaces_local_trip() -> None:
    """A later save on the NUC becomes the trip stored in this repo."""
    local = [_row("shanghai", "2026-10-07 00:47:11", "Shanghai", note="old")]
    nuc = [_row("shanghai", "2026-10-07 10:44:03", "Shanghai", note="new")]

    merged = merge_trips(local, nuc, None)

    assert merged[0].data["note"] == "new"


def test_merge_trips__newer_local_save__keeps_repo_trip() -> None:
    """This repo stays the source when its save is the later one."""
    local = [_row("dec", "2026-10-06 23:33:07", "Dec", note="repo")]
    nuc = [_row("dec", "2026-10-06 23:19:54", "Dec", note="nuc")]

    merged = merge_trips(local, nuc, None)

    assert merged[0].data["note"] == "repo"


def test_merge_trips__same_plan_different_id__keeps_nuc_id() -> None:
    """One plan stored under two ids becomes the NUC id."""
    local = [_row("local-id", "2026-10-06 06:25:41", "Australia Day")]
    nuc = [_row("nuc-id", "2026-10-06 06:25:41", "Australia Day")]

    merged = merge_trips(local, nuc, None)

    assert [row.trip_id for row in merged] == ["nuc-id"]


def test_merge_trips__same_title_different_plan__keeps_both() -> None:
    """Two family copies of one title stay as two trips."""
    local = [_row("mario", "2026-10-06 06:25:41", "Holiday", travelers=["Mario"])]
    nuc = [_row("reuben", "2026-10-06 06:25:41", "Holiday", travelers=["Reuben"])]

    merged = merge_trips(local, nuc, None)

    assert {row.trip_id for row in merged} == {"mario", "reuben"}


def test_merge_trips__deleted_after_sync__does_not_return() -> None:
    """A trip removed in this repo stays removed when the NUC still has it."""
    local: list[TripRow] = []
    nuc = [_row("gone", "2026-10-07 10:44:03", "Gone")]

    merged = merge_trips(local, nuc, {"gone"})

    assert merged == []


def test_merge_trips__new_nuc_trip__is_added() -> None:
    """A trip saved only on the NUC is added to this repo."""
    local = [_row("kept", "2026-10-06 06:25:41", "Kept")]
    nuc = [
        _row("kept", "2026-10-06 06:25:41", "Kept"),
        _row("added", "2026-10-08 01:00:00", "Added"),
    ]

    merged = merge_trips(local, nuc, {"kept"})

    assert {row.trip_id for row in merged} == {"kept", "added"}
