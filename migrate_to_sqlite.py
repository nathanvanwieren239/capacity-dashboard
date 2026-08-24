"""
One-time migration: CSV files -> SQLite.

    python migrate_to_sqlite.py            # migrate data/*.csv into data/tracker.db
    python migrate_to_sqlite.py --verify   # check an existing database matches the CSVs

Kept in the repo after the migration so the conversion is reproducible and
auditable, not a thing that happened once on somebody's laptop.

The CSVs are left untouched. Delete them only once the database has been in
use long enough to trust.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

import db
import launch_model as lm

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_CSV = DATA_DIR / "projects.csv"
GATES_CSV = DATA_DIR / "gates.csv"
AUDIT_CSV = DATA_DIR / "audit_log.csv"


def _checksum(df: pd.DataFrame, columns: list[str]) -> str:
    """Order-independent fingerprint of the values that matter."""
    present = [c for c in columns if c in df.columns]
    if df.empty:
        return "empty"
    normalised = (
        df[present]
        .astype(str)
        .apply(lambda col: col.str.strip().replace({"None": "", "NaT": "", "nan": ""}))
    )
    rows = sorted(normalised.agg("|".join, axis=1).tolist())
    return str(hash(tuple(rows)))


KEY_PROJECT_FIELDS = [
    "project_id", "project_name", "plant", "launch_type", "program_manager",
    "gate_zero_date", "ppap_target_date", "sop_target_date", "project_status",
]
KEY_GATE_FIELDS = [
    "project_id", "gate_no", "gate_code", "plan_date", "adjusted_date",
    "actual_date",
]


def verify() -> bool:
    """Compare the database against the CSVs. Returns True if they match."""
    if not (PROJECTS_CSV.exists() and GATES_CSV.exists()):
        print("No CSVs to compare against — nothing to verify.")
        return True

    csv_projects = lm.load_projects(PROJECTS_CSV)
    csv_gates = lm.load_gates(GATES_CSV)
    db_projects = lm.normalise_projects(db.read_projects())
    db_gates = lm.normalise_gates(db.read_gates())

    ok = True

    print(f"projects  csv={len(csv_projects):>5}  db={len(db_projects):>5}", end="  ")
    if len(csv_projects) != len(db_projects):
        print("MISMATCH")
        ok = False
    else:
        print("ok")

    print(f"gates     csv={len(csv_gates):>5}  db={len(db_gates):>5}", end="  ")
    if len(csv_gates) != len(db_gates):
        print("MISMATCH")
        ok = False
    else:
        print("ok")

    for label, a, b, fields in (
        ("projects", csv_projects, db_projects, KEY_PROJECT_FIELDS),
        ("gates", csv_gates, db_gates, KEY_GATE_FIELDS),
    ):
        ca, cb = _checksum(a, fields), _checksum(b, fields)
        print(f"{label} checksum", "ok" if ca == cb else f"MISMATCH ({ca} vs {cb})")
        if ca != cb:
            ok = False
            missing = set(a["project_id"]) - set(b["project_id"])
            extra = set(b["project_id"]) - set(a["project_id"])
            if missing:
                print("  in CSV but not DB:", sorted(missing)[:10])
            if extra:
                print("  in DB but not CSV:", sorted(extra)[:10])

    return ok


def migrate() -> None:
    if not (PROJECTS_CSV.exists() and GATES_CSV.exists()):
        raise SystemExit(
            "No projects.csv / gates.csv found in data/. Nothing to migrate.\n"
            "If this is a fresh install, just run the app — it will build the "
            "database from generated data."
        )

    projects = lm.load_projects(PROJECTS_CSV)
    gates = lm.load_gates(GATES_CSV)
    print(f"read {len(projects)} projects and {len(gates)} gates from CSV")

    # Gates whose project is missing would be rejected by the foreign key.
    known = set(projects["project_id"])
    orphans = gates[~gates["project_id"].isin(known)]
    if len(orphans):
        print(
            f"  dropping {len(orphans)} orphaned gate rows referencing missing "
            f"projects: {sorted(set(orphans['project_id']))[:5]}"
        )
        gates = gates[gates["project_id"].isin(known)]

    db.replace_all(projects, gates)
    print(f"wrote {db.DB_PATH}")

    if AUDIT_CSV.exists():
        audit = pd.read_csv(AUDIT_CSV).fillna("")
        if len(audit):
            with db.transaction() as conn:
                db.insert_audit(conn, audit.to_dict("records"))
            print(f"carried over {len(audit)} audit entries")

    print()
    if verify():
        print("\nverified: database matches the CSVs")
        print("CSVs left in place. Remove them once you are happy.")
    else:
        raise SystemExit("\nVERIFICATION FAILED — database does not match the CSVs")


if __name__ == "__main__":
    if "--verify" in sys.argv:
        raise SystemExit(0 if verify() else 1)
    migrate()
