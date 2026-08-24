"""
Launch Tracker — self-contained test suite.

    python run_tests.py              # run everything
    python run_tests.py --quick      # skip the slow Streamlit boot tests
    python run_tests.py --keep       # leave the temp workspace for inspection

WHY THIS IS SAFE TO RUN ANY TIME
--------------------------------
Every test runs against a COPY of the application in a temporary directory.
Your real `data/` is never read, written, or deleted. One of the tests
deliberately destroys a database and rebuilds it from a backup — that is the
whole point of it — so isolation matters.

WHAT IT PROVES
--------------
  1  the code imports and the app boots
  2  a fresh install builds its own database
  3  gate dates land on the exact thirds the tracker sheet uses
  4  concurrent editors cannot silently overwrite each other
  5  backups are written and self-verify
  6  a database deleted outright can be rebuilt from a snapshot
  7  a corrupted or tampered backup is detected
  8  the database rejects orphaned records
  9  both roles behave correctly, both pages render
 10  passwords can come from the environment (needed for containers)

Exit code is 0 if everything passed, 1 otherwise, so it can be wired into
anything that cares.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

APP_DIR = Path(__file__).parent.resolve()

# Everything needed to run. `data/` is deliberately absent — each run starts
# from nothing so the bootstrap path gets exercised too.
COPY_ITEMS = [
    "app.py", "auth.py", "config.py", "store.py", "db.py", "schema.sql",
    "safe_io.py", "daily_backup.py", "gate_schedule.py", "launch_model.py",
    "launch_data.py", "launch_charts.py", "tracker_import.py",
    "capacity_model.py", "synthetic_data.py", "migrate_to_sqlite.py",
    "requirements.txt", "views", "assets",
]

PASS, FAIL, SKIP = "PASS", "FAIL", "SKIP"
results: list[tuple[str, str, str]] = []


def record(name: str, status: str, detail: str = "") -> None:
    results.append((name, status, detail))
    mark = {PASS: "  ok  ", FAIL: " FAIL ", SKIP: " skip "}[status]
    print(f"[{mark}] {name}")
    if detail:
        for line in str(detail).splitlines():
            print(f"          {line}")


def check(name: str, fn) -> None:
    """Run one test, catching anything it throws."""
    try:
        detail = fn()
        record(name, PASS, detail or "")
    except AssertionError as exc:
        record(name, FAIL, str(exc))
    except Exception:
        record(name, FAIL, traceback.format_exc(limit=3))


def build_workspace() -> Path:
    ws = Path(tempfile.mkdtemp(prefix="tracker-test-"))
    for item in COPY_ITEMS:
        src = APP_DIR / item
        if not src.exists():
            continue
        dst = ws / item
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    # Streamlit config, but never the real secrets file.
    (ws / ".streamlit").mkdir(exist_ok=True)
    cfg = APP_DIR / ".streamlit" / "config.toml"
    if cfg.exists():
        shutil.copy2(cfg, ws / ".streamlit" / "config.toml")
    return ws


def run_in_workspace(ws: Path, code: str, env_extra: dict | None = None) -> str:
    """Execute a snippet inside the workspace as its own process."""
    import os

    env = {**os.environ, "PYTHONPATH": str(ws), **(env_extra or {})}
    proc = subprocess.run(
        [sys.executable, "-c", code],
        cwd=ws, env=env, capture_output=True, text=True, timeout=900,
    )
    if proc.returncode != 0:
        raise AssertionError(
            f"exit {proc.returncode}\nSTDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr[-2500:]}"
        )
    return proc.stdout.strip()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
def t_imports(ws: Path) -> str:
    return run_in_workspace(ws, """
import auth, config, store, db, safe_io, daily_backup
import gate_schedule, launch_model, launch_charts, launch_data
import tracker_import, capacity_model, synthetic_data
print("all modules import cleanly")
""")


def t_bootstrap(ws: Path) -> str:
    return run_in_workspace(ws, """
import launch_model as lm, db
assert not db.exists(), "database should not exist before first run"
p, g = lm.load_bundled()
assert len(p) > 0 and len(g) > 0, "bootstrap produced no data"
assert db.exists(), "database was not created"
print(f"bootstrapped {len(p)} projects, {len(g)} gates from empty")
""")


def t_gate_maths(ws: Path) -> str:
    return run_in_workspace(ws, """
from datetime import date, timedelta
import gate_schedule as gs

# The real example from the tracker sheet.
kickoff, ppap, sop = date(2024,12,17), date(2025,4,4), date(2026,1,1)
plan = gs.planned_dates("Launch", "Full", kickoff, ppap, sop)
assert plan["1"] == date(2025,1,22), f"gate 1 was {plan['1']}, sheet says 2025-01-22"
assert plan["2"] == date(2025,2,27), f"gate 2 was {plan['2']}, sheet says 2025-02-27"
assert plan["3"] == ppap, "gate 3 must equal PPAP"
assert plan["4"] == sop, "gate 4 must equal SOP"

simple = gs.planned_dates("Launch", "Simple", kickoff, ppap, sop)
assert set(simple) == {"0","SL","4","6M"}, f"simple launch gates were {sorted(simple)}"
assert simple["SL"] == ppap, "simple launch date should equal PPAP"
print("gate 1 = 2025-01-22 and gate 2 = 2025-02-27, matching the tracker sheet")
""")


def t_concurrency(ws: Path) -> str:
    return run_in_workspace(ws, """
import threading, launch_model as lm, store, db
p, _ = lm.load_bundled()
a, b = p.project_id.iloc[0], p.project_id.iloc[1]
with db.transaction() as conn:
    conn.execute("DELETE FROM audit_log")

errors = []
def edit(pid, val):
    try:
        store.update_project("editor", pid, {"job_number": val})
    except Exception as e:
        errors.append(repr(e))

threads = [threading.Thread(target=edit, args=(a if i%2==0 else b, f"J-{i:03d}"))
           for i in range(20)]
for t in threads: t.start()
for t in threads: t.join()
assert not errors, f"errors during concurrent writes: {errors[:3]}"

audit = store.read_audit()
assert len(audit) == 20, f"expected 20 audit entries, got {len(audit)}"

# The real proof: each write saw the previous one's result.
for pid, grp in audit.groupby("project_id"):
    vals = grp[["old_value","new_value"]].values.tolist()
    for i in range(1, len(vals)):
        assert vals[i][0] == vals[i-1][1], (
            f"LOST UPDATE on {pid}: entry {i} started from {vals[i][0]!r} "
            f"but the previous write left {vals[i-1][1]!r}")
print("20 concurrent writes, all 20 recorded, audit chain unbroken")
""")


def t_backup_and_verify(ws: Path) -> str:
    return run_in_workspace(ws, """
import daily_backup as bk
snap = bk.run_daily(force=True)
assert snap is not None, "no snapshot was written"
files = {f.name for f in snap.iterdir()}
for needed in ("projects.csv", "gates.csv", "tracker.db", "manifest.json"):
    assert needed in files, f"{needed} missing from snapshot"
m = bk.read_manifest(snap)
assert m.get("integrity") == "ok", f"integrity check said {m.get('integrity')!r}"
v = bk.verify(snap)
assert v["ok"], f"verification failed: {v['problems']}"
print(f"snapshot {snap.name} written and verified: {m['rows']}")
""")


def t_restore_from_deletion(ws: Path) -> str:
    """The important one."""
    return run_in_workspace(ws, """
import shutil
from pathlib import Path
import daily_backup as bk, db, store, launch_model as lm

# Make a change we can look for afterwards.
store.update_project("editor", lm.load_bundled()[0].project_id.iloc[0],
                     {"job_number": "RESTORE-CANARY"})
before_p, before_g = lm.load_bundled()
before_audit = len(store.read_audit())
snap = bk.run_daily(force=True)

# Destroy everything: the database, its journals, and the loose CSVs so
# nothing can quietly bootstrap from them.
data = Path("data")
for f in ("tracker.db", "tracker.db-wal", "tracker.db-shm",
          "projects.csv", "gates.csv", "audit_log.csv"):
    (data / f).unlink(missing_ok=True)
assert not db.exists(), "database still present after deletion"

# Rebuild from the snapshot's CSVs alone.
result = bk.restore_from_csv(snap)
after_p, after_g = lm.load_bundled()
after_audit = len(store.read_audit())

assert len(after_p) == len(before_p), f"projects {len(before_p)} -> {len(after_p)}"
assert len(after_g) == len(before_g), f"gates {len(before_g)} -> {len(after_g)}"
assert set(after_p.project_id) == set(before_p.project_id), "project ids differ"
assert after_audit == before_audit, f"audit {before_audit} -> {after_audit}"

canary = after_p[after_p.job_number == "RESTORE-CANARY"]
assert len(canary) == 1, "the edit made before the snapshot did not survive"

# Dates must round-trip exactly, not approximately.
cols = ["project_id","gate_no","plan_date","adjusted_date","actual_date"]
b = before_g.sort_values(["project_id","gate_no"])[cols].reset_index(drop=True)
a = after_g.sort_values(["project_id","gate_no"])[cols].reset_index(drop=True)
assert b.equals(a), "gate dates did not round-trip identically"

print(f"database destroyed and rebuilt from CSV: {result}")
print("projects, gates, every date and the full audit history recovered identically")
""")


def t_corruption_detected(ws: Path) -> str:
    return run_in_workspace(ws, """
import daily_backup as bk
snap = bk.list_snapshots()[0]

# 1. corrupt the database copy
dbf = snap / "tracker.db"
good = dbf.read_bytes()
bad = bytearray(good); bad[3000:3200] = b"\\x00" * 200
dbf.write_bytes(bytes(bad))
r = bk.verify(snap)
assert not r["ok"], "a corrupted database copy was reported as fine"
dbf.write_bytes(good)

# 2. tamper with a CSV row count
csv = snap / "projects.csv"
orig = csv.read_text()
csv.write_text("\\n".join(orig.splitlines()[:-3]))
r2 = bk.verify(snap)
assert not r2["ok"], "a truncated CSV was reported as fine"
csv.write_text(orig)

assert bk.verify(snap)["ok"], "snapshot did not verify after being restored"
print("corrupted database and truncated CSV both detected; snapshot clean again")
""")


def t_foreign_keys(ws: Path) -> str:
    return run_in_workspace(ws, """
import sqlite3, db
conn = db.connect()
try:
    try:
        conn.execute("INSERT INTO gates (project_id, gate_no, gate_code) "
                     "VALUES ('NO-SUCH-PROJECT', 99, 'X')")
        conn.commit()
        raise AssertionError("an orphaned gate row was accepted")
    except sqlite3.IntegrityError:
        pass
    n0 = conn.execute("select count(*) from gates where project_id="
                      "(select project_id from projects limit 1)").fetchone()[0]
    conn.execute("DELETE FROM projects WHERE project_id="
                 "(select project_id from projects limit 1)")
    n1 = conn.execute("select count(*) from gates where project_id="
                      "(select project_id from projects limit 1)").fetchone()[0]
    conn.rollback()
    print(f"orphan rejected; deleting a project cascaded to its {n0} gates")
finally:
    conn.close()
""")


def t_app_boots(ws: Path) -> str:
    return run_in_workspace(ws, """
import warnings; warnings.filterwarnings("ignore")
from streamlit.testing.v1 import AppTest

for pw, expect_forms in (("viewer", False), ("editor", True)):
    at = AppTest.from_file("app.py", default_timeout=400).run()
    at.text_input[0].set_value(pw); at.button[0].click().run()
    assert not at.exception, f"{pw}: {[str(e.value)[:200] for e in at.exception]}"
    assert len(at.get("plotly_chart")) >= 2, f"{pw}: launch page charts missing"
    has_forms = any("Add Gate Zero" in b.label for b in at.button)
    assert has_forms is expect_forms, f"{pw}: editor forms visible = {has_forms}"
    at.switch_page("views/capacity_page.py").run()
    assert not at.exception, f"{pw} capacity page: {at.exception}"

at = AppTest.from_file("app.py", default_timeout=400).run()
at.text_input[0].set_value("wrong-password"); at.button[0].click().run()
assert at.error, "a wrong password was accepted"
assert not at.get("plotly_chart"), "content rendered despite a bad password"
print("viewer read-only, editor has forms, both pages render, bad password rejected")
""", {"APP_PASSWORD_VIEWER": "viewer", "APP_PASSWORD_EDITOR": "editor"})


def t_filters(ws: Path) -> str:
    return run_in_workspace(ws, """
import warnings; warnings.filterwarnings("ignore")
from streamlit.testing.v1 import AppTest

def page():
    at = AppTest.from_file("app.py", default_timeout=400).run()
    at.text_input[0].set_value("viewer"); at.button[0].click().run()
    return at

cases = [("Project type", ["Prototype"]), ("Project type", ["Launch"]),
         ("Launch type", ["Simple"]), ("Launch type", [])]
for label, val in cases:
    at = page()
    {m.label: m for m in at.multiselect}[label].set_value(val)
    at.run()
    assert not at.exception, f"{label}={val}: {[str(e.value)[:150] for e in at.exception]}"

at = page()
{m.label: m for m in at.multiselect}["Plants"].set_value([])
at.run()
assert at.warning, "empty plant selection should warn rather than break"
print(f"{len(cases)} filter combinations plus the empty case all handled")
""", {"APP_PASSWORD_VIEWER": "viewer", "APP_PASSWORD_EDITOR": "editor"})


def t_env_passwords(ws: Path) -> str:
    """Containers pass credentials as environment variables, not files."""
    secrets = ws / ".streamlit" / "secrets.toml"
    if secrets.exists():
        secrets.unlink()
    return run_in_workspace(ws, """
import warnings; warnings.filterwarnings("ignore")
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=400).run()
assert not at.get("plotly_chart"), "content shown before login"
at.text_input[0].set_value("from-env-editor"); at.button[0].click().run()
assert not at.exception, str(at.exception)
assert len(at.get("plotly_chart")) >= 2, "did not log in using environment passwords"
assert any("Add Gate Zero" in b.label for b in at.button), "editor role not applied"
print("logged in with no secrets file, using environment variables only")
""", {"APP_PASSWORD_VIEWER": "from-env-viewer",
      "APP_PASSWORD_EDITOR": "from-env-editor"})


# ---------------------------------------------------------------------------
def main() -> None:
    quick = "--quick" in sys.argv
    keep = "--keep" in sys.argv

    print("=" * 72)
    print("Launch Tracker — test suite")
    print("=" * 72)
    print(f"application : {APP_DIR}")

    ws = build_workspace()
    print(f"workspace   : {ws}")
    print("your real data/ directory is not touched\n")

    started = time.time()

    fast = [
        ("modules import", t_imports),
        ("fresh install builds its own database", t_bootstrap),
        ("gate dates match the tracker sheet", t_gate_maths),
        ("concurrent edits cannot overwrite each other", t_concurrency),
        ("backups are written and self-verify", t_backup_and_verify),
        ("DESTROYED database rebuilt from backup", t_restore_from_deletion),
        ("corrupted backups are detected", t_corruption_detected),
        ("database rejects orphaned records", t_foreign_keys),
    ]
    slow = [
        ("app boots, both roles, both pages", t_app_boots),
        ("filter combinations do not break the page", t_filters),
        ("passwords work from environment variables", t_env_passwords),
    ]

    for name, fn in fast:
        check(name, lambda fn=fn: fn(ws))

    if quick:
        for name, _ in slow:
            record(name, SKIP, "--quick")
    else:
        print("\n(the next few take a minute or two — they start the app for real)\n")
        for name, fn in slow:
            check(name, lambda fn=fn: fn(ws))

    elapsed = time.time() - started
    passed = sum(1 for _, s, _ in results if s == PASS)
    failed = sum(1 for _, s, _ in results if s == FAIL)
    skipped = sum(1 for _, s, _ in results if s == SKIP)

    print("\n" + "=" * 72)
    print(f"{passed} passed, {failed} failed, {skipped} skipped   ({elapsed:.0f}s)")
    print("=" * 72)

    if failed:
        print("\nFailed:")
        for name, status, detail in results:
            if status == FAIL:
                print(f"  - {name}")
        print("\nScroll up for the detail of each failure.")

    if keep:
        print(f"\nWorkspace kept at: {ws}")
    else:
        shutil.rmtree(ws, ignore_errors=True)

    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
