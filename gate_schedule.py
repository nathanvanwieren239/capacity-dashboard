"""
The gate model, and the arithmetic that derives planned gate dates.

Gate sequence confirmed in review on 19 Aug 2026:

    FULL LAUNCH     0  Project Initiation   (kickoff, from the Gate Zero form)
                    1  Gate 1               kickoff + 1/3 of the way to PPAP
                    2  Gate 2               kickoff + 2/3 of the way to PPAP
                    3  Gate 3 — PPAP        the PPAP date itself
                    4  Gate 4 — SOP         SOP and project sign-off
                   6M  6 Month Review       SOP + 6 months

    SIMPLE LAUNCH   0, SL, 4, 6M
                    Skips gates 1-3. The Simple Launch form covers what
                    gates 1-3 would have, and lands on the PPAP date.
                    Gate 4 sign-off is still required.

    PROTOTYPE       0, S, R
                    PLACEHOLDER. The prototype route has no agreed gate
                    model yet; these are stand-ins.

Everything here works in real dates. Manufacturing weeks are gone.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

# gate_no, gate_code, gate_name, qa_lab_hours
FULL_LAUNCH_GATES = [
    (0, "0", "Project Initiation", 2.0),
    (1, "1", "Gate 1", 6.0),
    (2, "2", "Gate 2", 10.0),
    (3, "3", "Gate 3 — PPAP", 44.0),
    (4, "4", "Gate 4 — SOP", 8.0),
    (5, "6M", "6 Month Review", 4.0),
]

SIMPLE_LAUNCH_GATES = [
    (0, "0", "Project Initiation", 2.0),
    (2, "SL", "Simple Launch", 26.0),
    (4, "4", "Gate 4 — SOP", 6.0),
    (5, "6M", "6 Month Review", 4.0),
]

PROTOTYPE_GATES = [
    (0, "0", "Kickoff", 2.0),
    (2, "S", "Sample Build", 14.0),
    (4, "R", "Dimensional Report", 22.0),
]

SIX_MONTH_CODE = "6M"
PPAP_CODE = "3"
SOP_CODE = "4"

# Fractions of the kickoff-to-PPAP window where gates 1 and 2 land.
GATE_1_FRACTION = 1 / 3
GATE_2_FRACTION = 2 / 3


def gate_template(project_type: str, launch_type: str):
    if project_type == "Prototype":
        return PROTOTYPE_GATES
    return SIMPLE_LAUNCH_GATES if launch_type == "Simple" else FULL_LAUNCH_GATES


def _as_date(value) -> date | None:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return None
    if isinstance(value, date):
        return value
    ts = pd.to_datetime(value, errors="coerce")
    return None if pd.isna(ts) else ts.date()


def add_months(start: date, months: int) -> date:
    return (pd.Timestamp(start) + pd.DateOffset(months=months)).date()


def planned_dates(
    project_type: str,
    launch_type: str,
    gate_zero: date,
    ppap: date | None,
    sop: date | None,
) -> dict[str, date]:
    """
    Derive the planned date for every gate from the three dates captured on
    the Gate Zero form: kickoff, PPAP and SOP.

    Gate 1 sits one third of the way from kickoff to PPAP, gate 2 two thirds.
    Gate 3 is PPAP. Gate 4 is SOP. The 6 month review is SOP + 6 months.
    """
    gate_zero = _as_date(gate_zero)
    ppap = _as_date(ppap)
    sop = _as_date(sop)

    if gate_zero is None:
        raise ValueError("Gate Zero date is required to plan a schedule.")

    # Fall back sensibly so a half-filled form still produces a schedule.
    if ppap is None:
        ppap = sop - timedelta(days=30) if sop else gate_zero + timedelta(days=180)
    if sop is None:
        sop = ppap + timedelta(days=30)

    span = (ppap - gate_zero).days
    out: dict[str, date] = {
        "0": gate_zero,
        "1": gate_zero + timedelta(days=round(span * GATE_1_FRACTION)),
        "2": gate_zero + timedelta(days=round(span * GATE_2_FRACTION)),
        "3": ppap,
        "4": sop,
        "SL": ppap,
        "6M": add_months(sop, 6),
        # Prototype placeholders.
        "S": gate_zero + timedelta(days=round(span * 0.5)),
        "R": sop,
    }
    return {code: out[code] for _, code, _, _ in gate_template(project_type, launch_type)}


def build_gate_rows(
    project_id: str,
    project_type: str,
    launch_type: str,
    gate_zero: date,
    ppap: date | None,
    sop: date | None,
) -> list[dict]:
    """Full gate rows for a new project, with plan dates auto-calculated."""
    plan = planned_dates(project_type, launch_type, gate_zero, ppap, sop)
    rows = []
    for gate_no, code, name, qa_hours in gate_template(project_type, launch_type):
        rows.append(
            {
                "project_id": project_id,
                "gate_no": gate_no,
                "gate_code": code,
                "gate_name": name,
                "plan_date": plan[code],
                "adjusted_date": pd.NaT,
                "actual_date": pd.NaT,
                "qa_lab_hours": qa_hours,
            }
        )
    return rows
