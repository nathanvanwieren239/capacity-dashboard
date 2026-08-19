"""
Synthetic launch / prototype portfolio data.

Writes two CSVs into ./data. PLACEHOLDERS - swap for the real tracker export.
Everything here is invented: no real part numbers, customers or people.

Gate model follows the process described in review:
    Gate 0   project kickoff, entered when the project is created
    Gate 1
    Gate 2
    Gate 3   typically closed when parts are fed back
    PPAP     submission milestone
    Gate 4   SOP and project sign-off

A SIMPLE LAUNCH skips gates 1-3 and starts at PPAP, but still requires
Gate 4 sign-off. Used for part families where one part gets a full launch
and the rest follow as simple launches on the same timeline.

--------------------------------------------------------------------------
projects.csv  - one row per project
--------------------------------------------------------------------------
    project_id        str
    project_name      str
    project_type      str    Launch | Prototype
    launch_type       str    Full | Simple | n/a   (n/a for prototypes)
    family            str    part family, blank if standalone
    plant             str    Kentwood | Marshall
    program_manager   str
    job_number        str
    customer          str
    sop_original_week int    originally committed SOP
    sop_actual_week   int    blank until launched
    project_status    str    Green | Yellow | Red  (manually assessed)
    prr_count         int    PRRs in the first 12 months after SOP
    comments          str

--------------------------------------------------------------------------
gates.csv  - one row per project per gate
--------------------------------------------------------------------------
    project_id        str
    gate_no           int    sort order
    gate_code         str    label shown in the dot: 0,1,2,3,P,4
    gate_name         str
    original_week     int    first committed date
    adjusted_week     int    revised date, blank if never moved
    actual_week       int    completion, blank if still open
    qa_lab_hours      float  QA / metrology lab hours this gate consumes

Gate status is DERIVED from these dates, not stored:
    complete    actual_week present
    behind      open and due week has passed
    in progress open and due week still ahead
Due week = adjusted_week if present, else original_week.

On-time is measured against ORIGINAL_WEEK. Measuring against the adjusted
date would let a slipped project stay green by moving its own target.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

YEAR = 2026
SEED = 33
CURRENT_WEEK = 33

DATA_DIR = Path(__file__).parent / "data"

# (gate_no, gate_code, gate_name, qa_lab_hours)
FULL_LAUNCH_GATES = [
    (0, "0", "Gate 0 — Kickoff", 2.0),
    (1, "1", "Gate 1", 6.0),
    (2, "2", "Gate 2", 10.0),
    (3, "3", "Gate 3 — Parts Fed Back", 20.0),
    (4, "P", "PPAP Submission", 44.0),
    (5, "4", "Gate 4 — SOP Sign-off", 8.0),
]

# Simple launch: skips 1-3, still needs PPAP and Gate 4.
SIMPLE_LAUNCH_GATES = [
    (0, "0", "Gate 0 — Kickoff", 2.0),
    (4, "P", "PPAP Submission", 26.0),
    (5, "4", "Gate 4 — SOP Sign-off", 6.0),
]

PROTOTYPE_GATES = [
    (0, "0", "Gate 0 — Kickoff", 2.0),
    (2, "S", "Sample Build", 14.0),
    (5, "R", "Dimensional Report", 22.0),
]

PLANTS = ["Kentwood", "Marshall"]

# Placeholder rosters - replace with the real ones.
PMS = ["Alvarez", "Booker", "Chen", "Duval"]
CUSTOMERS = ["Customer A", "Customer B", "Customer C", "Customer D"]

# A part family demonstrating the simple-launch pattern: one full launch,
# the rest follow as simple launches on the same timeline.
FAMILY_NAME = "Series-7 Pin"
FAMILY_VARIANTS = ["Bent", "Straight", "Short", "Long", "Stepped"]
FAMILY_FULL = 2  # first two variants get a full PPAP

STANDALONE_LAUNCHES = [
    "Injector Body 4412", "Pump Shaft 7130", "Valve Sleeve 2208",
    "Rotor Hub 9051", "Common Rail 5514", "Planet Pin 6620",
    "Turbo Spindle 3307", "Bearing Race 8140",
]

# Already launched - these carry the PRR counts and the on-time launch metric.
LAUNCHED = [
    "Output Shaft 3021", "Idler Pin 5540", "Sleeve Bearing 1190",
    "Thrust Washer 7702", "Spline Adapter 6318",
]

PROTOTYPES = [
    "Copper Busbar Pin", "Copper Rotor Slug",
    "Thin-Wall Sleeve Trial", "Hardened Pin Trial",
]

# Deliberate demo signals worth discussing in review.
PPAP_PILEUP_WEEK = 38   # family PPAPs all land together
OVERLOADED_PM = "Chen"
SLIP_WINDOW = 6         # a gate older than this would have been escalated


def _gates_for(project_type: str, launch_type: str):
    if project_type == "Prototype":
        return PROTOTYPE_GATES
    return SIMPLE_LAUNCH_GATES if launch_type == "Simple" else FULL_LAUNCH_GATES


def _build_gate_rows(
    rng: np.random.Generator,
    pid: str,
    template,
    start_week: int,
    end_week: int,
    pin_ppap_week: int | None = None,
    force_complete: bool = False,
) -> list[dict]:
    """
    pin_ppap_week   forces the PPAP milestone onto a specific week, used to
                    make a part family submit together the way it does in
                    practice.
    force_complete  every gate closed, for projects already launched.
    """
    rows = []
    span = max(end_week - start_week, len(template))
    n = len(template)

    for i, (gate_no, code, name, qa_hours) in enumerate(template):
        if i == 0:
            original = start_week
        elif i == n - 1:
            original = end_week
        elif code == "P" and pin_ppap_week is not None:
            original = pin_ppap_week
        else:
            frac = i / (n - 1)
            original = int(round(start_week + span * frac + rng.uniform(-1.5, 1.5)))
        original = min(max(original, 1), 52)

        # Some gates get pushed. Adjusted dates are what make the on-time
        # metric interesting - and why edit access is restricted.
        adjusted = None
        if rng.random() < (0.15 if force_complete else 0.30):
            adjusted = min(original + int(rng.integers(1, 4)), 52)
            # A pinned PPAP is a hard customer date; it does not drift.
            if code == "P" and pin_ppap_week is not None:
                adjusted = None

        due = adjusted if adjusted is not None else original

        actual = None
        if force_complete:
            actual = min(max(due + int(rng.integers(-2, 2)), 1), CURRENT_WEEK)
        elif due < CURRENT_WEEK:
            recently_due = due >= CURRENT_WEEK - SLIP_WINDOW
            if not (recently_due and rng.random() < 0.25):
                actual = min(max(due + int(rng.integers(-1, 3)), 1), CURRENT_WEEK)

        rows.append(
            {
                "project_id": pid,
                "gate_no": gate_no,
                "gate_code": code,
                "gate_name": name,
                "original_week": original,
                "adjusted_week": adjusted,
                "actual_week": actual,
                "qa_lab_hours": round(qa_hours * float(rng.uniform(0.85, 1.15)), 1),
            }
        )
    return rows


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)

    specs: list[dict] = []

    # --- the part family -------------------------------------------------
    # One or two variants take a full launch; the rest follow as simple
    # launches on the same timeline, all submitting PPAP together.
    for i, variant in enumerate(FAMILY_VARIANTS):
        specs.append(
            {
                "name": f"{FAMILY_NAME} — {variant}",
                "project_type": "Launch",
                "launch_type": "Full" if i < FAMILY_FULL else "Simple",
                "family": FAMILY_NAME,
                "end_week": PPAP_PILEUP_WEEK + 3,
                "span": 26,
                "pin_ppap": PPAP_PILEUP_WEEK,
                "complete": False,
            }
        )

    # --- already launched, so the scorecard has something in it ----------
    for name in LAUNCHED:
        specs.append(
            {
                "name": name,
                "project_type": "Launch",
                "launch_type": "Full",
                "family": "",
                "end_week": int(rng.integers(10, CURRENT_WEEK - 3)),
                "span": int(rng.integers(20, 28)),
                "pin_ppap": None,
                "complete": True,
            }
        )

    # --- standalone launches ---------------------------------------------
    for name in STANDALONE_LAUNCHES:
        specs.append(
            {
                "name": name,
                "project_type": "Launch",
                "launch_type": "Simple" if rng.random() < 0.25 else "Full",
                "family": "",
                "end_week": int(rng.integers(CURRENT_WEEK + 3, 53)),
                "span": int(rng.integers(20, 32)),
                "pin_ppap": None,
                "complete": False,
            }
        )

    # --- prototypes ------------------------------------------------------
    for name in PROTOTYPES:
        specs.append(
            {
                "name": name,
                "project_type": "Prototype",
                "launch_type": "n/a",
                "family": "",
                "end_week": int(rng.integers(CURRENT_WEEK + 2, 48)),
                "span": int(rng.integers(8, 14)),
                "pin_ppap": None,
                "complete": False,
            }
        )

    projects: list[dict] = []
    gates: list[dict] = []

    for i, spec in enumerate(specs):
        is_proto = spec["project_type"] == "Prototype"
        pid = f"{'P' if is_proto else 'L'}-{1000 + i * 7}"
        end_week = spec["end_week"]
        start_week = max(1, end_week - spec["span"])

        # Give one PM a visible cluster of work.
        pm = OVERLOADED_PM if i in (2, 3, 4, 9) else PMS[i % len(PMS)]

        template = _gates_for(spec["project_type"], spec["launch_type"])
        gate_rows = _build_gate_rows(
            rng, pid, template, start_week, end_week,
            pin_ppap_week=spec.get("pin_ppap"),
            force_complete=spec.get("complete", False),
        )
        gates.extend(gate_rows)

        last = gate_rows[-1]
        sop_actual = last["actual_week"]
        launched = sop_actual is not None

        # PRRs are customer disturbances in the first 12 months after SOP,
        # so they only exist once a project has launched.
        prr = int(rng.integers(0, 4)) if launched else 0

        # Project status is assessed by the PM, separate from gate status.
        open_gates = [g for g in gate_rows if g["actual_week"] is None]
        overdue = [
            g for g in open_gates
            if (g["adjusted_week"] or g["original_week"]) < CURRENT_WEEK
        ]
        if launched:
            status = "Green"
        elif overdue:
            status = "Red" if len(overdue) > 1 else "Yellow"
        else:
            status = "Green" if rng.random() < 0.75 else "Yellow"

        projects.append(
            {
                "project_id": pid,
                "project_name": spec["name"],
                "project_type": spec["project_type"],
                "launch_type": spec["launch_type"],
                "family": spec["family"],
                "plant": PLANTS[i % len(PLANTS)],
                "program_manager": pm,
                "job_number": f"J{47000 + i * 13}",
                "customer": CUSTOMERS[i % len(CUSTOMERS)],
                "sop_original_week": last["original_week"],
                "sop_actual_week": sop_actual,
                "project_status": status,
                "prr_count": prr,
                "comments": "",
            }
        )

    proj_df = pd.DataFrame(projects)
    gate_df = pd.DataFrame(gates)
    for col in ("adjusted_week", "actual_week"):
        gate_df[col] = gate_df[col].astype("Int64")
    proj_df["sop_actual_week"] = proj_df["sop_actual_week"].astype("Int64")
    return proj_df, gate_df


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    proj, gates = build()
    proj.to_csv(DATA_DIR / "projects.csv", index=False)
    gates.to_csv(DATA_DIR / "gates.csv", index=False)
    print(f"projects.csv  {len(proj):>5} rows -> {DATA_DIR / 'projects.csv'}")
    print(f"gates.csv     {len(gates):>5} rows -> {DATA_DIR / 'gates.csv'}")


if __name__ == "__main__":
    main()
