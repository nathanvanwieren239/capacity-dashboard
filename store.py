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

# Gate dates an editor may change. original_week is deliberately absent:
# it is the commitment the on-time metric is measured against, so it is
# write-once at creation. Slipping a date goes in adjusted_week, which keeps
# the slip visible instead of erasing it.
EDITABLE_GATE_FIELDS = ["adjusted_week", "actual_week"]


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


def update_gates(role: str, pid: str, edited: pd.DataFrame) -> list[str]:
    """
    Apply gate date changes for one project. `edited` must carry gate_no plus
    any of EDITABLE_GATE_FIELDS. original_week is ignored if present.
    """
    projects, gates = lm.load_bundled()
    audit, summary = [], []

    for _, new_row in edited.iterrows():
        gate_no = int(new_row["gate_no"])
        mask = (gates["project_id"] == pid) & (gates["gate_no"] == gate_no)
        if not mask.any():
            continue
        current = gates.loc[mask].iloc[0]

        for field in EDITABLE_GATE_FIELDS:
            if field not in new_row:
                continue
            new = new_row[field]
            new = pd.NA if pd.isna(new) else int(new)
            old = current[field]
            if pd.isna(old) and pd.isna(new):
                continue
            if not pd.isna(old) and not pd.isna(new) and int(old) == int(new):
                continue
            gates.loc[mask, field] = new
            label = f"{current['gate_code']}.{field}"
            audit.append(_entry(role, "edit", pid, label, old, new))
            summary.append(
                f"Gate {current['gate_code']} {field.replace('_', ' ')}: "
                f"{'—' if pd.isna(old) else int(old)} → "
                f"{'—' if pd.isna(new) else int(new)}"
            )

    if audit:
        _write(projects, gates)
        append_audit(audit)
    return summary
