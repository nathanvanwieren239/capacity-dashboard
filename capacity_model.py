"""
Capacity math. Deliberately free of Streamlit so it can be unit tested and
reused (scheduled report, Excel export, etc.) without launching the UI.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"

CAPACITY_COLUMNS = [
    "plant",
    "work_center",
    "week",
    "true_capacity_hours",
    "fully_staffed_capacity_hours",
    "current_capacity_hours",
]

DEMAND_COLUMNS = ["plant", "work_center", "week", "program", "demand_type", "hours"]

DEMAND_TYPES = ["Released", "Launch", "Quoted"]


@dataclass(frozen=True)
class CapacityTier:
    key: str
    label: str
    help: str


TIERS: dict[str, CapacityTier] = {
    "true_capacity_hours": CapacityTier(
        "true_capacity_hours",
        "True Capacity",
        "Theoretical ceiling: every asset, every shift, at target availability.",
    ),
    "fully_staffed_capacity_hours": CapacityTier(
        "fully_staffed_capacity_hours",
        "Fully Staffed Capacity",
        "The same assets with every shift completely crewed.",
    ),
    "current_capacity_hours": CapacityTier(
        "current_capacity_hours",
        "Current Capacity",
        "What the group delivers today, at present staffing and realized rate.",
    ),
}

DEFAULT_BASIS = "current_capacity_hours"


class SchemaError(ValueError):
    pass


def _require(df: pd.DataFrame, cols: list[str], name: str) -> None:
    missing = [c for c in cols if c not in df.columns]
    if missing:
        raise SchemaError(f"{name} is missing required column(s): {', '.join(missing)}")


def load_capacity(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, CAPACITY_COLUMNS, "capacity")
    df["week"] = df["week"].astype(int)
    for tier in TIERS:
        df[tier] = pd.to_numeric(df[tier], errors="coerce").fillna(0.0)
    return df


def load_demand(source) -> pd.DataFrame:
    df = pd.read_csv(source)
    _require(df, DEMAND_COLUMNS, "demand")
    df["week"] = df["week"].astype(int)
    df["hours"] = pd.to_numeric(df["hours"], errors="coerce").fillna(0.0)
    unknown = set(df["demand_type"].unique()) - set(DEMAND_TYPES)
    if unknown:
        raise SchemaError(
            f"demand has unrecognized demand_type value(s): {', '.join(sorted(unknown))}. "
            f"Expected one of {DEMAND_TYPES}."
        )
    return df


def load_bundled() -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load the demo CSVs, generating them first if they are absent. This keeps
    the repo free of generated files while still working on a clean clone
    (e.g. a fresh Streamlit Community Cloud deploy). Output is deterministic:
    synthetic_data.py uses a fixed seed.
    """
    cap_path = DATA_DIR / "capacity.csv"
    dem_path = DATA_DIR / "demand.csv"

    if not (cap_path.exists() and dem_path.exists()):
        import synthetic_data

        synthetic_data.main()

    return load_capacity(cap_path), load_demand(dem_path)


def visible_week_range(
    demand: pd.DataFrame, current_week: int, trim_trailing_zero: bool = True
) -> tuple[int, int]:
    """
    Start at the current week; drop trailing weeks that consume nothing so the
    chart does not run out to week 52 with dead air.
    """
    future = demand[demand["week"] >= current_week]
    if future.empty:
        return current_week, current_week

    if trim_trailing_zero:
        loaded = future.groupby("week")["hours"].sum()
        loaded = loaded[loaded > 0]
        end = int(loaded.index.max()) if not loaded.empty else current_week
    else:
        end = int(future["week"].max())

    return current_week, max(end, current_week)


def apply_filters(
    demand: pd.DataFrame,
    capacity: pd.DataFrame,
    plants: list[str],
    demand_types: list[str],
    week_start: int,
    week_end: int,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    d = demand[
        demand["plant"].isin(plants)
        & demand["demand_type"].isin(demand_types)
        & demand["week"].between(week_start, week_end)
    ].copy()
    c = capacity[
        capacity["plant"].isin(plants) & capacity["week"].between(week_start, week_end)
    ].copy()
    return d, c


def demand_by_week(demand: pd.DataFrame, by_plant: bool) -> pd.DataFrame:
    """Consumed hours per work center / week / demand type."""
    keys = ["plant", "work_center"] if by_plant else ["work_center"]
    return (
        demand.groupby(keys + ["week", "demand_type"], as_index=False)["hours"]
        .sum()
        .rename(columns={"hours": "consumed_hours"})
    )


def capacity_by_week(capacity: pd.DataFrame, by_plant: bool) -> pd.DataFrame:
    """
    Capacity per work center / week. When plants are pooled the tiers are
    summed - only valid if work can genuinely move between sites.
    """
    keys = ["plant", "work_center"] if by_plant else ["work_center"]
    return capacity.groupby(keys + ["week"], as_index=False)[list(TIERS)].sum()


def utilization(
    demand: pd.DataFrame, capacity: pd.DataFrame, basis: str, by_plant: bool
) -> pd.DataFrame:
    """
    One row per work center: total consumed vs. total available over the
    visible window, plus the worst single week.
    """
    if basis not in TIERS:
        raise ValueError(f"Unknown capacity basis: {basis}")

    keys = ["plant", "work_center"] if by_plant else ["work_center"]

    d = demand.groupby(keys + ["week"], as_index=False)["hours"].sum()
    c = capacity.groupby(keys + ["week"], as_index=False)[basis].sum()
    merged = c.merge(d, on=keys + ["week"], how="left")
    merged["hours"] = merged["hours"].fillna(0.0)
    merged["weekly_util"] = merged["hours"] / merged[basis].where(merged[basis] > 0)

    agg = merged.groupby(keys, as_index=False).agg(
        consumed_hours=("hours", "sum"),
        available_hours=(basis, "sum"),
        peak_week_util=("weekly_util", "max"),
        weeks_over=("weekly_util", lambda s: int((s > 1.0).sum())),
    )
    agg["utilization"] = agg["consumed_hours"] / agg["available_hours"].where(
        agg["available_hours"] > 0
    )
    agg = agg.sort_values("utilization", ascending=False, ignore_index=True)
    return agg


def headline_metrics(util: pd.DataFrame) -> dict[str, float | int | str]:
    if util.empty:
        return {
            "overall_util": 0.0,
            "over_count": 0,
            "tightest": "-",
            "tightest_util": 0.0,
        }
    overall = util["consumed_hours"].sum() / max(util["available_hours"].sum(), 1e-9)
    top = util.iloc[0]
    name = (
        f"{top['plant']} / {top['work_center']}"
        if "plant" in util.columns
        else str(top["work_center"])
    )
    return {
        "overall_util": float(overall),
        "over_count": int((util["utilization"] > 1.0).sum()),
        "tightest": name,
        "tightest_util": float(top["utilization"]),
    }
