"""
Launch portfolio math. Streamlit-free so it can be tested and reused.

Works entirely in real dates. Manufacturing weeks are gone.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd

import gate_schedule as gs

DATA_DIR = Path(__file__).parent / "data"

DATE_COLUMNS_GATES = ["plan_date", "adjusted_date", "actual_date"]
DATE_COLUMNS_PROJECTS = [
    "gate_zero_date", "ppap_target_date", "sop_target_date",
    "prr_start_date", "prr_end_date",
]

PROJECT_COLUMNS = [
    "project_id", "project_name", "project_type", "launch_type",
    "plant", "program_manager", "job_number", "project_status",
    "gate_zero_date", "ppap_target_date", "sop_target_date", "prr_count",
]

GATE_COLUMNS = [
    "project_id", "gate_no", "gate_code", "gate_name",
    "plan_date", "adjusted_date", "actual_date", "qa_lab_hours",
]

PROJECT_TYPES = ["Launch", "Prototype"]
# "Prototype" is a launch_type in its own right - prototypes are neither full
# nor simple, and labelling them n/a read as a bug.
LAUNCH_TYPES = ["Full", "Simple", "Prototype"]

COMPLETE, IN_PROGRESS, BEHIND = "Complete", "In progress", "Behind"
GATE_STATUSES = [COMPLETE, IN_PROGRESS, BEHIND]

# Optional columns tolerated when absent, with their fill value.
OPTIONAL_PROJECT_FIELDS = {
    "customer_part_number": "", "description": "", "family": "", "div": "",
    "customer": "", "sales_person": "", "qmsi_number": "", "qmsi_revision": "",
    "opportunity_number": "", "launch_process": "", "support_required": "",
    "launch_risk": "", "cer_status": "", "cer_number": "", "notes": "",
    "rpn": 0, "peak_annual_sales": 0.0, "qmsi_capex": 0.0, "cer_amount": 0.0,
    "prr_amount_first_year": 0.0,
}


class SchemaError(ValueError):
    pass


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing required column(s): {', '.join(missing)}")


def _to_date(series: pd.Series) -> pd.Series:
    return pd.to_datetime(series, errors="coerce").dt.date


def _is_date(v) -> bool:
    return isinstance(v, date)


def _before(series: pd.Series, limit: date) -> pd.Series:
    """Element-wise `< limit`, tolerating blanks and all-empty columns.

    Prototypes have no Gate 4, so SOP columns can be entirely empty; a plain
    vectorised comparison raises on that.
    """
    return series.map(lambda v: _is_date(v) and v < limit)


def _between(series: pd.Series, lo: date, hi: date) -> pd.Series:
    return series.map(lambda v: _is_date(v) and lo <= v <= hi)


def _at_or_before(series: pd.Series, limit: date) -> pd.Series:
    return series.map(lambda v: _is_date(v) and v <= limit)


def load_projects(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, PROJECT_COLUMNS, "projects")
    for col, fill in OPTIONAL_PROJECT_FIELDS.items():
        if col not in df.columns:
            df[col] = fill
        df[col] = df[col].fillna(fill)
    for col in DATE_COLUMNS_PROJECTS:
        if col in df.columns:
            df[col] = _to_date(df[col])
    df["prr_count"] = pd.to_numeric(df["prr_count"], errors="coerce").fillna(0).astype(int)
    # Legacy files labelled prototypes "n/a".
    df["launch_type"] = df["launch_type"].fillna("Prototype").replace("n/a", "Prototype")
    return df


def load_gates(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, GATE_COLUMNS, "gates")
    df["gate_no"] = df["gate_no"].astype(int)
    df["gate_code"] = df["gate_code"].astype(str)
    for col in DATE_COLUMNS_GATES:
        df[col] = _to_date(df[col])
    df["qa_lab_hours"] = pd.to_numeric(df["qa_lab_hours"], errors="coerce").fillna(0.0)
    return df


def load_bundled() -> tuple[pd.DataFrame, pd.DataFrame]:
    proj_path, gate_path = DATA_DIR / "projects.csv", DATA_DIR / "gates.csv"
    if not (proj_path.exists() and gate_path.exists()):
        import launch_data

        launch_data.main()
    return load_projects(proj_path), load_gates(gate_path)


# ---------------------------------------------------------------------------
# Derived fields
# ---------------------------------------------------------------------------
def annotate_gates(gates: pd.DataFrame, as_of: date) -> pd.DataFrame:
    """
    Derive due date, status and on-time flags.

    DUE DATE falls back: adjusted_date if one exists, otherwise plan_date.
    ON TIME is measured against that due date - this is the definition
    confirmed in review. `on_time_vs_plan` keeps the stricter reading
    (against the original plan) alongside it, so a project cannot quietly
    repair its record by moving its own target without that being visible.
    """
    g = gates.copy()

    g["due_date"] = g["adjusted_date"].where(g["adjusted_date"].notna(), g["plan_date"])
    g["is_complete"] = g["actual_date"].notna()
    g["is_behind"] = (~g["is_complete"]) & _before(g["due_date"], as_of)

    g["status"] = IN_PROGRESS
    g.loc[g["is_complete"], "status"] = COMPLETE
    g.loc[g["is_behind"], "status"] = BEHIND

    g["days_late"] = 0
    behind = g["is_behind"]
    g.loc[behind, "days_late"] = g.loc[behind].apply(
        lambda r: (as_of - r["due_date"]).days, axis=1
    )

    g["was_moved"] = g["adjusted_date"].notna()

    done = g["is_complete"] & g["due_date"].notna()
    g["on_time"] = pd.NA
    g.loc[done, "on_time"] = g.loc[done].apply(
        lambda r: r["actual_date"] <= r["due_date"], axis=1
    )

    done_plan = g["is_complete"] & g["plan_date"].notna()
    g["on_time_vs_plan"] = pd.NA
    g.loc[done_plan, "on_time_vs_plan"] = g.loc[done_plan].apply(
        lambda r: r["actual_date"] <= r["plan_date"], axis=1
    )
    return g


def project_progress(projects: pd.DataFrame, gates: pd.DataFrame) -> pd.DataFrame:
    total = gates.groupby("project_id")["gate_no"].count().rename("gates_total")
    done = (
        gates[gates["is_complete"]].groupby("project_id")["gate_no"].count()
        .rename("gates_complete")
    )
    behind = (
        gates[gates["is_behind"]].groupby("project_id")["gate_no"].count()
        .rename("gates_behind")
    )

    open_gates = gates[~gates["is_complete"]].sort_values(
        ["project_id", "due_date", "gate_no"]
    )
    nxt = open_gates.groupby("project_id").agg(
        next_gate=("gate_name", "first"),
        next_gate_code=("gate_code", "first"),
        next_due_date=("due_date", "first"),
    )

    sop = (
        gates[gates["gate_code"] == gs.SOP_CODE]
        .set_index("project_id")[["due_date", "actual_date"]]
        .rename(columns={"due_date": "sop_due_date", "actual_date": "sop_actual_date"})
    )
    start = (
        gates.sort_values("gate_no").groupby("project_id")["due_date"].first()
        .rename("start_date")
    )
    end = gates.groupby("project_id")["due_date"].max().rename("end_date")

    out = (
        projects.set_index("project_id")
        .join(total).join(done).join(behind).join(nxt).join(sop).join(start).join(end)
        .reset_index()
    )
    for col in ("gates_complete", "gates_total", "gates_behind"):
        out[col] = out[col].fillna(0).astype(int)
    out["pct_complete"] = out["gates_complete"] / out["gates_total"].where(
        out["gates_total"] > 0
    )
    out["is_launched"] = out["sop_actual_date"].notna()
    return out


def qa_lab_load(
    gates: pd.DataFrame, projects: pd.DataFrame, start: date, end: date
) -> pd.DataFrame:
    """QA lab hours per ISO week, split by project type. Kept for the
    hidden shared-resource view."""
    g = gates.merge(
        projects[["project_id", "project_type"]], on="project_id", how="left"
    )
    g["load_date"] = g["actual_date"].fillna(g["due_date"])
    g = g[g["load_date"].notna()]
    g = g[(g["load_date"] >= start) & (g["load_date"] <= end)]
    if g.empty:
        return pd.DataFrame(columns=["week_start", "project_type", "hours"])
    g["week_start"] = pd.to_datetime(g["load_date"]).dt.to_period("W").dt.start_time.dt.date
    return (
        g.groupby(["week_start", "project_type"], as_index=False)["qa_lab_hours"]
        .sum()
        .rename(columns={"qa_lab_hours": "hours"})
    )


def pm_workload(progress: pd.DataFrame, as_of: date, horizon_days: int) -> pd.DataFrame:
    df = progress.copy()
    limit = as_of + timedelta(days=horizon_days)
    sop = df["sop_actual_date"].where(df["sop_actual_date"].notna(), df["sop_due_date"])
    df["closing_soon"] = _between(sop, as_of, limit)
    df["red"] = df["project_status"] == "Red"
    out = df.groupby("program_manager", as_index=False).agg(
        active_projects=("project_id", "count"),
        launches=("project_type", lambda s: int((s == "Launch").sum())),
        prototypes=("project_type", lambda s: int((s == "Prototype").sum())),
        closing_soon=("closing_soon", "sum"),
        red_projects=("red", "sum"),
    )
    return out.sort_values(
        ["closing_soon", "active_projects"], ascending=False, ignore_index=True
    )


def coming_due(
    gates: pd.DataFrame, projects: pd.DataFrame, as_of: date, horizon_days: int
) -> pd.DataFrame:
    cols = [
        "project_id", "project_name", "project_type", "launch_type",
        "plant", "program_manager", "job_number",
    ]
    g = gates[~gates["is_complete"]].merge(projects[cols], on="project_id", how="left")
    limit = as_of + timedelta(days=horizon_days)
    window = g[_at_or_before(g["due_date"], limit) | g["is_behind"]].copy()
    window["days_out"] = window["due_date"].map(
        lambda d: (d - as_of).days if pd.notna(d) else None
    )
    return window.sort_values(["due_date", "project_id"], ignore_index=True)


def scorecard(projects: pd.DataFrame, gates: pd.DataFrame, as_of: date) -> dict:
    """
    The graded metrics named in review.

    `gate_on_time` uses the agreed definition: actual against the adjusted
    date, falling back to plan. `gate_on_time_vs_plan` measures against the
    original plan, so the difference between the two shows how much of the
    on-time record rests on dates that were moved.

    PRRs are counted for projects whose SOP is inside the last 12 months.
    """
    closed = gates[gates["is_complete"]]
    on_time = float(closed["on_time"].mean()) if len(closed) else float("nan")
    vs_plan = (
        float(closed["on_time_vs_plan"].mean()) if len(closed) else float("nan")
    )

    launched = projects[projects["sop_actual_date"].notna()] if (
        "sop_actual_date" in projects.columns
    ) else projects.iloc[0:0]

    if len(launched):
        launch_on_time = float(
            launched.apply(
                lambda r: _is_date(r["sop_actual_date"])
                and _is_date(r["sop_due_date"])
                and r["sop_actual_date"] <= r["sop_due_date"],
                axis=1,
            ).mean()
        )
    else:
        launch_on_time = float("nan")

    window_start = as_of - timedelta(days=365)
    recent = (
        launched[_between(launched["sop_actual_date"], window_start, as_of)]
        if len(launched)
        else launched
    )
    prr_recent = int(recent["prr_count"].sum()) if len(recent) else 0

    return {
        "gate_on_time": on_time,
        "gate_on_time_vs_plan": vs_plan,
        "gates_closed": int(len(closed)),
        "launch_on_time": launch_on_time,
        "launches_closed": int(len(launched)),
        "prr_12mo": prr_recent,
        "prr_projects": int(len(recent)),
        "prr_total": int(projects["prr_count"].sum()),
        "dates_moved": int(gates["was_moved"].sum()),
    }
