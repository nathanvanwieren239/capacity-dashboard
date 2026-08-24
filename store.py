"""
Read/write store for the launch portfolio, plus an append-only audit log.

Backed by SQLite (`data/tracker.db`). This module is the ONLY thing in the
application that writes data — the pages, charts and metrics all go through
it and cannot tell where rows are stored.

--------------------------------------------------------------------------
WHY SQLITE
--------------------------------------------------------------------------
The previous CSV store needed an advisory file lock, atomic temp-file
writes, and rolling backups to be safe with more than one editor. Those were
patches around the fact that text files have no notion of a transaction.

Here, each of the mutating functions below runs inside a single BEGIN
IMMEDIATE transaction. Two editors saving at the same moment serialise
correctly; a crash mid-write rolls back rather than truncating; and changing
one date updates one row instead of rewriting the whole dataset.

Backups still exist — a database does not protect you from importing the
wrong workbook and confirming it — but they now use SQLite's own backup API,
which is consistent even while the database is in use.

--------------------------------------------------------------------------
WHERE THIS PERSISTS
--------------------------------------------------------------------------
Durable on a machine you control. NOT durable on Streamlit Community Cloud,
where the container is rebuilt on every deploy. If containerised for an
internal server, `data/` must be a mounted volume.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd

import db
import gate_schedule as gs
import launch_model as lm
import safe_io

DATA_DIR = Path(__file__).parent / "data"

AUDIT_COLUMNS = db.AUDIT_COLUMNS

# Fields an editor may change on an existing project. Mirrors the Gate Zero
# form plus the tracker's own columns.
EDITABLE_PROJECT_FIELDS = [
    "project_name", "customer_part_number", "description",
    "plant", "div", "customer", "sales_person", "program_manager",
    "job_number", "qmsi_number", "qmsi_revision", "opportunity_number",
    "rpn", "peak_annual_sales", "launch_process", "support_required",
    "launch_risk", "qmsi_capex", "cer_amount", "cer_status", "cer_number",
    "launch_type", "project_status", "project_phase", "prr_count",
    "prr_amount_first_year", "gate_zero_date", "ppap_target_date",
    "sop_target_date", "notes",
]

# The three dates that drive every planned gate date.
SCHEDULE_SEED_FIELDS = ["gate_zero_date", "ppap_target_date", "sop_target_date"]

# Columns shown in the simple gate editor.
GATE_DATE_COLUMNS = ["plan_date", "adjusted_date", "actual_date"]

# Columns shown in the advanced editor, where the gate set itself changes.
GATE_EDIT_COLUMNS = [
    "gate_no", "gate_code", "gate_name",
    "plan_date", "adjusted_date", "actual_date", "qa_lab_hours",
]

BASELINE_FIELD = "plan_date"


class ValidationError(ValueError):
    pass


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def read_audit() -> pd.DataFrame:
    return db.read_audit().fillna("")


def append_audit(rows: list[dict]) -> None:
    if not rows:
        return
    with db.transaction() as conn:
        db.insert_audit(conn, rows)


def _fmt(v) -> str:
    # pd.NaT subclasses datetime, so the null check has to come first or an
    # empty date is written to the audit log as the string "NaT".
    if v is None:
        return ""
    try:
        if pd.isna(v):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(v, date):
        return v.isoformat()
    return str(v)


def _entry(role: str, action: str, pid: str, field: str, old, new) -> dict:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "role": role,
        "action": action,
        "project_id": pid,
        "field": field,
        "old_value": _fmt(old),
        "new_value": _fmt(new),
    }


# ---------------------------------------------------------------------------
# Reading inside a transaction
# ---------------------------------------------------------------------------
def _projects_in(conn) -> pd.DataFrame:
    return lm.normalise_projects(db.read_projects(conn))


def _gates_in(conn) -> pd.DataFrame:
    return lm.normalise_gates(db.read_gates(conn))


def next_project_id(projects: pd.DataFrame, is_prototype: bool) -> str:
    prefix = "P" if is_prototype else "L"
    nums = projects["project_id"].str.extract(r"-(\d+)$")[0].dropna().astype(int)
    return f"{prefix}-{(int(nums.max()) + 7) if len(nums) else 1000}"


# ---------------------------------------------------------------------------
# Mutations
# ---------------------------------------------------------------------------
def create_project(*, role: str, fields: dict) -> str:
    """
    Create a project and auto-calculate its whole gate schedule from the
    three Gate Zero dates. Returns the new project_id.
    """
    project_type = fields.get("project_type", "Launch")
    launch_type = fields.get("launch_type", "Full")
    if project_type == "Prototype":
        launch_type = "Prototype"

    gate_zero = fields.get("gate_zero_date")
    ppap = fields.get("ppap_target_date")
    sop = fields.get("sop_target_date")
    if not gate_zero:
        raise ValidationError("Gate Zero date is required.")
    if ppap and gate_zero and ppap < gate_zero:
        raise ValidationError("PPAP date cannot be before the Gate Zero date.")
    if sop and ppap and sop < ppap:
        raise ValidationError("SOP date cannot be before the PPAP date.")

    safe_io.backup(reason="create")

    with db.transaction() as conn:
        projects = _projects_in(conn)
        pid = next_project_id(projects, project_type == "Prototype")

        row = {c: "" for c in db.PROJECT_COLUMNS}
        row.update(
            {
                "project_id": pid,
                "project_type": project_type,
                "launch_type": launch_type,
                "project_status": "Green",
                "project_phase": "In-Process",
                "rpn": 0,
                "peak_annual_sales": 0.0,
                "qmsi_capex": 0.0,
                "cer_amount": 0.0,
                "prr_count": 0,
                "prr_amount_first_year": 0.0,
                "prr_start_date": None,
                "prr_end_date": None,
            }
        )
        for key, value in fields.items():
            if key in db.PROJECT_COLUMNS:
                row[key] = value
        if not row.get("project_name"):
            row["project_name"] = (
                f"{fields.get('customer_part_number','')} — "
                f"{fields.get('description','')}"
            ).strip(" —")

        db.insert_project(conn, row)
        for gate in gs.build_gate_rows(
            pid, project_type, launch_type, gate_zero, ppap, sop
        ):
            db.insert_gate(conn, gate)

        db.insert_audit(
            conn,
            [
                _entry(role, "create", pid, "project_name", "", row["project_name"]),
                _entry(role, "create", pid, "gate_zero_date", "", gate_zero),
                _entry(role, "create", pid, "ppap_target_date", "", ppap),
                _entry(role, "create", pid, "sop_target_date", "", sop),
            ],
        )
    return pid


def update_project(role: str, pid: str, changes: dict) -> list[str]:
    """Apply project-level field changes. Returns a list of change summaries."""
    for field in changes:
        if field not in EDITABLE_PROJECT_FIELDS:
            raise ValidationError(f"{field} is not editable")

    safe_io.backup(reason="edit")

    with db.transaction() as conn:
        projects = _projects_in(conn)
        match = projects[projects["project_id"] == pid]
        if match.empty:
            raise KeyError(f"No project {pid}")
        current = match.iloc[0]

        applied, audit, summary = {}, [], []
        for field, new in changes.items():
            old = current[field]
            if _fmt(old) == _fmt(new):
                continue
            applied[field] = new
            action = "seed" if field in SCHEDULE_SEED_FIELDS else "edit"
            audit.append(_entry(role, action, pid, field, old, new))
            summary.append(f"{field}: {_fmt(old) or '—'} → {_fmt(new) or '—'}")

        if applied:
            db.update_project_fields(conn, pid, applied)
            db.insert_audit(conn, audit)
    return summary


def replan_gates(role: str, pid: str) -> list[str]:
    """
    Recalculate every gate's PLAN date from the project's Gate Zero, PPAP and
    SOP dates. Adjusted and Actual dates are left untouched — this resets the
    auto-calculated baseline, not the record of what happened.
    """
    safe_io.backup(reason="replan")

    with db.transaction() as conn:
        projects = _projects_in(conn)
        match = projects[projects["project_id"] == pid]
        if match.empty:
            raise KeyError(f"No project {pid}")
        p = match.iloc[0]

        if pd.isna(p["gate_zero_date"]):
            raise ValidationError("This project has no Gate Zero date to plan from.")

        plan = gs.planned_dates(
            p["project_type"], p["launch_type"],
            p["gate_zero_date"], p["ppap_target_date"], p["sop_target_date"],
        )

        gates = _gates_in(conn)
        audit, summary = [], []
        for _, g in gates[gates["project_id"] == pid].iterrows():
            code = g["gate_code"]
            if code not in plan:
                continue
            old, new = g["plan_date"], plan[code]
            if _fmt(old) == _fmt(new):
                continue
            db.update_gate_fields(conn, pid, int(g["gate_no"]), {"plan_date": new})
            audit.append(_entry(role, "replan", pid, f"{code}.plan_date", old, new))
            summary.append(f"Gate {code} plan: {_fmt(old) or '—'} → {_fmt(new)}")

        if audit:
            db.insert_audit(conn, audit)
    return summary


def _coerce_gate_frame(pid: str, edited: pd.DataFrame, full: bool) -> pd.DataFrame:
    df = edited.copy()
    required = GATE_EDIT_COLUMNS if full else ["gate_no"] + GATE_DATE_COLUMNS
    for col in required:
        if col not in df.columns:
            raise ValidationError(f"Gate grid is missing the {col} column.")

    if full:
        df = df.dropna(subset=["gate_no", "gate_code"], how="all")
        if df.empty:
            raise ValidationError("A project must keep at least one gate.")
        if df["gate_no"].isna().any() or df["gate_code"].isna().any():
            raise ValidationError("Every gate needs an order number and a code.")
        df["gate_code"] = df["gate_code"].astype(str).str.strip()
        df["gate_name"] = df["gate_name"].fillna("").astype(str).str.strip()
        if (df["gate_code"] == "").any():
            raise ValidationError("Gate code cannot be blank — it is the dot label.")
        df["gate_no"] = df["gate_no"].astype(float).round().astype(int)
        if df["gate_no"].duplicated().any():
            dupes = sorted({int(v) for v in df.loc[df["gate_no"].duplicated(), "gate_no"]})
            raise ValidationError(
                "Gate order must be unique. Duplicated: "
                + ", ".join(str(d) for d in dupes)
            )
        df["qa_lab_hours"] = (
            pd.to_numeric(df["qa_lab_hours"], errors="coerce").fillna(0.0).astype(float)
        )
        if (df["qa_lab_hours"] < 0).any():
            raise ValidationError("QA lab hours cannot be negative.")
    else:
        df["gate_no"] = df["gate_no"].astype(float).round().astype(int)

    for col in GATE_DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce").dt.date

    if df["plan_date"].isna().any():
        raise ValidationError("Every gate needs a plan date.")

    df["project_id"] = pid
    return df.sort_values("gate_no", ignore_index=True)


def save_gate_dates(role: str, pid: str, edited: pd.DataFrame) -> list[str]:
    """Update Plan / Adjusted / Actual for existing gates. No add or remove."""
    new = _coerce_gate_frame(pid, edited, full=False).set_index("gate_no")

    safe_io.backup(reason="gate-dates")

    with db.transaction() as conn:
        gates = _gates_in(conn)
        audit, summary = [], []

        for _, g in gates[gates["project_id"] == pid].iterrows():
            gate_no = int(g["gate_no"])
            if gate_no not in new.index:
                continue
            applied = {}
            for field in GATE_DATE_COLUMNS:
                old, new_val = g[field], new.loc[gate_no, field]
                if _fmt(old) == _fmt(new_val):
                    continue
                applied[field] = new_val
                action = "baseline" if field == BASELINE_FIELD else "edit"
                audit.append(
                    _entry(role, action, pid, f"{g['gate_code']}.{field}", old, new_val)
                )
                prefix = "⚠ plan " if action == "baseline" else ""
                summary.append(
                    f"{prefix}Gate {g['gate_code']} {field.replace('_date','')}: "
                    f"{_fmt(old) or '—'} → {_fmt(new_val) or '—'}"
                )
            if applied:
                db.update_gate_fields(conn, pid, gate_no, applied)

        if audit:
            db.insert_audit(conn, audit)
    return summary


def replace_gates(role: str, pid: str, edited: pd.DataFrame) -> list[str]:
    """Advanced: replace the whole gate set, handling adds and removals."""
    new = _coerce_gate_frame(pid, edited, full=True)

    safe_io.backup(reason="gate-structure")

    with db.transaction() as conn:
        gates = _gates_in(conn)
        current = gates[gates["project_id"] == pid].set_index("gate_no")
        incoming = new.set_index("gate_no")
        audit, summary = [], []

        removed = sorted(set(current.index) - set(incoming.index))
        for gate_no in removed:
            code = current.loc[gate_no, "gate_code"]
            audit.append(_entry(role, "delete", pid, f"gate {code}", code, ""))
            summary.append(f"Removed gate {code}")
        db.delete_gates(conn, pid, removed)

        for gate_no in sorted(set(incoming.index) - set(current.index)):
            row = incoming.loc[gate_no]
            payload = {c: row.get(c) for c in db.GATE_COLUMNS if c in row}
            payload.update({"project_id": pid, "gate_no": int(gate_no)})
            payload.setdefault("status_override", "")
            db.insert_gate(conn, payload)
            audit.append(
                _entry(role, "create", pid, f"gate {row['gate_code']}", "",
                       row["plan_date"])
            )
            summary.append(
                f"Added gate {row['gate_code']} on {_fmt(row['plan_date'])}"
            )

        for gate_no in sorted(set(current.index) & set(incoming.index)):
            old_row, new_row = current.loc[gate_no], incoming.loc[gate_no]
            applied = {}
            for field in GATE_EDIT_COLUMNS:
                if field == "gate_no":
                    continue
                old, new_val = old_row[field], new_row[field]
                if field == "qa_lab_hours":
                    if abs(float(old or 0) - float(new_val or 0)) < 0.05:
                        continue
                elif _fmt(old) == _fmt(new_val):
                    continue
                applied[field] = new_val
                action = "baseline" if field == BASELINE_FIELD else "edit"
                audit.append(
                    _entry(role, action, pid, f"{old_row['gate_code']}.{field}",
                           old, new_val)
                )
                summary.append(
                    f"Gate {old_row['gate_code']} {field.replace('_', ' ')}: "
                    f"{_fmt(old) or '—'} → {_fmt(new_val) or '—'}"
                )
            if applied:
                db.update_gate_fields(conn, pid, int(gate_no), applied)

        if audit:
            db.insert_audit(conn, audit)
    return summary


# ---------------------------------------------------------------------------
# Export - the data stays reachable in Excel
# ---------------------------------------------------------------------------
def export_csv() -> dict[str, bytes]:
    """
    Current contents as CSV bytes, for download.

    A database is not openable in Excel, which was the one real cost of
    moving off files. This gives the data back without giving up transactions.
    """
    projects, gates = lm.load_bundled()
    return {
        "projects.csv": projects.to_csv(index=False).encode(),
        "gates.csv": gates.to_csv(index=False).encode(),
        "audit_log.csv": read_audit().to_csv(index=False).encode(),
    }
