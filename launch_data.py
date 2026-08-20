"""
Synthetic launch / prototype portfolio data.

Column contract mirrors the real Gate Zero Summary sheet (NA & SA tab).
Everything here is INVENTED - no real part numbers, customers or people.

--------------------------------------------------------------------------
projects.csv  - one row per project
--------------------------------------------------------------------------
  identity
    project_id            str    internal key
    project_name          str    Customer Part Number — Description
    customer_part_number  str
    description           str
    project_type          str    Launch | Prototype
    launch_type           str    Full | Simple | Prototype
    family                str    part family, blank if standalone

  ownership / commercial            (Gate Zero form)
    plant                 str    Kentwood | Marshall | Wellington | North Attleboro
    div                   str    MS | PS
    customer              str
    sales_person          str
    program_manager       str
    job_number            str
    qmsi_number           str
    qmsi_revision         str    raised in review as missing and needed
    opportunity_number    str
    rpn                   int    Gate Zero risk priority number
    peak_annual_sales     float
    launch_process        str
    support_required      str
    launch_risk           str    Low | Medium | High

  capex
    qmsi_capex            float
    cer_amount            float
    cer_status            str
    cer_number            str

  schedule seeds                    (drive every planned gate date)
    gate_zero_date        date
    ppap_target_date      date
    sop_target_date       date

  status and outcome
    project_status        str    Green | Yellow | Red  (assessed, not derived)
    prr_count             int    PRRs in the first 12 months after SOP
    prr_amount_first_year float
    prr_start_date        date   blank until launched
    prr_end_date          date   SOP + 12 months
    notes                 str

--------------------------------------------------------------------------
gates.csv  - one row per project per gate
--------------------------------------------------------------------------
    project_id      str
    gate_no         int    sort order
    gate_code       str    0 1 2 3 4 SL 6M  (label inside the timeline dot)
    gate_name       str
    plan_date       date   auto-calculated from the Gate Zero dates
    adjusted_date   date   revised commitment, blank if never moved
    actual_date     date   completion, blank if still open
    qa_lab_hours    float

Due date = adjusted_date if present, else plan_date.
On-time  = actual_date <= due date  (falls back to plan when not adjusted).
--------------------------------------------------------------------------
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

import gate_schedule as gs
from config import DIVISIONS, PLANTS, today

SEED = 41
DATA_DIR = Path(__file__).parent / "data"

PMS = ["Alvarez", "Booker", "Chen", "Duval"]
SALES = ["Hargreaves", "Iqbal", "Novak"]
CUSTOMERS = ["Customer A", "Customer B", "Customer C", "Customer D"]
LAUNCH_PROCESSES = ["Standard APQP", "Transfer", "Re-source"]
SUPPORT = ["None", "Tooling", "Gauging", "Tooling + Gauging"]
RISKS = ["Low", "Medium", "High"]
CER_STATUS = ["Not required", "Submitted", "Approved"]

FAMILY_NAME = "Series-7 Pin"
FAMILY_VARIANTS = ["Bent", "Straight", "Short", "Long", "Stepped"]
FAMILY_FULL = 2  # first two variants take a full launch

STANDALONE = [
    ("4412-01", "Injector Body"), ("7130-02", "Pump Shaft"),
    ("2208-05", "Valve Sleeve"), ("9051-11", "Rotor Hub"),
    ("5514-03", "Common Rail Fitting"), ("6620-08", "Planet Pin"),
    ("3307-04", "Turbo Spindle"), ("8140-09", "Bearing Race"),
]

LAUNCHED = [
    ("3021-07", "Output Shaft"), ("5540-02", "Idler Pin"),
    ("1190-06", "Sleeve Bearing"), ("7702-01", "Thrust Washer"),
    ("6318-03", "Spline Adapter"),
]

PROTOTYPES = [
    ("CU-001", "Copper Busbar Pin"), ("CU-014", "Copper Rotor Slug"),
    ("TW-003", "Thin-Wall Sleeve Trial"), ("HP-009", "Hardened Pin Trial"),
]

SLIP_WINDOW_DAYS = 45  # a gate older than this would have been escalated

# Indices into STANDALONE that are running late, so the demo shows red.
SLIPPING_STANDALONE = {1, 4, 6}


def _iso(d) -> str | None:
    return None if d is None or pd.isna(d) else pd.Timestamp(d).date().isoformat()


def build() -> tuple[pd.DataFrame, pd.DataFrame]:
    rng = np.random.default_rng(SEED)
    now = today()

    specs: list[dict] = []

    # A part family: two full launches, the rest simple, all sharing a PPAP.
    family_ppap = now + timedelta(days=35)
    for i, variant in enumerate(FAMILY_VARIANTS):
        specs.append(
            {
                "part": f"7{i}10-0{i}", "desc": f"{FAMILY_NAME} {variant}",
                "project_type": "Launch",
                "launch_type": "Full" if i < FAMILY_FULL else "Simple",
                "family": FAMILY_NAME,
                "gate_zero": family_ppap - timedelta(days=int(rng.integers(150, 200))),
                "ppap": family_ppap,
                "sop": family_ppap + timedelta(days=int(rng.integers(25, 45))),
                "launched": False,
            }
        )

    # A few projects are deliberately behind, so the red state is visible.
    for n, (part, desc) in enumerate(STANDALONE):
        ppap = now + timedelta(days=int(rng.integers(20, 210)))
        specs.append(
            {
                "part": part, "desc": desc, "project_type": "Launch",
                "launch_type": "Simple" if rng.random() < 0.25 else "Full",
                "family": "",
                "gate_zero": ppap - timedelta(days=int(rng.integers(140, 220))),
                "ppap": ppap,
                "sop": ppap + timedelta(days=int(rng.integers(25, 50))),
                "launched": False,
                "slipping": n in SLIPPING_STANDALONE,
            }
        )

    # Already launched, so the scorecard and PRR window have real content.
    for part, desc in LAUNCHED:
        sop = now - timedelta(days=int(rng.integers(40, 330)))
        ppap = sop - timedelta(days=int(rng.integers(25, 45)))
        specs.append(
            {
                "part": part, "desc": desc, "project_type": "Launch",
                "launch_type": "Full", "family": "",
                "gate_zero": ppap - timedelta(days=int(rng.integers(150, 210))),
                "ppap": ppap, "sop": sop, "launched": True,
            }
        )

    for part, desc in PROTOTYPES:
        ppap = now + timedelta(days=int(rng.integers(10, 90)))
        specs.append(
            {
                "part": part, "desc": desc, "project_type": "Prototype",
                "launch_type": "Prototype", "family": "",
                "gate_zero": ppap - timedelta(days=int(rng.integers(30, 70))),
                "ppap": ppap,
                "sop": ppap + timedelta(days=int(rng.integers(10, 25))),
                "launched": False,
            }
        )

    projects, gates = [], []

    for i, spec in enumerate(specs):
        is_proto = spec["project_type"] == "Prototype"
        pid = f"{'P' if is_proto else 'L'}-{1000 + i * 7}"

        rows = gs.build_gate_rows(
            pid, spec["project_type"], spec["launch_type"],
            spec["gate_zero"], spec["ppap"], spec["sop"],
        )

        for row in rows:
            plan = row["plan_date"]

            # Roughly a third of gates get their commitment moved.
            adjusted = None
            if rng.random() < (0.15 if spec["launched"] else 0.30):
                adjusted = plan + timedelta(days=int(rng.integers(5, 25)))
            due = adjusted or plan

            actual = None
            slipping = spec.get("slipping") and due < now and (
                due >= now - timedelta(days=120)
            )
            if slipping:
                pass  # deliberately left open so the demo shows real slippage
            elif spec["launched"] and row["gate_code"] != gs.SIX_MONTH_CODE:
                actual = due + timedelta(days=int(rng.integers(-9, 4)))
            elif due < now:
                recent = due >= now - timedelta(days=SLIP_WINDOW_DAYS)
                if not (recent and rng.random() < 0.40):
                    actual = min(due + timedelta(days=int(rng.integers(-9, 4))), now)

            row["adjusted_date"] = adjusted
            row["actual_date"] = actual

        gates.extend(rows)

        sop_actual = next(
            (r["actual_date"] for r in rows if r["gate_code"] == gs.SOP_CODE), None
        )
        launched = sop_actual is not None

        open_rows = [r for r in rows if r["actual_date"] is None]
        behind = [r for r in open_rows if (r["adjusted_date"] or r["plan_date"]) < now]
        if launched:
            status = "Green"
        elif len(behind) > 1:
            status = "Red"
        elif behind:
            status = "Yellow"
        else:
            status = "Green" if rng.random() < 0.75 else "Yellow"

        prr = int(rng.integers(0, 5)) if launched else 0
        peak_sales = float(rng.integers(150, 3200)) * 1000

        projects.append(
            {
                "project_id": pid,
                "project_name": f"{spec['part']} — {spec['desc']}",
                "customer_part_number": spec["part"],
                "description": spec["desc"],
                "project_type": spec["project_type"],
                "launch_type": spec["launch_type"],
                "family": spec["family"],
                "plant": PLANTS[i % len(PLANTS)],
                "div": DIVISIONS[i % len(DIVISIONS)],
                "customer": CUSTOMERS[i % len(CUSTOMERS)],
                "sales_person": SALES[i % len(SALES)],
                "program_manager": "Chen" if i in (2, 3, 4, 9) else PMS[i % len(PMS)],
                "job_number": f"J{47000 + i * 13}",
                "qmsi_number": f"QMSI-{3200 + i * 3}",
                "qmsi_revision": f"{rng.integers(1, 5)}",
                "opportunity_number": f"OPP-{61000 + i * 17}",
                "rpn": int(rng.integers(20, 220)),
                "peak_annual_sales": peak_sales,
                "launch_process": LAUNCH_PROCESSES[i % len(LAUNCH_PROCESSES)],
                "support_required": SUPPORT[i % len(SUPPORT)],
                "launch_risk": RISKS[min(int(rng.integers(0, 3)), 2)],
                "qmsi_capex": float(rng.integers(0, 900)) * 1000,
                "cer_amount": float(rng.integers(0, 600)) * 1000,
                "cer_status": CER_STATUS[i % len(CER_STATUS)],
                "cer_number": f"CER-{8800 + i * 5}",
                "gate_zero_date": _iso(spec["gate_zero"]),
                "ppap_target_date": _iso(spec["ppap"]),
                "sop_target_date": _iso(spec["sop"]),
                "project_status": status,
                "prr_count": prr,
                "prr_amount_first_year": float(prr) * float(rng.integers(2, 30)) * 1000,
                "prr_start_date": _iso(sop_actual) if launched else None,
                "prr_end_date": _iso(gs.add_months(sop_actual, 12)) if launched else None,
                "notes": "",
            }
        )

    proj_df = pd.DataFrame(projects)
    gate_df = pd.DataFrame(gates)
    for col in ("plan_date", "adjusted_date", "actual_date"):
        gate_df[col] = gate_df[col].map(_iso)
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
