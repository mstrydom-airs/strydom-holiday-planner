"""Keep this repo and the Home Assistant planner on one trip database.

This repo is the copy that is written to the NUC. Each sync first reads the
trips saved on the NUC so a newer save there is kept, then copies the planner
and ``travel_hub.db`` back and restarts Travel Hub.

Needs: SPEC-007
"""

from __future__ import annotations

import argparse
import io
import json
import logging
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

logger = logging.getLogger(__name__)

SSH_HOST = "root@192.168.1.144"
SSH_PORT = "22228"
SSH_TIMEOUT_SECONDS = 75
DEPLOY_ROOTS = (
    "app.py",
    "database.py",
    "requirements.txt",
    "static",
    "templates",
    "trip_planner",
    "travel_hub.db",
)
SKIP_PARTS = frozenset({"__pycache__"})

# Stop the app before replacing its database, then start it again.
REMOTE_COMMAND = """
set -e
fuser -k 8765/tcp >/dev/null 2>&1 || true
python3 -c 'import sys,time,urllib.request
for _ in range(25):
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/", timeout=1)
    except Exception:
        sys.exit(0)
    time.sleep(0.3)
sys.exit(1)'
cp -a /config/trip_planner/travel_hub.db /config/trip_planner/travel_hub.db.bak-last || true
tar -xf - -C /config/trip_planner
rm -f /config/trip_planner/travel_hub.db-wal /config/trip_planner/travel_hub.db-shm
find /config/trip_planner -type d -name __pycache__ -prune -exec rm -rf {} +
python3 /config/scripts/trip_planner_serve.py
python3 -c 'import sys,time,urllib.request
for _ in range(25):
    try:
        urllib.request.urlopen("http://127.0.0.1:8765/", timeout=2)
        print("up")
        sys.exit(0)
    except Exception:
        time.sleep(0.3)
sys.exit(1)'
"""

PULL_COMMAND = """
python3 -c 'import sqlite3
src = sqlite3.connect("/config/trip_planner/travel_hub.db")
dst = sqlite3.connect("/tmp/travel_hub_pull.db")
src.backup(dst)
dst.close()
src.close()'
cat /tmp/travel_hub_pull.db
rm -f /tmp/travel_hub_pull.db
"""


class TripRow(NamedTuple):
    """One saved trip, including the timestamp stored beside its JSON."""

    trip_id: str
    kind: str
    updated_at: str
    data: dict[str, Any]


def _is_skipped(relative: PurePosixPath) -> bool:
    """Return True when ``relative`` must not be copied onto the NUC."""
    if any(part.startswith(".") or part in SKIP_PARTS for part in relative.parts):
        return True
    name = relative.name
    if name.endswith((".pyc", ".pyo")):
        return True
    return name != "travel_hub.db" and ".db" in name


def collect_deploy_files(root: Path) -> list[Path]:
    """Return planner files under ``root`` that belong on Home Assistant.

    Needs: SPEC-007
    """
    chosen: list[Path] = []
    for entry in DEPLOY_ROOTS:
        path = root / entry
        if not path.exists():
            continue
        if path.is_file():
            chosen.append(path)
            continue
        chosen.extend(_files_under(root, path))
    return chosen


def _files_under(root: Path, directory: Path) -> list[Path]:
    """Return deployable files inside ``directory``."""
    chosen: list[Path] = []
    for file_path in directory.rglob("*"):
        if not file_path.is_file():
            continue
        relative = PurePosixPath(file_path.relative_to(root).as_posix())
        if _is_skipped(relative):
            continue
        chosen.append(file_path)
    return chosen


def newer_trip(local: TripRow, remote: TripRow) -> TripRow:
    """Return the trip whose saved time is later. This repo wins a tie.

    Needs: SPEC-007
    """
    if remote.updated_at > local.updated_at:
        return remote
    return local


def _payload_key(row: TripRow) -> str:
    """Return trip JSON with the id removed, for spotting the same plan."""
    payload = dict(row.data)
    payload.pop("id", None)
    return json.dumps(payload, sort_keys=True, ensure_ascii=False)


def matching_payload_id(rows: dict[str, TripRow], remote: TripRow) -> str | None:
    """Return a different id that stores the same plan as ``remote``."""
    remote_key = _payload_key(remote)
    for trip_id, row in rows.items():
        if trip_id != remote.trip_id and _payload_key(row) == remote_key:
            return trip_id
    return None


def apply_nuc_row(
    merged: dict[str, TripRow],
    remote: TripRow,
    previously_synced: set[str] | None,
) -> None:
    """Fold one NUC trip into ``merged``.

    Needs: SPEC-007
    """
    current = merged.get(remote.trip_id)
    if current is not None:
        merged[remote.trip_id] = newer_trip(current, remote)
        return
    twin_id = matching_payload_id(merged, remote)
    if twin_id is not None:
        del merged[twin_id]
        merged[remote.trip_id] = remote
        return
    if previously_synced is not None and remote.trip_id in previously_synced:
        return
    merged[remote.trip_id] = remote


def merge_trips(
    local_rows: list[TripRow],
    nuc_rows: list[TripRow],
    previously_synced: set[str] | None,
) -> list[TripRow]:
    """Update local trips from the NUC without bringing back a deleted trip.

    Needs: SPEC-007
    """
    merged = {row.trip_id: row for row in local_rows}
    for remote in nuc_rows:
        apply_nuc_row(merged, remote, previously_synced)
    return list(merged.values())


def trip_signature(rows: list[TripRow]) -> tuple[tuple[str, str, str, str], ...]:
    """Return a stable comparison key for a set of trips."""
    packed = [
        (
            row.trip_id,
            row.kind,
            row.updated_at,
            json.dumps(row.data, sort_keys=True, ensure_ascii=False),
        )
        for row in rows
    ]
    return tuple(sorted(packed))


def load_trips(path: Path) -> list[TripRow]:
    """Read trips from a Travel Hub SQLite file.

    Needs: SPEC-007
    """
    connection = sqlite3.connect(path)
    try:
        rows = connection.execute("SELECT id, kind, updated_at, data FROM trips").fetchall()
    finally:
        connection.close()
    loaded: list[TripRow] = []
    for trip_id, kind, updated_at, data in rows:
        loaded.append(TripRow(str(trip_id), str(kind), str(updated_at), json.loads(data)))
    return loaded


def load_trips_from_bytes(payload: bytes) -> list[TripRow]:
    """Read trips from SQLite bytes downloaded from the NUC."""
    if not payload.startswith(b"SQLite format 3"):
        raise OSError("Home Assistant did not return a trip database")
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as handle:
        handle.write(payload)
        temporary = Path(handle.name)
    try:
        return load_trips(temporary)
    finally:
        temporary.unlink(missing_ok=True)


def _create_trips_table(connection: sqlite3.Connection) -> None:
    """Create the trips table on a fresh database file."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS trips (
            id TEXT PRIMARY KEY,
            kind TEXT NOT NULL,
            data TEXT NOT NULL,
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )


def write_trips(path: Path, rows: list[TripRow]) -> None:
    """Replace trips in ``path``, keeping each row's original timestamp.

    Needs: SPEC-007
    """
    temporary = path.with_name(path.name + ".syncing")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    connection.row_factory = sqlite3.Row
    try:
        _create_trips_table(connection)
        connection.execute("DELETE FROM trips")
        for row in rows:
            payload = json.dumps(row.data, ensure_ascii=False)
            connection.execute(
                "INSERT INTO trips (id, kind, data, updated_at) VALUES (?, ?, ?, ?)",
                (row.trip_id, row.kind, payload, row.updated_at),
            )
        connection.commit()
    finally:
        connection.close()
    temporary.replace(path)


def backup_database(path: Path) -> None:
    """Keep the previous local database beside the live file."""
    if path.is_file():
        shutil.copy2(path, path.with_name(path.name + ".bak-last"))


def _ssh_base() -> list[str]:
    """Return the ssh invocation for the Home Assistant NUC."""
    key = Path.home() / ".ssh" / "id_ed25519"
    if not key.is_file():
        raise OSError(f"SSH key not found: {key}")
    return [
        "ssh",
        "-p",
        SSH_PORT,
        "-i",
        str(key),
        "-o",
        "BatchMode=yes",
        "-o",
        "ConnectTimeout=8",
        "-o",
        "StrictHostKeyChecking=accept-new",
        SSH_HOST,
    ]


def _run_ssh(
    remote_command: str, payload: bytes | None = None
) -> subprocess.CompletedProcess[bytes]:
    """Run ``remote_command`` on the NUC and return the completed process."""
    completed = subprocess.run(  # noqa: S603
        [*_ssh_base(), remote_command],
        input=payload,
        capture_output=True,
        timeout=SSH_TIMEOUT_SECONDS,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", "replace").strip()
        raise OSError(detail or f"ssh exited {completed.returncode}")
    return completed


def pull_database_bytes() -> bytes:
    """Download a consistent snapshot of the NUC trip database.

    Needs: SPEC-007
    """
    completed = _run_ssh(PULL_COMMAND)
    return completed.stdout


def push_and_restart(root: Path) -> None:
    """Send this repo's planner and trip database to the NUC, then restart it.

    Needs: SPEC-007
    """
    archive = build_archive(root, collect_deploy_files(root))
    completed = _run_ssh(REMOTE_COMMAND, archive)
    message = completed.stdout.decode("utf-8", "replace").strip()
    if message:
        logger.info("%s", message)


def build_archive(root: Path, files: list[Path]) -> bytes:
    """Pack ``files`` into a tar using paths relative to ``root``.

    Needs: SPEC-007
    """
    buffer = io.BytesIO()
    with tarfile.open(fileobj=buffer, mode="w") as archive:
        for path in files:
            archive.add(path, arcname=path.relative_to(root).as_posix())
    return buffer.getvalue()


def synced_at_value(stamp_path: Path) -> float | None:
    """Return the last successful sync time, or None when a sync is due."""
    if not stamp_path.is_file():
        return None
    text = stamp_path.read_text(encoding="utf-8").strip()
    try:
        return float(text)
    except ValueError:
        try:
            payload = json.loads(text)
            return float(payload["synced_at"])
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            return None


def previous_trip_ids(stamp_path: Path) -> set[str] | None:
    """Return trip ids from the last sync. None means this is the first merge."""
    if not stamp_path.is_file():
        return None
    text = stamp_path.read_text(encoding="utf-8").strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    trip_ids = payload.get("trip_ids")
    if not isinstance(trip_ids, list):
        return None
    return {str(trip_id) for trip_id in trip_ids}


def source_is_newer(root: Path, synced_at: float) -> bool:
    """Return True when planner files changed after ``synced_at``."""
    files = collect_deploy_files(root)
    if not files:
        return False
    return max(path.stat().st_mtime for path in files) > synced_at


def sync_is_stale(root: Path, stamp_path: Path) -> bool:
    """Return True when source files are newer than the last successful sync.

    Needs: SPEC-007
    """
    synced_at = synced_at_value(stamp_path)
    if synced_at is None:
        return True
    return source_is_newer(root, synced_at)


def _write_stamp(stamp_path: Path, trip_ids: list[str]) -> None:
    """Remember a successful sync and the trip ids that were written."""
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"synced_at": time.time(), "trip_ids": sorted(trip_ids)}
    stamp_path.write_text(json.dumps(payload), encoding="utf-8")


def _should_skip_push(root: Path, stamp_path: Path, *, trips_changed: bool, if_stale: bool) -> bool:
    """Return True when an idle check has nothing new to publish."""
    if not if_stale or trips_changed:
        return False
    synced_at = synced_at_value(stamp_path)
    if synced_at is None:
        return False
    return not source_is_newer(root, synced_at)


def run_sync(root: Path, *, if_stale: bool) -> int:
    """Read NUC trips into this repo, then publish this repo to the NUC.

    Needs: SPEC-007
    """
    stamp_path = root / ".cursor" / "ha-sync-stamp"
    local_db = root / "travel_hub.db"
    local_rows = load_trips(local_db) if local_db.is_file() else []
    nuc_rows = load_trips_from_bytes(pull_database_bytes())
    merged = merge_trips(local_rows, nuc_rows, previous_trip_ids(stamp_path))
    trips_changed = trip_signature(merged) != trip_signature(local_rows)
    if _should_skip_push(root, stamp_path, trips_changed=trips_changed, if_stale=if_stale):
        sys.stdout.write("{}\n")
        return 0
    if trips_changed:
        backup_database(local_db)
        write_trips(local_db, merged)
        logger.info("Updated local trips from Home Assistant (%s trips).", len(merged))
    push_and_restart(root)
    _write_stamp(stamp_path, [row.trip_id for row in merged])
    if if_stale:
        sys.stdout.write("{}\n")
    else:
        logger.info("Travel Hub on Home Assistant matches this repo.")
    return 0


def main(argv: list[str] | None = None) -> int:
    """Sync trips from the NUC, then update the NUC from this repo.

    Needs: SPEC-007
    """
    parser = argparse.ArgumentParser(description="Sync the planner with Home Assistant.")
    parser.add_argument(
        "--if-stale",
        action="store_true",
        help="Skip the publish when neither trips nor planner files changed.",
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    try:
        return run_sync(root, if_stale=args.if_stale)
    except (OSError, subprocess.TimeoutExpired, sqlite3.Error, json.JSONDecodeError) as exc:
        logger.error("Could not sync Home Assistant: %s", exc)
        return 1


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stderr, format="%(message)s")
    raise SystemExit(main())
