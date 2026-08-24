"""
SQLite access for the launch tracker.

Replaces the CSV files. One file, `data/tracker.db`, no server, nothing for
IT to install — SQLite ships with Python.

What this buys over CSVs:

- **Transactions.** A group of changes either all commit or none do. The
  lost-update and torn-write problems that `safe_io` patched around are
  structurally impossible here rather than defended against.
- **Targeted writes.** Changing one date updates one row instead of
  rewriting both entire files.
- **Referential integrity.** A gate cannot point at a project that is not
  there, and deleting a project removes its gates.
- **Queryability.** Questions can be asked in SQL instead of needing new
  Python each time.

Concurrency notes: WAL mode lets readers continue while a write is in
progress, and `BEGIN IMMEDIATE` takes the write lock up front so two
concurrent read-modify-writes serialise instead of one failing late. A
`busy_timeout` makes waiters queue rather than error.
"""

from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path

import pandas as pd

APP_DIR = Path(__file__).parent
DATA_DIR = APP_DIR / "data"
DB_PATH = DATA_DIR / "tracker.db"
SCHEMA_PATH = APP_DIR / "schema.sql"

BUSY_TIMEOUT_MS = 15_000

PROJECT_COLUMNS = [
    "project_id", "project_name", "customer_part_number", "description",
    "project_type", "launch_type", "family", "plant", "div", "customer",
    "sales_person", "gate_zero_corp", "program_manager", "job_number",
    "qmsi_number", "qmsi_revision", "opportunity_number", "rpn",
    "peak_annual_sales", "launch_process", "support_required", "launch_risk",
    "qmsi_capex", "cer_amount", "cer_status", "cer_number",
    "gate_zero_date", "ppap_target_date", "sop_target_date",
    "project_status", "project_phase", "prr_count", "prr_amount_first_year",
    "prr_start_date", "prr_end_date", "main_risk_comments", "notes",
]

GATE_COLUMNS = [
    "project_id", "gate_no", "gate_code", "gate_name",
    "plan_date", "adjusted_date", "actual_date", "qa_lab_hours",
    "status_override",
]

AUDIT_COLUMNS = [
    "timestamp", "role", "action", "project_id", "field", "old_value", "new_value",
]

DATE_FIELDS_PROJECT = [
    "gate_zero_date", "ppap_target_date", "sop_target_date",
    "prr_start_date", "prr_end_date",
]
DATE_FIELDS_GATE = ["plan_date", "adjusted_date", "actual_date"]


def connect(path: Path | None = None) -> sqlite3.Connection:
    """Open a connection with the pragmas this app depends on."""
    target = Path(path) if path else DB_PATH
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=BUSY_TIMEOUT_MS / 1000)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA synchronous = FULL")
    conn.execute(f"PRAGMA busy_timeout = {BUSY_TIMEOUT_MS}")
    return conn


def init(path: Path | None = None) -> None:
    """Create tables if they do not exist. Safe to call repeatedly."""
    conn = connect(path)
    try:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
        conn.commit()
    finally:
        conn.close()


@contextmanager
def transaction(path: Path | None = None):
    """
    Run a read-modify-write as one unit.

    BEGIN IMMEDIATE claims the write lock at the start rather than on first
    write, so two concurrent editors queue instead of one discovering the
    conflict after it has already computed its changes. Commit on success,
    roll back on any exception.
    """
    conn = connect(path)
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
    except Exception:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        conn.close()


def exists(path: Path | None = None) -> bool:
    target = Path(path) if path else DB_PATH
    if not target.exists():
        return False
    conn = connect(target)
    try:
        row = conn.execute(
            "SELECT count(*) AS n FROM sqlite_master "
            "WHERE type='table' AND name='projects'"
        ).fetchone()
        return bool(row["n"])
    finally:
        conn.close()


def is_empty(path: Path | None = None) -> bool:
    if not exists(path):
        return True
    conn = connect(path)
    try:
        return conn.execute("SELECT count(*) AS n FROM projects").fetchone()["n"] == 0
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def _read(conn, sql: str, columns: list[str]) -> pd.DataFrame:
    df = pd.read_sql_query(sql, conn)
    for col in columns:
        if col not in df.columns:
            df[col] = None
    return df[columns]


def read_projects(conn=None) -> pd.DataFrame:
    own = conn is None
    conn = conn or connect()
    try:
        return _read(conn, "SELECT * FROM projects ORDER BY project_id", PROJECT_COLUMNS)
    finally:
        if own:
            conn.close()


def read_gates(conn=None) -> pd.DataFrame:
    own = conn is None
    conn = conn or connect()
    try:
        return _read(
            conn,
            "SELECT * FROM gates ORDER BY project_id, gate_no",
            GATE_COLUMNS,
        )
    finally:
        if own:
            conn.close()


def read_audit(conn=None, limit: int | None = None) -> pd.DataFrame:
    own = conn is None
    conn = conn or connect()
    try:
        sql = "SELECT * FROM audit_log ORDER BY id"
        if limit:
            sql = (
                "SELECT * FROM (SELECT * FROM audit_log ORDER BY id DESC "
                f"LIMIT {int(limit)}) ORDER BY id"
            )
        return _read(conn, sql, AUDIT_COLUMNS)
    finally:
        if own:
            conn.close()


# ---------------------------------------------------------------------------
# Writing helpers
# ---------------------------------------------------------------------------
def _sql_value(v):
    """Coerce a pandas/py value into something sqlite3 will accept."""
    if v is None:
        return None
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if hasattr(v, "isoformat"):
        return pd.Timestamp(v).date().isoformat()
    if isinstance(v, (pd.Int64Dtype.type, )):  # pragma: no cover
        return int(v)
    if hasattr(v, "item"):  # numpy scalar
        return v.item()
    return v


def insert_project(conn, row: dict) -> None:
    values = {c: _sql_value(row.get(c)) for c in PROJECT_COLUMNS}
    for col in PROJECT_COLUMNS:
        if col not in DATE_FIELDS_PROJECT and values[col] is None:
            values[col] = 0 if col in ("rpn", "prr_count") else (
                0.0 if col in (
                    "peak_annual_sales", "qmsi_capex", "cer_amount",
                    "prr_amount_first_year",
                ) else ""
            )
    placeholders = ", ".join(f":{c}" for c in PROJECT_COLUMNS)
    conn.execute(
        f"INSERT INTO projects ({', '.join(PROJECT_COLUMNS)}) VALUES ({placeholders})",
        values,
    )


def update_project_fields(conn, project_id: str, changes: dict) -> None:
    if not changes:
        return
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    params = {k: _sql_value(v) for k, v in changes.items()}
    params["_pid"] = project_id
    conn.execute(f"UPDATE projects SET {sets} WHERE project_id = :_pid", params)


def insert_gate(conn, row: dict) -> None:
    values = {c: _sql_value(row.get(c)) for c in GATE_COLUMNS}
    for col in ("gate_name", "status_override"):
        values[col] = values[col] or ""
    values["qa_lab_hours"] = values["qa_lab_hours"] or 0.0
    placeholders = ", ".join(f":{c}" for c in GATE_COLUMNS)
    conn.execute(
        f"INSERT OR REPLACE INTO gates ({', '.join(GATE_COLUMNS)}) "
        f"VALUES ({placeholders})",
        values,
    )


def update_gate_fields(conn, project_id: str, gate_no: int, changes: dict) -> None:
    if not changes:
        return
    sets = ", ".join(f"{k} = :{k}" for k in changes)
    params = {k: _sql_value(v) for k, v in changes.items()}
    params["_pid"] = project_id
    params["_gno"] = int(gate_no)
    conn.execute(
        f"UPDATE gates SET {sets} WHERE project_id = :_pid AND gate_no = :_gno",
        params,
    )


def delete_gates(conn, project_id: str, gate_nos: list[int] | None = None) -> None:
    if gate_nos is None:
        conn.execute("DELETE FROM gates WHERE project_id = ?", (project_id,))
        return
    if not gate_nos:
        return
    marks = ", ".join("?" for _ in gate_nos)
    conn.execute(
        f"DELETE FROM gates WHERE project_id = ? AND gate_no IN ({marks})",
        [project_id, *[int(n) for n in gate_nos]],
    )


def insert_audit(conn, rows: list[dict]) -> None:
    if not rows:
        return
    conn.executemany(
        "INSERT INTO audit_log (timestamp, role, action, project_id, field, "
        "old_value, new_value) VALUES (:timestamp, :role, :action, "
        ":project_id, :field, :old_value, :new_value)",
        [{c: (r.get(c) if r.get(c) is not None else "") for c in AUDIT_COLUMNS}
         for r in rows],
    )


def replace_all(projects: pd.DataFrame, gates: pd.DataFrame, path: Path | None = None) -> None:
    """
    Wholesale replacement, used by the workbook importer and the migration.
    Runs in one transaction: either the whole new dataset lands or none of it.
    """
    init(path)
    with transaction(path) as conn:
        conn.execute("DELETE FROM gates")
        conn.execute("DELETE FROM projects")
        for row in projects.to_dict("records"):
            insert_project(conn, row)
        for row in gates.to_dict("records"):
            insert_gate(conn, row)


def backup_to(target: Path, path: Path | None = None) -> Path:
    """
    Consistent snapshot using SQLite's own backup API.

    Copying the file with the filesystem can catch it mid-transaction or miss
    the WAL. This cannot.
    """
    target = Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    source = connect(path)
    dest = sqlite3.connect(target)
    try:
        source.backup(dest)
    finally:
        dest.close()
        source.close()
    return target
