"""
Launch portfolio math. Streamlit-free so it can be tested and reused.

Load here is milestone EVENTS landing in the same week and pulling on a
shared support resource - the QA lab above all - not machine hours.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

PROJECT_COLUMNS = [
    "project_id",
    "project_name",
    "project_type",
    "launch_type",
    "plant",
    "program_manager",
    "job_number",
    "sop_original_week",
    "sop_actual_week",
    "project_status",
    "prr_count",
]

GATE_COLUMNS = [
    "project_id",
    "gate_no",
    "gate_code",
    "gate_name",
    "original_week",
    "adjusted_week",
    "actual_week",
    "qa_lab_hours",
]

PROJECT_TYPES = ["Launch", "Prototype"]
LAUNCH_TYPES = ["Full", "Simple"]

# Gate status is derived from dates, never stored.
COMPLETE = "Complete"
IN_PROGRESS = "In progress"
BEHIND = "Behind"
GATE_STATUSES = [COMPLETE, IN_PROGRESS, BEHIND]


class SchemaError(ValueError):
    pass


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing required column(s): {', '.join(missing)}")


def load_projects(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, PROJECT_COLUMNS, "projects")
    df["sop_original_week"] = df["sop_original_week"].astype(int)
    df["sop_actual_week"] = pd.to_numeric(
        df["sop_actual_week"], errors="coerce"
    ).astype("Int64")
    df["prr_count"] = pd.to_numeric(df["prr_count"], errors="coerce").fillna(0).astype(int)
    for col in ("family", "comments", "customer"):
        if col not in df.columns:
            df[col] = ""
        df[col] = df[col].fillna("")
    # "n/a" round-trips through CSV as NaN; prototypes have no launch type.
    df["launch_type"] = df["launch_type"].fillna("n/a")
    return df


def load_gates(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, GATE_COLUMNS, "gates")
    df["gate_no"] = df["gate_no"].astype(int)
    df["gate_code"] = df["gate_code"].astype(str)
    df["original_week"] = df["original_week"].astype(int)
    for col in ("adjusted_week", "actual_week"):
        df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
    df["qa_lab_hours"] = pd.to_numeric(df["qa_lab_hours"], errors="coerce").fillna(0.0)
    return df


def load_bundled() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load portfolio CSVs, generating them on a clean clone if absent."""
    proj_path = DATA_DIR / "projects.csv"
    gate_path = DATA_DIR / "gates.csv"

    if not (proj_path.exists() and gate_path.exists()):
        import launch_data

        launch_data.main()

    return load_projects(proj_path), load_gates(gate_path)


# ---------------------------------------------------------------------------
# Derived fields
# ---------------------------------------------------------------------------
def annotate_gates(gates: pd.DataFrame, current_week: int) -> pd.DataFrame:
    """
    Derive due week, status and on-time flags.

    Status is exactly the three states asked for in review:
        Complete    -> green
        In progress -> yellow
        Behind      -> red
    """
    g = gates.copy()

    g["due_week"] = g["adjusted_week"].fillna(g["original_week"]).astype(int)
    g["is_complete"] = g["actual_week"].notna()
    g["is_behind"] = (~g["is_complete"]) & (g["due_week"] < current_week)

    g["status"] = IN_PROGRESS
    g.loc[g["is_complete"], "status"] = COMPLETE
    g.loc[g["is_behind"], "status"] = BEHIND

    g["weeks_late"] = 0
    g.loc[g["is_behind"], "weeks_late"] = (
        current_week - g.loc[g["is_behind"], "due_week"]
    )

    # Was the date moved, and did it close by the ORIGINAL commitment?
    g["was_moved"] = g["adjusted_week"].notna()
    g["on_time"] = pd.NA
    done = g["is_complete"]
    g.loc[done, "on_time"] = (
        g.loc[done, "actual_week"].astype(int) <= g.loc[done, "original_week"]
    )
    return g


def project_progress(projects: pd.DataFrame, gates: pd.DataFrame) -> pd.DataFrame:
    """One row per project with gate counts and the next open gate."""
    total = gates.groupby("project_id")["gate_no"].count().rename("gates_total")
    done = (
        gates[gates["is_complete"]].groupby("project_id")["gate_no"].count()
        .rename("gates_complete")
    )
    behind = (
        gates[gates["is_behind"]].groupby("project_id")["gate_no"].count()
        .rename("gates_behind")
    )

    open_gates = gates[~gates["is_complete"]]
    next_gate = (
        open_gates.sort_values(["project_id", "due_week", "gate_no"])
        .groupby("project_id")
        .agg(
            next_gate=("gate_name", "first"),
            next_gate_code=("gate_code", "first"),
            next_due_week=("due_week", "first"),
        )
    )

    out = (
        projects.set_index("project_id")
        .join(total).join(done).join(behind).join(next_gate)
        .reset_index()
    )
    for col in ("gates_complete", "gates_total", "gates_behind"):
        out[col] = out[col].fillna(0).astype(int)
    out["pct_complete"] = out["gates_complete"] / out["gates_total"].where(
        out["gates_total"] > 0
    )
    out["is_launched"] = out["sop_actual_week"].notna()
    return out


def qa_lab_load(
    gates: pd.DataFrame, projects: pd.DataFrame, weeks: list[int]
) -> pd.DataFrame:
    """
    QA lab hours landing per week, split by project type.

    Booked to the week the gate is due (or was completed). Coarse but honest:
    real lab work spreads over several weeks and that needs the lab's input.
    """
    g = gates.merge(
        projects[["project_id", "project_type"]], on="project_id", how="left"
    )
    g["load_week"] = g["actual_week"].fillna(g["due_week"]).astype(int)

    grouped = (
        g.groupby(["load_week", "project_type"], as_index=False)["qa_lab_hours"]
        .sum()
        .rename(columns={"load_week": "week", "qa_lab_hours": "hours"})
    )
    idx = pd.MultiIndex.from_product(
        [weeks, PROJECT_TYPES], names=["week", "project_type"]
    )
    return (
        grouped.set_index(["week", "project_type"])
        .reindex(idx, fill_value=0.0)
        .reset_index()
    )


def pm_workload(progress: pd.DataFrame, current_week: int, horizon: int) -> pd.DataFrame:
    """Projects per PM, and how many wrap up inside the horizon."""
    df = progress.copy()
    sop = df["sop_actual_week"].fillna(df["sop_original_week"]).astype(int)
    df["closing_soon"] = sop.between(current_week, current_week + horizon)
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
    gates: pd.DataFrame, projects: pd.DataFrame, current_week: int, horizon: int
) -> pd.DataFrame:
    """Open gates due inside the horizon, plus anything already behind."""
    cols = [
        "project_id", "project_name", "project_type", "launch_type",
        "plant", "program_manager", "job_number",
    ]
    g = gates[~gates["is_complete"]].merge(projects[cols], on="project_id", how="left")
    window = g[(g["due_week"] <= current_week + horizon) | (g["is_behind"])].copy()
    window["when"] = window["due_week"] - current_week
    return window.sort_values(["due_week", "project_id"], ignore_index=True)


def scorecard(projects: pd.DataFrame, gates: pd.DataFrame) -> dict[str, float | int]:
    """
    The three graded metrics named in review.

    On-time is measured against the ORIGINAL committed date. Measuring
    against the adjusted date would let a project stay green by moving its
    own target, which is the whole reason edit access gets restricted.
    """
    closed = gates[gates["is_complete"]]
    gate_on_time = float(closed["on_time"].mean()) if len(closed) else float("nan")

    launched = projects[projects["sop_actual_week"].notna()]
    if len(launched):
        launch_on_time = float(
            (
                launched["sop_actual_week"].astype(int)
                <= launched["sop_original_week"].astype(int)
            ).mean()
        )
    else:
        launch_on_time = float("nan")

    return {
        "gate_on_time": gate_on_time,
        "gates_closed": int(len(closed)),
        "launch_on_time": launch_on_time,
        "launches_closed": int(len(launched)),
        "prr_total": int(projects["prr_count"].sum()),
        "dates_moved": int(gates["was_moved"].sum()),
    }
