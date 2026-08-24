"""
Daily backups, and the restore path that makes them real.

    python daily_backup.py             # take today's snapshot if not already taken
    python daily_backup.py --force     # take one regardless
    python daily_backup.py --list      # show what exists
    python daily_backup.py --restore data/backups/daily/2026-08-23

WHY BOTH FORMATS
----------------
Each snapshot holds the SQLite file AND a CSV of every table.

- The `.db` copy is an exact restore: same rows, same types, same audit log.
- The CSVs are the insurance policy against this application. In five years
  the Python may not run, the Streamlit version may be long gone, and nobody
  may remember how any of it worked. A folder of dated CSVs is still
  readable by anything, including a person.

A backup you have never restored from is a hope, not a backup, so
`restore_from_csv()` exists and is tested.

RETENTION
---------
Daily snapshots for `KEEP_DAILY` days, plus the first snapshot of every month
kept for `KEEP_MONTHLY` months. Recent mistakes are usually caught within
days; the monthlies cover the mistake nobody noticed until quarter end.

THE PART THIS DOES NOT SOLVE
----------------------------
These land next to the database, on the same machine. That protects against
a bad import or a wrong edit. It does NOT protect against the server dying,
being rebuilt, or being decommissioned.

Point `EXTERNAL_BACKUP_DIR` at a network location that the company's normal
backup regime already covers, or ask IT to include the app's data directory
in it. Copies on one box are not a backup strategy.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import date, datetime
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DAILY_DIR = DATA_DIR / "backups" / "daily"

# How often to snapshot. 24 = daily. Set to 1 for hourly, which is what you
# want once this is the system of record: it caps how much work a failure can
# destroy at one hour instead of one day.
SNAPSHOT_EVERY_HOURS = int(os.environ.get("TRACKER_SNAPSHOT_HOURS", "24"))

KEEP_SNAPSHOTS = int(os.environ.get("TRACKER_KEEP_SNAPSHOTS", "60"))
KEEP_MONTHLY = int(os.environ.get("TRACKER_KEEP_MONTHLY", "24"))

# Warn in the app if the newest snapshot is older than this.
STALE_AFTER_HOURS = SNAPSHOT_EVERY_HOURS * 2

# Optional second copy, off this machine. Set via environment variable, e.g.
#   TRACKER_BACKUP_DIR=\\fileserver\share\launch-tracker-backups
EXTERNAL_BACKUP_DIR = os.environ.get("TRACKER_BACKUP_DIR", "").strip()

TABLES = ("projects", "gates", "audit_log")
MANIFEST = "manifest.json"


def _slot(now: datetime | None = None) -> str:
    """
    Name of the current snapshot slot.

    Daily gives '2026-08-23'. Anything finer gives '2026-08-23T14', so a
    snapshot per interval sorts naturally and cannot collide.
    """
    now = now or datetime.now()
    if SNAPSHOT_EVERY_HOURS >= 24:
        return now.date().isoformat()
    hour = (now.hour // SNAPSHOT_EVERY_HOURS) * SNAPSHOT_EVERY_HOURS
    return f"{now.date().isoformat()}T{hour:02d}"


def _today_dir(day: date | None = None) -> Path:
    if day is not None:
        return DAILY_DIR / day.isoformat()
    return DAILY_DIR / _slot()


def exists_for_today(day: date | None = None) -> bool:
    return (_today_dir(day) / MANIFEST).exists()


def run_daily(force: bool = False, day: date | None = None) -> Path | None:
    """
    Take today's snapshot. Returns the folder, or None if already taken.

    Safe to call on every app start: it is a no-op once today's exists, so
    it costs one filesystem check.
    """
    import db
    import launch_model as lm
    import store

    target = _today_dir(day)
    if target.exists() and not force:
        if (target / MANIFEST).exists():
            return None
        # A half-finished snapshot from an interrupted run.
        shutil.rmtree(target, ignore_errors=True)

    target.mkdir(parents=True, exist_ok=True)

    projects, gates = lm.load_bundled()
    audit = store.read_audit()
    frames = {"projects": projects, "gates": gates, "audit_log": audit}

    for name, frame in frames.items():
        frame.to_csv(target / f"{name}.csv", index=False)

    integrity = "no database"
    if db.DB_PATH.exists():
        db.backup_to(target / "tracker.db")
        integrity = _check_integrity(target / "tracker.db")

    manifest = {
        "created": datetime.now().isoformat(timespec="seconds"),
        "date": (day.isoformat() if day else _slot()),
        "rows": {name: int(len(frame)) for name, frame in frames.items()},
        "integrity": integrity,
        "files": sorted(p.name for p in target.iterdir()),
    }
    (target / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    _prune()
    _copy_external(target)
    return target


def _copy_external(snapshot: Path) -> Path | None:
    """Mirror a snapshot somewhere off this machine, if configured."""
    if not EXTERNAL_BACKUP_DIR:
        return None
    try:
        dest = Path(EXTERNAL_BACKUP_DIR) / snapshot.name
        if dest.exists():
            shutil.rmtree(dest, ignore_errors=True)
        shutil.copytree(snapshot, dest)
        return dest
    except Exception as exc:  # never let a backup failure break the app
        print(f"  external backup to {EXTERNAL_BACKUP_DIR} failed: {exc}")
        return None


def list_snapshots() -> list[Path]:
    if not DAILY_DIR.exists():
        return []
    return sorted(
        (p for p in DAILY_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )


def read_manifest(snapshot: Path) -> dict:
    path = Path(snapshot) / MANIFEST
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def _check_integrity(db_file: Path) -> str:
    """
    Ask SQLite to verify the copy.

    A corrupt backup is worse than no backup, because you find out at the
    moment you need it. This costs milliseconds and turns that into something
    you find out immediately.
    """
    import sqlite3

    try:
        conn = sqlite3.connect(db_file)
        try:
            result = conn.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            conn.close()
        return result
    except Exception as exc:  # noqa: BLE001
        return f"check failed: {exc}"


def _prune() -> None:
    """Keep recent snapshots, plus the first snapshot of each month."""
    snapshots = sorted(p for p in DAILY_DIR.iterdir() if p.is_dir())
    if not snapshots:
        return

    keep = set(snapshots[-KEEP_SNAPSHOTS:])

    first_of_month: dict[str, Path] = {}
    for snap in snapshots:
        month = snap.name[:7]  # YYYY-MM
        first_of_month.setdefault(month, snap)
    for month in sorted(first_of_month)[-KEEP_MONTHLY:]:
        keep.add(first_of_month[month])

    for snap in snapshots:
        if snap not in keep:
            shutil.rmtree(snap, ignore_errors=True)


def verify(snapshot: Path) -> dict:
    """
    Confirm a snapshot is actually restorable.

    Checks the manifest exists, the CSVs parse, the row counts match what the
    manifest claims, and the database copy passes SQLite's integrity check.
    A backup nobody has verified is a guess.
    """
    snapshot = Path(snapshot)
    problems: list[str] = []

    manifest = read_manifest(snapshot)
    if not manifest:
        problems.append("no manifest")

    claimed = manifest.get("rows", {})
    counted: dict[str, int] = {}
    for name in TABLES:
        path = snapshot / f"{name}.csv"
        if not path.exists():
            if name != "audit_log":
                problems.append(f"{name}.csv missing")
            continue
        try:
            counted[name] = len(pd.read_csv(path))
        except Exception as exc:  # noqa: BLE001
            problems.append(f"{name}.csv unreadable: {exc}")
            continue
        if name in claimed and claimed[name] != counted[name]:
            problems.append(
                f"{name}: manifest says {claimed[name]}, file has {counted[name]}"
            )

    db_copy = snapshot / "tracker.db"
    integrity = None
    if db_copy.exists():
        integrity = _check_integrity(db_copy)
        if integrity != "ok":
            problems.append(f"database integrity: {integrity}")

    if counted.get("projects", 0) == 0:
        problems.append("no projects in snapshot")

    return {
        "snapshot": snapshot.name,
        "ok": not problems,
        "rows": counted,
        "integrity": integrity,
        "problems": problems,
    }


def health() -> dict:
    """
    Is the backup arrangement actually working?

    Surfaced in the app so a silently failing backup becomes visible rather
    than being discovered on the day it is needed.
    """
    snaps = list_snapshots()
    now = datetime.now()

    if not snaps:
        return {
            "ok": False,
            "age_hours": None,
            "latest": None,
            "offsite": bool(EXTERNAL_BACKUP_DIR),
            "messages": ["No snapshots have been taken yet."],
        }

    latest = snaps[0]
    manifest = read_manifest(latest)
    created = manifest.get("created")
    try:
        age_hours = (now - datetime.fromisoformat(created)).total_seconds() / 3600
    except (TypeError, ValueError):
        age_hours = None

    messages: list[str] = []
    ok = True

    if age_hours is None:
        messages.append("Latest snapshot has no readable timestamp.")
        ok = False
    elif age_hours > STALE_AFTER_HOURS:
        messages.append(
            f"Newest snapshot is {age_hours:.0f} hours old — expected one every "
            f"{SNAPSHOT_EVERY_HOURS}."
        )
        ok = False

    if manifest.get("integrity") not in (None, "ok", "no database"):
        messages.append(f"Latest snapshot integrity: {manifest['integrity']}")
        ok = False

    if not EXTERNAL_BACKUP_DIR:
        messages.append(
            "No off-machine copy configured. Every backup is on the same "
            "server as the database."
        )
        ok = False
    elif not Path(EXTERNAL_BACKUP_DIR).exists():
        messages.append(f"Off-site path unreachable: {EXTERNAL_BACKUP_DIR}")
        ok = False

    return {
        "ok": ok,
        "age_hours": age_hours,
        "latest": latest.name,
        "count": len(snaps),
        "offsite": bool(EXTERNAL_BACKUP_DIR),
        "interval_hours": SNAPSHOT_EVERY_HOURS,
        "messages": messages,
    }


# ---------------------------------------------------------------------------
# Restore
# ---------------------------------------------------------------------------
class RestoreError(RuntimeError):
    pass


def restore_from_csv(snapshot: Path | dict) -> dict:
    """
    Rebuild the database from a snapshot's CSVs.

    Accepts a folder path, or a dict of {name: file-like} for an upload.
    Returns row counts. Takes a safety snapshot of the current state first,
    so a restore is itself undoable.
    """
    import db
    import launch_model as lm
    import safe_io

    if isinstance(snapshot, dict):
        sources = snapshot
    else:
        folder = Path(snapshot)
        if not folder.is_dir():
            raise RestoreError(f"No such snapshot folder: {folder}")
        sources = {}
        for name in TABLES:
            path = folder / f"{name}.csv"
            if path.exists():
                sources[name] = path

    if "projects" not in sources or "gates" not in sources:
        raise RestoreError(
            "A restore needs at least projects.csv and gates.csv."
        )

    projects = lm.load_projects(sources["projects"])
    gates = lm.load_gates(sources["gates"])

    known = set(projects["project_id"])
    orphans = gates[~gates["project_id"].isin(known)]
    gates = gates[gates["project_id"].isin(known)]

    if projects.empty:
        raise RestoreError("That snapshot contains no projects — refusing to restore.")

    safe_io.backup(reason="pre-restore")

    db.replace_all(projects, gates)

    audit_rows = 0
    if "audit_log" in sources:
        audit = pd.read_csv(sources["audit_log"]).fillna("")
        if len(audit):
            with db.transaction() as conn:
                conn.execute("DELETE FROM audit_log")
                db.insert_audit(conn, audit.to_dict("records"))
            audit_rows = len(audit)

    return {
        "projects": len(projects),
        "gates": len(gates),
        "audit_log": audit_rows,
        "orphaned_gates_dropped": len(orphans),
    }


def main() -> None:
    args = sys.argv[1:]

    if "--list" in args:
        snaps = list_snapshots()
        if not snaps:
            print("No daily snapshots yet.")
            return
        print(f"{len(snaps)} snapshot(s) in {DAILY_DIR}:")
        for snap in snaps:
            m = read_manifest(snap)
            rows = m.get("rows", {})
            print(
                f"  {snap.name}  "
                f"projects={rows.get('projects','?'):>4}  "
                f"gates={rows.get('gates','?'):>4}  "
                f"audit={rows.get('audit_log','?'):>5}"
            )
        return

    if "--verify" in args:
        snaps = list_snapshots()
        if not snaps:
            raise SystemExit("No snapshots to verify.")
        bad = 0
        for snap in snaps:
            result = verify(snap)
            flag = "ok  " if result["ok"] else "FAIL"
            print(f"  {flag} {snap.name}  rows={result['rows']}")
            for problem in result["problems"]:
                print(f"        - {problem}")
            bad += 0 if result["ok"] else 1
        print(f"\n{len(snaps) - bad}/{len(snaps)} snapshots verified")
        raise SystemExit(1 if bad else 0)

    if "--health" in args:
        h = health()
        print("backup health:", "OK" if h["ok"] else "ATTENTION")
        print(f"  latest: {h['latest']}  ({h['count']} kept)")
        if h["age_hours"] is not None:
            print(f"  age: {h['age_hours']:.1f} h  (interval {h['interval_hours']} h)")
        print(f"  off-site: {'yes' if h['offsite'] else 'NO'}")
        for m in h["messages"]:
            print("  -", m)
        raise SystemExit(0 if h["ok"] else 1)

    if "--restore" in args:
        i = args.index("--restore")
        if i + 1 >= len(args):
            raise SystemExit("--restore needs a snapshot folder")
        result = restore_from_csv(Path(args[i + 1]))
        print("restored:", result)
        return

    made = run_daily(force="--force" in args)
    if made is None:
        print(f"Today's snapshot already exists: {_today_dir()}")
    else:
        m = read_manifest(made)
        print(f"wrote {made}")
        print("  rows:", m.get("rows"))
        if EXTERNAL_BACKUP_DIR:
            print(f"  mirrored to {EXTERNAL_BACKUP_DIR}")
        else:
            print(
                "  NOTE: no TRACKER_BACKUP_DIR set — this copy is on the same "
                "machine as the database."
            )


if __name__ == "__main__":
    main()
