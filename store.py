"""
Read/write store for the launch portfolio, plus an append-only audit log.

--------------------------------------------------------------------------
IMPORTANT - WHERE THIS PERSISTS
--------------------------------------------------------------------------
Writes go to CSV files in ./data. That is durable when the app runs on a
machine you control (your laptop, or an internal server).

It is NOT durable on Streamlit Community Cloud. That container is rebuilt on
every deploy and can be recycled at any time, and `data/*.csv` is gitignored
so a fresh container regenerates synthetic data. Edits made on the hosted
demo will disappear.

This is deliberate for the review build: it makes the entry and edit flow
real enough to demonstrate without pretending the hosting question is
settled. When the source of truth is decided - SharePoint Excel, a Google
Sheet, or an internal database - only this module needs to change. Nothing
in the page or the model layer touches files directly.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

import launch_data as ld
import launch_model as lm

DATA_DIR = Path(__file__).parent / "data"
PROJECTS_CSV = DATA_DIR / "projects.csv"
GATES_CSV = DATA_DIR / "gates.csv"
AUDIT_CSV = DATA_DIR / "audit_log.csv"

AUDIT_COLUMNS = [
    "timestamp",
    "role",
    "action",
    "project_id",
    "field",
    "old_value",
    "new_value",
]

# Fields an editor may change on an existing project.
EDITABLE_PROJECT_FIELDS = [
    "project_name",
    "plant",
    "program_manager",
    "job_number",
    "launch_type",
    "project_status",
    "sop_actual_week",
    "prr_count",
    "comments",
]

# Every gate column an editor may change, including the gate set itself.
#
# original_week is editable, but treat it as load-bearing: it is the
# commitment the on-time metric is measured against, so changing it rewrites
# history rather than recording a slip. Slips belong in adjusted_week. The
# audit log flags original_week edits separately so they stay visible.
GATE_EDIT_COLUMNS = [
    "gate_no",
    "gate_code",
    "gate_name",
    "original_week",
    "adjusted_week",
    "actual_week",
    "qa_lab_hours",
]

BASELINE_FIELD = "original_week"

_INT_GATE_FIELDS = ["gate_no", "original_week"]
_NULLABLE_INT_GATE_FIELDS = ["adjusted_week", "actual_week"]


# ---------------------------------------------------------------------------
# Audit log
# ---------------------------------------------------------------------------
def read_audit() -> pd.DataFrame:
    if not AUDIT_CSV.exists():
        return pd.DataFrame(columns=AUDIT_COLUMNS)
    return pd.read_csv(AUDIT_CSV).fillna("")


def append_audit(rows: list[dict]) -> None:
    if not rows:
        return
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=AUDIT_COLUMNS)
    header = not AUDIT_CSV.exists()
    df.to_csv(AUDIT_CSV, mode="a", header=header, index=False)


def _entry(role: str, action: str, pid: str, field: str, old, new) -> dict:
    return {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "role": role,
        "action": action,
        "project_id": pid,
        "field": field,
        "old_value": "" if pd.isna(old) else old,
        "new_value": "" if pd.isna(new) else new,
    }


# ---------------------------------------------------------------------------
# Writing
# ---------------------------------------------------------------------------
def _append(df: pd.DataFrame, rows: list[dict]) -> pd.DataFrame:
    """
    Append rows, first coercing the new frame to the existing dtypes.
    Appending an untyped frame that holds NA in a nullable-int column makes
    pandas warn about dtype inference; matching dtypes up front avoids it.
    """
    new = pd.DataFrame(rows, columns=df.columns)
    for col in df.columns:
        try:
            new[col] = new[col].astype(df[col].dtype)
        except (TypeError, ValueError):
            pass
    return pd.concat([df, new], ignore_index=True)


def _write(projects: pd.DataFrame, gates: pd.DataFrame) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    projects.to_csv(PROJECTS_CSV, index=False)
    gates.to_csv(GATES_CSV, index=False)


def next_project_id(projects: pd.DataFrame, is_prototype: bool) -> str:
    prefix = "P" if is_prototype else "L"
    nums = (
        projects["project_id"]
        .str.extract(r"-(\d+)$")[0]
        .dropna()
        .astype(int)
    )
    return f"{prefix}-{(int(nums.max()) + 7) if len(nums) else 1000}"


def create_project(
    *,
    role: str,
    project_name: str,
    project_type: str,
    launch_type: str,
    plant: str,
    program_manager: str,
    job_number: str,
    family: str,
    gate_zero_week: int,
    ppap_week: int | None,
    sop_week: int,
    comments: str,
) -> str:
    """
    Create a project and its gate rows from the standard template, so it
    appears on the dashboard immediately. Returns the new project_id.
    """
    projects, gates = lm.load_bundled()
    pid = next_project_id(projects, project_type == "Prototype")

    if project_type == "Prototype":
        template = ld.PROTOTYPE_GATES
    elif launch_type == "Simple":
        template = ld.SIMPLE_LAUNCH_GATES
    else:
        template = ld.FULL_LAUNCH_GATES

    # Space intermediate gates evenly between Gate 0 and SOP. PPAP, where the
    # template has one, is pinned to the date entered.
    n = len(template)
    span = max(sop_week - gate_zero_week, n - 1)
    new_gates = []
    for i, (gate_no, code, name, qa_hours) in enumerate(template):
        if i == 0:
            week = gate_zero_week
        elif i == n - 1:
            week = sop_week
        elif code == "P" and ppap_week:
            week = int(ppap_week)
        else:
            week = int(round(gate_zero_week + span * (i / (n - 1))))
        new_gates.append(
            {
                "project_id": pid,
                "gate_no": gate_no,
                "gate_code": code,
                "gate_name": name,
                "original_week": min(max(week, 1), 52),
                "adjusted_week": pd.NA,
                "actual_week": pd.NA,
                "qa_lab_hours": qa_hours,
            }
        )

    new_project = {
        "project_id": pid,
        "project_name": project_name,
        "project_type": project_type,
        "launch_type": launch_type,
        "family": family,
        "plant": plant,
        "program_manager": program_manager,
        "job_number": job_number,
        "customer": "",
        "sop_original_week": sop_week,
        "sop_actual_week": pd.NA,
        "project_status": "Green",
        "prr_count": 0,
        "comments": comments,
    }

    projects = _append(projects, [new_project])
    gates = _append(gates, new_gates)
    _write(projects, gates)

    append_audit(
        [
            _entry(role, "create", pid, "project_name", "", project_name),
            _entry(role, "create", pid, "gate_zero_week", "", gate_zero_week),
            _entry(role, "create", pid, "sop_original_week", "", sop_week),
        ]
    )
    return pid


def update_project(role: str, pid: str, changes: dict) -> list[str]:
    """Apply project-level field changes. Returns a list of change summaries."""
    projects, gates = lm.load_bundled()
    mask = projects["project_id"] == pid
    if not mask.any():
        raise KeyError(f"No project {pid}")

    row = projects.loc[mask].iloc[0]
    audit, summary = [], []

    for field, new in changes.items():
        if field not in EDITABLE_PROJECT_FIELDS:
            raise ValueError(f"{field} is not editable")
        old = row[field]
        if pd.isna(old) and pd.isna(new):
            continue
        if str(old) == str(new):
            continue
        projects.loc[mask, field] = new
        audit.append(_entry(role, "edit", pid, field, old, new))
        summary.append(f"{field}: {old!s} → {new!s}")

    if audit:
        _write(projects, gates)
        append_audit(audit)
    return summary


class ValidationError(ValueError):
    pass


def _clean_gate_frame(pid: str, edited: pd.DataFrame) -> pd.DataFrame:
    """Coerce the edited grid into storable rows, raising on bad input."""
    df = edited.copy()

    for col in GATE_EDIT_COLUMNS:
        if col not in df.columns:
            raise ValidationError(f"Gate grid is missing the {col} column.")

    # Drop rows the editor added but left empty.
    df = df.dropna(subset=["gate_no", "gate_code", "original_week"], how="all")
    if df.empty:
        raise ValidationError("A project must keep at least one gate.")

    for col in ["gate_no", "gate_code", "original_week"]:
        if df[col].isna().any():
            raise ValidationError(f"Every gate needs a {col.replace('_', ' ')}.")

    df["gate_code"] = df["gate_code"].astype(str).str.strip()
    df["gate_name"] = df["gate_name"].fillna("").astype(str).str.strip()
    if (df["gate_code"] == "").any():
        raise ValidationError("Gate code cannot be blank — it is the dot label.")

    for col in _INT_GATE_FIELDS:
        df[col] = df[col].astype(float).round().astype(int)
    for col in _NULLABLE_INT_GATE_FIELDS:
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

    df["qa_lab_hours"] = (
        pd.to_numeric(df["qa_lab_hours"], errors="coerce").fillna(0.0).astype(float)
    )

    if df["gate_no"].duplicated().any():
        dupes = sorted({int(v) for v in df.loc[df["gate_no"].duplicated(), "gate_no"]})
        raise ValidationError(
            "Gate number must be unique within a project. Duplicated: "
            + ", ".join(str(d) for d in dupes)
        )

    for col in ["original_week"] + _NULLABLE_INT_GATE_FIELDS:
        bad = df[col].dropna()
        if len(bad) and ((bad < 1) | (bad > 52)).any():
            raise ValidationError(f"{col.replace('_', ' ').title()} must be 1–52.")

    if (df["qa_lab_hours"] < 0).any():
        raise ValidationError("QA lab hours cannot be negative.")

    df["project_id"] = pid
    return df[["project_id"] + GATE_EDIT_COLUMNS].sort_values(
        "gate_no", ignore_index=True
    )


def replace_gates(role: str, pid: str, edited: pd.DataFrame) -> list[str]:
    """
    Replace the whole gate set for one project.

    Handles added rows, deleted rows and field edits. Every difference is
    audited; changes to original_week are logged as `baseline` so a rewritten
    commitment stays visible next to ordinary edits.
    """
    projects, gates = lm.load_bundled()
    new = _clean_gate_frame(pid, edited)

    current = gates[gates["project_id"] == pid].set_index("gate_no")
    incoming = new.set_index("gate_no")

    audit, summary = [], []

    removed = sorted(set(current.index) - set(incoming.index))
    for gate_no in removed:
        code = current.loc[gate_no, "gate_code"]
        audit.append(_entry(role, "delete", pid, f"gate {code}", code, ""))
        summary.append(f"Removed gate {code}")

    added = sorted(set(incoming.index) - set(current.index))
    for gate_no in added:
        row = incoming.loc[gate_no]
        audit.append(
            _entry(role, "create", pid, f"gate {row['gate_code']}", "",
                   f"wk {row['original_week']}")
        )
        summary.append(f"Added gate {row['gate_code']} at wk {row['original_week']}")

    for gate_no in sorted(set(current.index) & set(incoming.index)):
        old_row, new_row = current.loc[gate_no], incoming.loc[gate_no]
        for field in GATE_EDIT_COLUMNS:
            if field == "gate_no":
                continue
            old, new_val = old_row[field], new_row[field]
            if pd.isna(old) and pd.isna(new_val):
                continue
            if not pd.isna(old) and not pd.isna(new_val):
                if field == "qa_lab_hours":
                    if abs(float(old) - float(new_val)) < 0.05:
                        continue
                elif str(old) == str(new_val):
                    continue
            action = "baseline" if field == BASELINE_FIELD else "edit"
            label = f"{old_row['gate_code']}.{field}"
            audit.append(_entry(role, action, pid, label, old, new_val))
            shown_old = "—" if pd.isna(old) else old
            shown_new = "—" if pd.isna(new_val) else new_val
            prefix = "⚠ baseline " if action == "baseline" else ""
            summary.append(
                f"{prefix}Gate {old_row['gate_code']} "
                f"{field.replace('_', ' ')}: {shown_old} → {shown_new}"
            )

    if audit:
        others = gates[gates["project_id"] != pid]
        gates = pd.concat(
            [others, new.reindex(columns=others.columns)], ignore_index=True
        )
        for col in _NULLABLE_INT_GATE_FIELDS + ["gate_no", "original_week"]:
            gates[col] = pd.to_numeric(gates[col], errors="coerce").astype(
                "Int64" if col in _NULLABLE_INT_GATE_FIELDS else "int64"
            )
        _write(projects, gates)
        append_audit(audit)
    return summary


# Kept for callers that only touch dates.
def update_gates(role: str, pid: str, edited: pd.DataFrame) -> list[str]:
    return replace_gates(role, pid, edited)
