"""
Machine capacity page - load vs. capacity by work center.

Moved verbatim from the original single-page app.py. Page config, auth and
the sidebar logo now live in app.py so they run once for every page.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import capacity_model as cm
from config import CAPACITY_CURRENT_WEEK as CURRENT_WEEK, CAPACITY_YEAR as YEAR

# Released uses the NN brand blue; Launch stays high-contrast orange on
# purpose - it is the series the whole story hangs on.
DEMAND_COLORS = {
    "Released": "#416AB9",
    "Launch": "#F58518",
    "Quoted": "#B3B3B3",
}

TIER_STYLE = {
    "true_capacity_hours": dict(color="#7B52AB", dash="dash"),
    "fully_staffed_capacity_hours": dict(color="#2CA02C", dash="dashdot"),
    "current_capacity_hours": dict(color="#D62728", dash="dot"),
}


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
@st.cache_data
def _bundled():
    return cm.load_bundled()


def get_data():
    """Sidebar data source control. Returns (capacity, demand, source_label)."""
    st.sidebar.subheader("Data source")
    mode = st.sidebar.radio(
        "Source",
        ["Synthetic demo data", "Upload CSV"],
        label_visibility="collapsed",
    )

    if mode == "Upload CSV":
        cap_file = st.sidebar.file_uploader("capacity.csv", type="csv", key="cap")
        dem_file = st.sidebar.file_uploader("demand.csv", type="csv", key="dem")
        if cap_file and dem_file:
            try:
                return cm.load_capacity(cap_file), cm.load_demand(dem_file), "Uploaded"
            except cm.SchemaError as exc:
                st.sidebar.error(str(exc))
                st.stop()
        st.sidebar.info("Upload both files, or switch back to demo data.")
        st.stop()

    cap, dem = _bundled()
    return cap, dem, "Synthetic demo data"


# ---------------------------------------------------------------------------
# Chart
# ---------------------------------------------------------------------------
def work_center_chart(
    title: str,
    dem: pd.DataFrame,
    cap: pd.DataFrame,
    demand_types: list[str],
    shown_tiers: list[str],
    weeks: list[int],
) -> go.Figure:
    fig = go.Figure()

    for dtype in cm.DEMAND_TYPES:
        if dtype not in demand_types:
            continue
        series = (
            dem[dem["demand_type"] == dtype]
            .set_index("week")["consumed_hours"]
            .reindex(weeks, fill_value=0.0)
        )
        fig.add_bar(
            x=weeks,
            y=series.values,
            name=dtype,
            marker_color=DEMAND_COLORS[dtype],
            hovertemplate=f"{dtype}<br>Wk %{{x}}: %{{y:,.0f}} h<extra></extra>",
        )

    cap_idx = cap.set_index("week")
    for tier in shown_tiers:
        series = cap_idx[tier].reindex(weeks, fill_value=0.0)
        fig.add_scatter(
            x=weeks,
            y=series.values,
            name=cm.TIERS[tier].label,
            mode="lines",
            line=dict(width=2, shape="hv", **TIER_STYLE[tier]),
            hovertemplate=(
                f"{cm.TIERS[tier].label}<br>Wk %{{x}}: %{{y:,.0f}} h<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="stack",
        title=dict(text=title, x=0, font=dict(size=15)),
        height=300,
        margin=dict(l=10, r=10, t=60, b=10),
        legend=dict(
            orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1,
            font=dict(size=10),
        ),
        xaxis_title="Manufacturing week",
        yaxis_title="Hours",
        hovermode="x unified",
    )
    fig.update_xaxes(dtick=2)
    return fig


# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------
capacity, demand, source_label = get_data()

st.sidebar.divider()
st.sidebar.subheader("View")

all_plants = sorted(capacity["plant"].unique())
plants = st.sidebar.multiselect("Plants", all_plants, default=all_plants)
if not plants:
    st.warning("Select at least one plant.")
    st.stop()

pool_plants = st.sidebar.toggle(
    "Pool plants into one view",
    value=False,
    help=(
        "Off = one chart per plant/work center. On = capacity summed across "
        "plants. Only meaningful if a program can actually be moved between "
        "sites."
    ),
)

basis = st.sidebar.selectbox(
    "Capacity basis for utilization",
    list(cm.TIERS),
    index=list(cm.TIERS).index(cm.DEFAULT_BASIS),
    format_func=lambda k: cm.TIERS[k].label,
    help="Which line utilization % is measured against.",
)
st.sidebar.caption(cm.TIERS[basis].help)

shown_tiers = st.sidebar.multiselect(
    "Capacity lines to plot",
    list(cm.TIERS),
    default=list(cm.TIERS),
    format_func=lambda k: cm.TIERS[k].label,
)

demand_types = st.sidebar.multiselect(
    "Demand included", cm.DEMAND_TYPES, default=["Released", "Launch"]
)
if not demand_types:
    st.warning("Select at least one demand type.")
    st.stop()

wk_lo, wk_hi = cm.visible_week_range(
    demand[demand["demand_type"].isin(demand_types)], CURRENT_WEEK
)
week_start, week_end = st.sidebar.slider("Week range", 1, 52, (wk_lo, wk_hi))

f_demand, f_capacity = cm.apply_filters(
    demand, capacity, plants, demand_types, week_start, week_end
)

by_plant = not pool_plants
d_agg = cm.demand_by_week(f_demand, by_plant)
c_agg = cm.capacity_by_week(f_capacity, by_plant)
util = cm.utilization(f_demand, f_capacity, basis, by_plant)
metrics = cm.headline_metrics(util)

# --- header ---------------------------------------------------------------
st.title("🏭 Machine Capacity — future state")
st.info(
    "**Future state.** This page is a concept for machine-hour capacity and "
    "runs on entirely invented plants, work centers and demand. It is not "
    "connected to the launch tracker. The working tool is the "
    "**Launch Portfolio** page.",
    icon="🧪",
)
st.caption(
    f"Weeks {week_start}–{week_end} ({YEAR}) · {', '.join(plants)} · "
    f"utilization measured against **{cm.TIERS[basis].label}** · "
    f"source: {source_label}"
)

k1, k2, k3, k4 = st.columns(4)
k1.metric("Overall utilization", f"{metrics['overall_util']:.0%}")
k2.metric("Work centers over capacity", metrics["over_count"])
k3.metric("Tightest work center", metrics["tightest"])
k4.metric("Its utilization", f"{metrics['tightest_util']:.0%}")

st.divider()

# --- chart grid -----------------------------------------------------------
weeks = list(range(week_start, week_end + 1))
group_keys = ["plant", "work_center"] if by_plant else ["work_center"]

groups = sorted({tuple(r) for r in c_agg[group_keys].drop_duplicates().to_numpy()})

cols = st.columns(2)
for i, key in enumerate(groups):
    mask_d = pd.Series(True, index=d_agg.index)
    mask_c = pd.Series(True, index=c_agg.index)
    for col, val in zip(group_keys, key):
        mask_d &= d_agg[col] == val
        mask_c &= c_agg[col] == val

    title = " / ".join(str(k) for k in key)
    fig = work_center_chart(
        title, d_agg[mask_d], c_agg[mask_c], demand_types, shown_tiers, weeks
    )
    cols[i % 2].plotly_chart(fig, width="stretch")

st.divider()

# --- bottleneck table -----------------------------------------------------
st.subheader("Bottleneck ranking")
table = util.copy()
table["utilization"] = table["utilization"].map(lambda v: f"{v:.0%}")
table["peak_week_util"] = table["peak_week_util"].map(
    lambda v: f"{v:.0%}" if pd.notna(v) else "-"
)
table["consumed_hours"] = table["consumed_hours"].map(lambda v: f"{v:,.0f}")
table["available_hours"] = table["available_hours"].map(lambda v: f"{v:,.0f}")
table = table.rename(
    columns={
        "plant": "Plant",
        "work_center": "Work center",
        "consumed_hours": "Consumed h",
        "available_hours": "Available h",
        "utilization": "Utilization",
        "peak_week_util": "Peak week",
        "weeks_over": "Weeks over",
    }
)
st.dataframe(table, width="stretch", hide_index=True)

with st.expander("Assumptions and open questions"):
    st.markdown(
        """
**Placeholders that need real answers before this means anything**

- Plant and work center names are invented.
- The three capacity tiers are modeled as fixed ratios off a 144 h/machine/week
  ceiling. Real staffing ratios and operator coverage need to come from the
  plants.
- Pooling plants sums capacity. That is only valid if a program can actually
  move between sites — tooling, PPAP, and customer approval usually say
  otherwise.
- Setup/changeover is baked into demand hours rather than modeled separately.
- Quoted demand is shown at full value, not probability weighted.
- Current week is hard-coded to 33.
"""
    )
