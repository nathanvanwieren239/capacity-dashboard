"""
Synthetic data generator for the capacity dashboard demo.

Writes two CSVs into ./data. These are PLACEHOLDERS. Swap them for real
extracts; the dashboard only depends on the column contracts below.

--------------------------------------------------------------------------
capacity.csv  - one row per plant / work_center / week
--------------------------------------------------------------------------
    plant                        str    site name
    work_center                  str    machine group / cell
    week                         int    1-52 (ISO week)
    machines                     int    assets in the group (reference only)
    true_capacity_hours          float  theoretical ceiling: every asset,
                                        every shift, at target availability
    fully_staffed_capacity_hours float  the same assets with every shift
                                        completely crewed
    current_capacity_hours       float  what the group delivers today, at
                                        present staffing and realized rate

    Invariant: true >= fully staffed >= current

--------------------------------------------------------------------------
demand.csv  - one row per plant / work_center / week / program / demand_type
--------------------------------------------------------------------------
    plant          str
    work_center    str
    week           int    1-52
    program        str    customer program / part family
    demand_type    str    one of: Released | Launch | Quoted
    hours          float  standard run hours + setup allocated to that week

    Released = firm customer releases
    Launch   = awarded business not yet at full rate
    Quoted   = open RFQs (shown separately; not a commitment)
--------------------------------------------------------------------------
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

YEAR = 2026
WEEKS = list(range(1, 53))
SEED = 7

DATA_DIR = Path(__file__).parent / "data"

# --------------------------------------------------------------------------
# Shop definition. Work centers per site are placeholders - correct them.
# (work_center, machine_count, full_staff_factor, current_factor)
#   full_staff_factor: true -> fully staffed. Below 1.0 because even a fully
#                      crewed cell does not run the theoretical 24 h x 6 d.
#   current_factor:    fully staffed -> current. Today's staffing gap and
#                      realized run rate.
# --------------------------------------------------------------------------
SHOP: dict[str, list[tuple[str, int, float, float]]] = {
    "Kentwood": [
        ("Swiss Turning", 18, 0.78, 0.84),
        ("CNC Turning", 10, 0.85, 0.80),
        ("Centerless Grinding", 6, 0.70, 0.76),
        ("ID/OD Grinding", 5, 0.66, 0.74),
        ("Milling", 4, 0.80, 0.78),
        ("Wash & Inspect", 3, 0.90, 0.88),
    ],
    "Wellington": [
        ("Multi-Spindle", 12, 0.72, 0.79),
        ("CNC Turning", 14, 0.83, 0.81),
        ("Centerless Grinding", 8, 0.68, 0.75),
        ("Honing", 4, 0.75, 0.82),
        ("Gundrilling", 3, 0.62, 0.71),
        ("Wash & Inspect", 3, 0.90, 0.88),
    ],
    "Attleboro": [
        ("Swiss Turning", 9, 0.74, 0.83),
        ("Milling", 11, 0.82, 0.79),
        ("ID/OD Grinding", 7, 0.64, 0.73),
        ("Heat Treat", 2, 0.88, 0.86),
        ("Assembly", 6, 0.95, 0.85),
        ("Wash & Inspect", 2, 0.90, 0.88),
    ],
}

# Theoretical ceiling per asset per week: 24 h x 6 days.
GROSS_HOURS_PER_MACHINE_WEEK = 144.0

# Planned non-production weeks -> fraction of a normal week available.
SHUTDOWN_FACTORS = {
    1: 0.60,   # New Year ramp back
    27: 0.35,  # summer shutdown
    28: 0.65,
    47: 0.80,  # Thanksgiving
    52: 0.30,  # Christmas shutdown
}

# Once firm releases run out, demand drops to forecast volume rather than zero.
FORECAST_FLOOR = 0.72

# Cells deliberately run tight so the demo shows a real constraint.
HOT_CELLS = {
    ("Wellington", "Multi-Spindle"),
    ("Kentwood", "ID/OD Grinding"),
    ("Attleboro", "Heat Treat"),
}

# Short codes used in synthetic RFQ names.
PLANT_CODES = {"Kentwood": "KTW", "Wellington": "WEL", "Attleboro": "ATT"}

PROGRAMS = {
    "Kentwood": ["Injector Body 4412", "Pump Shaft 7130", "Valve Sleeve 2208",
                "Rotor Hub 9051"],
    "Wellington": ["Common Rail 5514", "Planet Pin 6620", "Turbo Spindle 3307",
                "Bearing Race 8140"],
    "Attleboro": ["eAxle Shaft 1180", "Steering Pinion 4460", "Cam Follower 2275",
                "Sensor Housing 9902"],
}


def _week_factor(week: int) -> float:
    return SHUTDOWN_FACTORS.get(week, 1.0)


def build_capacity() -> pd.DataFrame:
    rows = []
    for plant, centers in SHOP.items():
        for wc, machines, full_staff_factor, current_factor in centers:
            true_base = machines * GROSS_HOURS_PER_MACHINE_WEEK
            for week in WEEKS:
                f = _week_factor(week)
                true_h = true_base * f
                staffed_h = true_h * full_staff_factor
                current_h = staffed_h * current_factor
                rows.append(
                    {
                        "plant": plant,
                        "work_center": wc,
                        "week": week,
                        "machines": machines,
                        "true_capacity_hours": round(true_h, 1),
                        "fully_staffed_capacity_hours": round(staffed_h, 1),
                        "current_capacity_hours": round(current_h, 1),
                    }
                )
    return pd.DataFrame(rows)


def build_demand(capacity: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """
    Shape of the synthetic story:
      Released - near-term firm releases, taper off past the release horizon
      Launch   - awarded program ramping in during H2
      Quoted   - scattered RFQ volume in the back half
    """
    rows = []
    horizon_start = 33  # roughly "today"
    release_horizon = 13  # weeks of firm visibility

    for (plant, wc), grp in capacity.groupby(["plant", "work_center"]):
        base = grp["current_capacity_hours"].median()
        programs = PROGRAMS[plant]

        # How hard this work center is loaded at steady state.
        load_factor = rng.uniform(0.70, 1.10)
        # A couple of known-tight cells, so the demo has a real bottleneck.
        if (plant, wc) in HOT_CELLS:
            load_factor = rng.uniform(1.05, 1.20)

        # Which program is launching into this work center, and when.
        launch_program = programs[rng.integers(0, len(programs))]
        launch_week = int(rng.integers(36, 44))
        launch_peak = base * rng.uniform(0.30, 0.70)

        for week in WEEKS:
            f = _week_factor(week)

            # ---- Released -------------------------------------------------
            if week >= horizon_start:
                # Firm releases taper past the visibility horizon, but the
                # program does not stop - it drops to forecast volume.
                age = week - horizon_start
                decay = max(FORECAST_FLOOR, 1.0 - age / release_horizon)
            else:
                decay = 1.0  # history, kept so the file is complete
            released = base * load_factor * decay * f
            released *= rng.uniform(0.90, 1.10)
            if released > 1:
                for i, prog in enumerate(programs[:3]):
                    share = [0.5, 0.3, 0.2][i]
                    rows.append(
                        {
                            "plant": plant,
                            "work_center": wc,
                            "week": week,
                            "program": prog,
                            "demand_type": "Released",
                            "hours": round(released * share, 1),
                        }
                    )

            # ---- Launch ---------------------------------------------------
            if week >= launch_week:
                ramp = min(1.0, (week - launch_week + 1) / 8.0)
                launch_h = launch_peak * ramp * f * rng.uniform(0.95, 1.05)
                if launch_h > 1:
                    rows.append(
                        {
                            "plant": plant,
                            "work_center": wc,
                            "week": week,
                            "program": launch_program,
                            "demand_type": "Launch",
                            "hours": round(launch_h, 1),
                        }
                    )

            # ---- Quoted ---------------------------------------------------
            if week >= horizon_start + 8 and rng.random() < 0.55:
                quoted_h = base * rng.uniform(0.05, 0.30) * f
                rows.append(
                    {
                        "plant": plant,
                        "work_center": wc,
                        "week": week,
                        "program": f"RFQ {PLANT_CODES[plant]}-{week:02d}",
                        "demand_type": "Quoted",
                        "hours": round(quoted_h, 1),
                    }
                )

    return pd.DataFrame(rows)


def main() -> None:
    rng = np.random.default_rng(SEED)
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    capacity = build_capacity()
    demand = build_demand(capacity, rng)

    capacity.to_csv(DATA_DIR / "capacity.csv", index=False)
    demand.to_csv(DATA_DIR / "demand.csv", index=False)

    print(f"capacity.csv  {len(capacity):>6} rows -> {DATA_DIR / 'capacity.csv'}")
    print(f"demand.csv    {len(demand):>6} rows -> {DATA_DIR / 'demand.csv'}")


if __name__ == "__main__":
    main()
