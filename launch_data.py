"""
Synthetic launch / prototype portfolio data.

Writes two CSVs into ./data. PLACEHOLDERS - swap for the real tracker export.
The dashboard only depends on the column contracts below.

--------------------------------------------------------------------------
projects.csv  - one row per project
--------------------------------------------------------------------------
    project_id       str    e.g. "L-1042"
    project_name     str    customer / part description
    project_type     str    Launch | Prototype
    plant            str    owning site
    program_manager  str    person accountable
    customer         str
    start_week       int    1-52
    end_week         int    1-52  (SOP for launches, final report for protos)

--------------------------------------------------------------------------
gates.csv  - one row per project per gate
--------------------------------------------------------------------------
    project_id       str
    gate_no          int    ordering, 1 = first
    gate             str    gate name
    due_week         int    1-52
    completed_week   int    blank if not yet complete
    status           str    Green | Yellow | Red   (gate review RAG)
    qa_lab_hours     float  QA / metrology lab hours this gate consumes

    A gate with a completed_week is done. Open gates carry the RAG status
    assigned at the last review.

Shared-resource note: QA lab hours are the reason prototypes belong in the
same table as launches. Both draw on the same lab.
--------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

YEAR = 2026
SEED = 21
CURRENT_WEEK = 33

DATA_DIR = Path(__file__).parent / "data"

# Gate template for a full production launch.
# (gate_no, name, qa_lab_hours)
LAUNCH_GATES = [
    (1, "Kickoff", 2.0),
    (2, "Feasibility / Quote", 6.0),
    (3, "Design & Tooling Release", 8.0),
    (4, "Process Sign-off", 18.0),
    (5, "Run at Rate", 26.0),
    (6, "PPAP Submission", 44.0),
]

# Prototypes run a shorter path but still hit the lab.
PROTOTYPE_GATES = [
    (1, "Kickoff", 2.0),
    (2, "Sample Build", 14.0),
    (3, "Dimensional Report", 22.0),
]

PLANTS = ["Kentwood", "Wellington", "Attleboro"]

# Placeholder names - replace with the real PM roster.
PMS = ["Alvarez", "Booker", "Chen", "Duval", "Ellis"]

CUSTOMERS = ["Bosch", "ZF", "Cummins", "BorgWarner", "Denso", "Nidec"]

LAUNCH_NAMES = [
    "Injector Body 4412", "Pump Shaft 7130", "Valve Sleeve 2208",
    "Rotor Hub 9051", "Common Rail 5514", "Planet Pin 6620",
    "Turbo Spindle 3307", "Bearing Race 8140", "eAxle Shaft 1180",
    "Steering Pinion 4460", "Cam Follower 2275", "Sensor Housing 9902",
]

PROTOTYPE_NAMES = [
    "Copper Busbar Pin", "Copper Rotor Slug",
    "Thin-Wall Sleeve Trial", "Hardened Pin Trial",
]

# --------------------------------------------------------------------------
# Deliberate demo signals, so the page shows something worth discussing:
#   1. Five projects submit PPAP / dimensional reports in the same week.
#   2. One PM has three projects closing inside a four-week window.
# --------------------------------------------------------------------------
PPAP_PILEUP_WEEK = 38
PILEUP_PROJECTS = 5
OVERLOADED_PM = "Chen"

# How far past due a gate can still be open before we assume it would have
# been escalated and closed.
SLIP_WINDOW = 6


def _rag(rng: np.random.Generator, weeks_late: int) -> str:
    """Gate RAG. Slipping gates skew red; everything else is mostly green."""
    if weeks_late >= 2:
        return "Red"
    if weeks_late >= 0:
        return "Yellow" if rng.random() < 0.7 else "Red"
    return "Green" if rng.random() < 0.82 else "Yellow"


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)

    projects: list[dict] = []
    gates: list[dict] = []

    specs = [(n, "Launch") for n in LAUNCH_NAMES]
    specs += [(n, "Prototype") for n in PROTOTYPE_NAMES]

    for i, (name, ptype) in enumerate(specs):
        is_launch = ptype == "Launch"
        template = LAUNCH_GATES if is_launch else PROTOTYPE_GATES
        pid = f"{'L' if is_launch else 'P'}-{1000 + i * 7}"

        # Concentrate the pileup on the first few projects, and give the
        # overloaded PM a cluster of projects that finish together.
        in_pileup = i < PILEUP_PROJECTS

        if is_launch:
            span = int(rng.integers(20, 34))
        else:
            span = int(rng.integers(8, 14))

        if in_pileup:
            end_week = PPAP_PILEUP_WEEK
        else:
            # Every project in the portfolio is still active, so its final
            # gate lands ahead of today.
            end_week = int(rng.integers(CURRENT_WEEK + 2, 53))

        start_week = max(1, end_week - span)

        pm = OVERLOADED_PM if i in (2, 3, 4) else PMS[i % len(PMS)]

        projects.append(
            {
                "project_id": pid,
                "project_name": name,
                "project_type": ptype,
                "plant": PLANTS[i % len(PLANTS)],
                "program_manager": pm,
                "customer": CUSTOMERS[i % len(CUSTOMERS)],
                "start_week": start_week,
                "end_week": end_week,
            }
        )

        # Space the gates across the project span, last gate on end_week.
        n_gates = len(template)
        for gate_no, gate_name, qa_hours in template:
            frac = gate_no / n_gates
            jitter = float(rng.uniform(-1.5, 1.5))
            due = int(round(start_week + span * frac + jitter))
            due = min(max(due, 1), 52)

            if gate_no == n_gates:
                due = end_week

            if due < CURRENT_WEEK:
                # A gate more than SLIP_WINDOW weeks past due would have been
                # escalated long ago, so treat it as closed. Only recent gates
                # are allowed to still be open and late.
                recently_due = due >= CURRENT_WEEK - SLIP_WINDOW
                if recently_due and rng.random() < 0.25:
                    completed = None
                    status = _rag(rng, CURRENT_WEEK - due)
                else:
                    completed = due + int(rng.integers(-1, 3))
                    completed = min(max(completed, 1), CURRENT_WEEK)
                    status = "Green" if completed <= due else _rag(rng, completed - due)
            else:
                completed = None
                status = _rag(rng, -1)

            gates.append(
                {
                    "project_id": pid,
                    "gate_no": gate_no,
                    "gate": gate_name,
                    "due_week": due,
                    "completed_week": completed,
                    "status": status,
                    "qa_lab_hours": qa_hours * float(rng.uniform(0.85, 1.15)),
                }
            )

    proj_df = pd.DataFrame(projects)
    gate_df = pd.DataFrame(gates)
    gate_df["qa_lab_hours"] = gate_df["qa_lab_hours"].round(1)
    gate_df["completed_week"] = gate_df["completed_week"].astype("Int64")
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
