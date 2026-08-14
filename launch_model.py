"""
Launch portfolio math. Streamlit-free so it can be tested and reused.

The question this page answers is different from the capacity page. There,
load is measured in machine hours. Here, load is driven by milestone EVENTS
landing in the same week and pulling on a shared support resource - the QA
lab above all. Same "load vs. capacity" shape, different unit.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

PROJECT_COLUMNS = [
    "project_id",
    "project_name",
    "project_type",
    "plant",
    "program_manager",
    "customer",
    "start_week",
    "end_week",
]

GATE_COLUMNS = [
    "project_id",
    "gate_no",
    "gate",
    "due_week",
    "completed_week",
    "status",
    "qa_lab_hours",
]

PROJECT_TYPES = ["Launch", "Prototype"]
RAG_ORDER = ["Red", "Yellow", "Green"]


class SchemaError(ValueError):
    pass


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing required column(s): {', '.join(missing)}")


def load_projects(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, PROJECT_COLUMNS, "projects")
    for col in ("start_week", "end_week"):
        df[col] = df[col].astype(int)
    return df


def load_gates(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, GATE_COLUMNS, "gates")
    df["gate_no"] = df["gate_no"].astype(int)
    df["due_week"] = df["due_week"].astype(int)
    df["completed_week"] = pd.to_numeric(df["completed_week"], errors="coerce").astype(
        "Int64"
    )
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
# Derived views
# ---------------------------------------------------------------------------
def annotate_gates(gates: pd.DataFrame, current_week: int) -> pd.DataFrame:
    """Add completion / lateness flags used by every downstream view."""
    g = gates.copy()
    g["is_complete"] = g["completed_week"].notna()
    g["is_overdue"] = (~g["is_complete"]) & (g["due_week"] < current_week)
    g["weeks_late"] = 0
    g.loc[g["is_overdue"], "weeks_late"] = current_week - g.loc[g["is_overdue"], "due_week"]
    # Display status: completed gates are shown as complete regardless of the
    # RAG they carried while open.
    g["display_status"] = g["status"].where(~g["is_complete"], "Complete")
    return g


def project_progress(projects: pd.DataFrame, gates: pd.DataFrame) -> pd.DataFrame:
    """One row per project: gates complete, total, and current worst RAG."""
    total = gates.groupby("project_id")["gate_no"].count().rename("gates_total")
    done = (
        gates[gates["is_complete"]].groupby("project_id")["gate_no"].count()
        .rename("gates_complete")
    )

    open_gates = gates[~gates["is_complete"]]
    worst = (
        open_gates.assign(
            rank=open_gates["status"].map({"Red": 0, "Yellow": 1, "Green": 2})
        )
        .sort_values("rank")
        .groupby("project_id")["status"]
        .first()
        .rename("current_status")
    )

    next_gate = (
        open_gates.sort_values(["project_id", "due_week", "gate_no"])
        .groupby("project_id")
        .agg(next_gate=("gate", "first"), next_due_week=("due_week", "first"))
    )

    out = (
        projects.set_index("project_id")
        .join(total)
        .join(done)
        .join(worst)
        .join(next_gate)
        .reset_index()
    )
    out["gates_complete"] = out["gates_complete"].fillna(0).astype(int)
    out["gates_total"] = out["gates_total"].fillna(0).astype(int)
    out["current_status"] = out["current_status"].fillna("Complete")
    out["pct_complete"] = out["gates_complete"] / out["gates_total"].where(
        out["gates_total"] > 0
    )
    return out


def qa_lab_load(
    gates: pd.DataFrame, projects: pd.DataFrame, weeks: list[int]
) -> pd.DataFrame:
    """
    QA lab hours landing per week, split by project type.

    Hours are attributed to the week the gate is due (or was completed, for
    closed gates) - a coarse but honest first pass. Real lab work spreads
    over several weeks and that refinement needs the lab's input.
    """
    g = gates.merge(
        projects[["project_id", "project_type", "plant", "program_manager"]],
        on="project_id",
        how="left",
    )
    g["load_week"] = g["completed_week"].fillna(g["due_week"]).astype(int)

    grouped = (
        g.groupby(["load_week", "project_type"], as_index=False)["qa_lab_hours"]
        .sum()
        .rename(columns={"load_week": "week", "qa_lab_hours": "hours"})
    )

    idx = pd.MultiIndex.from_product([weeks, PROJECT_TYPES], names=["week", "project_type"])
    return (
        grouped.set_index(["week", "project_type"])
        .reindex(idx, fill_value=0.0)
        .reset_index()
    )


def gate_events_per_week(
    gates: pd.DataFrame, projects: pd.DataFrame, weeks: list[int]
) -> pd.DataFrame:
    """Count of gate milestones due each week - the pile-up detector."""
    g = gates.merge(projects[["project_id", "project_type"]], on="project_id", how="left")
    counts = (
        g[g["due_week"].isin(weeks)]
        .groupby(["due_week", "gate"], as_index=False)["project_id"]
        .count()
        .rename(columns={"due_week": "week", "project_id": "events"})
    )
    return counts


def pm_workload(progress: pd.DataFrame, current_week: int, horizon: int) -> pd.DataFrame:
    """
    Projects per program manager, and how many wrap up inside the horizon.
    A PM with several projects closing at once is a reallocation candidate.
    """
    df = progress.copy()
    df["closing_soon"] = df["end_week"].between(current_week, current_week + horizon)
    df["at_risk"] = df["current_status"] == "Red"

    out = df.groupby("program_manager", as_index=False).agg(
        active_projects=("project_id", "count"),
        launches=("project_type", lambda s: int((s == "Launch").sum())),
        prototypes=("project_type", lambda s: int((s == "Prototype").sum())),
        closing_soon=("closing_soon", "sum"),
        red_projects=("at_risk", "sum"),
    )
    return out.sort_values(
        ["closing_soon", "active_projects"], ascending=False, ignore_index=True
    )


def coming_due(
    gates: pd.DataFrame, projects: pd.DataFrame, current_week: int, horizon: int
) -> pd.DataFrame:
    """Open gates due inside the horizon, plus anything already overdue."""
    g = gates[~gates["is_complete"]].merge(
        projects[["project_id", "project_name", "project_type", "plant", "program_manager"]],
        on="project_id",
        how="left",
    )
    window = g[
        (g["due_week"] <= current_week + horizon) | (g["is_overdue"])
    ].copy()
    window["when"] = window["due_week"] - current_week
    return window.sort_values(["due_week", "project_id"], ignore_index=True)
