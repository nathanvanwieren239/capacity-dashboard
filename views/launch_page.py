"""
Launch Portfolio page.

Answers a different question than the capacity page. There, load is machine
hours. Here, load is milestone EVENTS landing in the same week and pulling on
a shared support resource - the QA lab above all. Prototypes sit in the same
table as launches precisely because they draw on that same lab.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

import launch_model as lm
from config import CURRENT_WEEK, STATUS_COLORS, YEAR

TYPE_COLORS = {"Launch": "#416AB9", "Prototype": "#35B0F1"}


@st.cache_data
def _bundled():
    return lm.load_bundled()


# ---------------------------------------------------------------------------
# Charts
# ---------------------------------------------------------------------------
def gate_timeline(
    progress: pd.DataFrame, gates: pd.DataFrame, weeks: list[int]
) -> go.Figure:
    """
    Projects on Y, weeks of the year on X, gate due dates plotted as markers
    colored by review status. The shape the launch engineer sketched.
    """
    fig = go.Figure()

    order = progress.sort_values(["end_week", "project_id"])
    labels = {
        r.project_id: f"{r.project_id}  {r.project_name}" for r in order.itertuples()
    }

    # Project span line.
    for r in order.itertuples():
        fig.add_scatter(
            x=[r.start_week, r.end_week],
            y=[labels[r.project_id]] * 2,
            mode="lines",
            line=dict(color="#D5D9E0", width=6),
            hoverinfo="skip",
            showlegend=False,
        )

    # Gate markers, one trace per status so the legend is meaningful.
    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)

    for status in ["Complete", "Green", "Yellow", "Red"]:
        sub = g[g["display_status"] == status]
        if sub.empty:
            continue
        fig.add_scatter(
            x=sub["due_week"],
            y=sub["label"],
            mode="markers",
            name=status,
            marker=dict(
                size=13,
                color=STATUS_COLORS[status],
                symbol="circle" if status == "Complete" else "diamond",
                line=dict(width=1, color="white"),
            ),
            customdata=sub[["gate", "qa_lab_hours"]],
            hovertemplate=(
                "%{y}<br>%{customdata[0]}<br>Due wk %{x}"
                f"<br>{status}"
                "<br>QA lab %{customdata[1]:.0f} h<extra></extra>"
            ),
        )

    fig.add_vline(
        x=CURRENT_WEEK,
        line=dict(color="#1A1D21", width=2, dash="dot"),
        annotation_text=f"Wk {CURRENT_WEEK}",
        annotation_position="top",
    )

    fig.update_layout(
        height=max(360, 34 * len(order) + 130),
        margin=dict(l=10, r=10, t=50, b=10),
        xaxis_title="Manufacturing week",
        yaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="closest",
    )
    fig.update_xaxes(range=[min(weeks) - 1, max(weeks) + 1], dtick=2)
    fig.update_yaxes(categoryorder="array", categoryarray=list(labels.values())[::-1])
    return fig


def gate_progress_bars(progress: pd.DataFrame, gates: pd.DataFrame) -> go.Figure:
    """
    One horizontal bar per project, one segment per gate, colored by review
    status. "Launch 123 is at Gate 2 so it has 2 bars" - with the RAG in it.
    """
    order = progress.sort_values(["pct_complete", "project_id"], ascending=[False, True])
    labels = {
        r.project_id: f"{r.project_id}  {r.project_name}" for r in order.itertuples()
    }

    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)
    g = g.sort_values(["label", "gate_no"])

    fig = go.Figure()
    max_gates = int(g["gate_no"].max())

    for gate_no in range(1, max_gates + 1):
        sub = g[g["gate_no"] == gate_no]
        if sub.empty:
            continue
        # Reindex onto every project so segments line up.
        sub = sub.set_index("label").reindex(labels.values())
        fig.add_bar(
            y=sub.index,
            x=[1 if pd.notna(s) else 0 for s in sub["gate"]],
            orientation="h",
            marker=dict(
                color=[
                    STATUS_COLORS.get(s, "#C7CBD1") if pd.notna(s) else "rgba(0,0,0,0)"
                    for s in sub["display_status"]
                ],
                line=dict(color="white", width=2),
            ),
            name=f"Gate {gate_no}",
            showlegend=False,
            customdata=sub[["gate", "display_status", "due_week"]].values,
            hovertemplate=(
                "%{y}<br>Gate " + str(gate_no) + ": %{customdata[0]}"
                "<br>%{customdata[1]} · due wk %{customdata[2]}<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="stack",
        height=max(320, 30 * len(order) + 110),
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="Gates",
        yaxis_title=None,
        bargap=0.35,
    )
    fig.update_xaxes(dtick=1, range=[0, max_gates])
    fig.update_yaxes(categoryorder="array", categoryarray=list(labels.values())[::-1])
    return fig


def qa_lab_chart(load: pd.DataFrame, weeks: list[int], capacity: float) -> go.Figure:
    fig = go.Figure()
    for ptype in lm.PROJECT_TYPES:
        sub = load[load["project_type"] == ptype].set_index("week")["hours"]
        fig.add_bar(
            x=weeks,
            y=sub.reindex(weeks, fill_value=0.0).values,
            name=ptype,
            marker_color=TYPE_COLORS[ptype],
            hovertemplate=f"{ptype}<br>Wk %{{x}}: %{{y:,.0f}} h<extra></extra>",
        )

    fig.add_scatter(
        x=weeks,
        y=[capacity] * len(weeks),
        mode="lines",
        name="Lab capacity",
        line=dict(color="#D62728", width=2, dash="dash"),
        hovertemplate="Capacity %{y:,.0f} h<extra></extra>",
    )

    fig.update_layout(
        barmode="stack",
        height=340,
        margin=dict(l=10, r=10, t=40, b=10),
        xaxis_title="Manufacturing week",
        yaxis_title="QA lab hours",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(dtick=2)
    return fig


# ---------------------------------------------------------------------------
# Controls
# ---------------------------------------------------------------------------
projects_all, gates_all = _bundled()

st.sidebar.divider()
st.sidebar.subheader("Portfolio view")

plants = st.sidebar.multiselect(
    "Plants", sorted(projects_all["plant"].unique()),
    default=sorted(projects_all["plant"].unique()),
)
types = st.sidebar.multiselect(
    "Project type", lm.PROJECT_TYPES, default=lm.PROJECT_TYPES
)
pms = st.sidebar.multiselect(
    "Program manager", sorted(projects_all["program_manager"].unique()),
    default=sorted(projects_all["program_manager"].unique()),
)
horizon = st.sidebar.slider(
    "Look-ahead (weeks)", 2, 20, 8,
    help="Window used for 'coming due' and for flagging projects closing soon.",
)
lab_capacity = st.sidebar.number_input(
    "QA lab capacity (h/week)", min_value=20, max_value=600, value=120, step=10,
    help="Placeholder. Needs the real number from the lab.",
)

if not (plants and types and pms):
    st.warning("Select at least one plant, project type and program manager.")
    st.stop()

projects = projects_all[
    projects_all["plant"].isin(plants)
    & projects_all["project_type"].isin(types)
    & projects_all["program_manager"].isin(pms)
]
if projects.empty:
    st.warning("No projects match those filters.")
    st.stop()

gates = lm.annotate_gates(
    gates_all[gates_all["project_id"].isin(projects["project_id"])], CURRENT_WEEK
)
progress = lm.project_progress(projects, gates)

weeks = list(range(CURRENT_WEEK, 53))
qa_load = lm.qa_lab_load(gates, projects, weeks)
qa_by_week = qa_load.groupby("week", as_index=False)["hours"].sum()
due = lm.coming_due(gates, projects, CURRENT_WEEK, horizon)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🚀 Launch Portfolio")
st.caption(
    f"Week {CURRENT_WEEK} of {YEAR} · {len(projects)} active projects · "
    f"{int((projects['project_type'] == 'Prototype').sum())} prototypes · "
    "synthetic data"
)

peak = qa_by_week.loc[qa_by_week["hours"].idxmax()] if not qa_by_week.empty else None
overdue_n = int(gates["is_overdue"].sum())

k1, k2, k3, k4 = st.columns(4)
k1.metric("Gates due in next %d wks" % horizon, int((due["when"] >= 0).sum()))
k2.metric("Overdue gates", overdue_n)
k3.metric(
    "Peak QA lab week",
    f"Wk {int(peak['week'])}" if peak is not None else "-",
    delta=f"{peak['hours']:.0f} h vs {lab_capacity} h cap" if peak is not None else None,
    delta_color="inverse",
)
k4.metric("Projects at Red", int((progress["current_status"] == "Red").sum()))

st.divider()

# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
st.subheader("Gate timeline")
st.caption(
    "Each row is a project; markers are gate reviews at their due week, "
    "colored by status. Vertical dotted line is today."
)
st.plotly_chart(gate_timeline(progress, gates, weeks), width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# QA lab load - the pile-up detector
# ---------------------------------------------------------------------------
st.subheader("Shared resource load — QA lab")
st.caption(
    "Hours are booked to the week each gate is due. This is what shows five "
    "PPAP submissions landing together."
)
st.plotly_chart(qa_lab_chart(qa_load, weeks, float(lab_capacity)), width="stretch")

over_weeks = qa_by_week[qa_by_week["hours"] > lab_capacity]["week"].tolist()
if over_weeks:
    st.warning(
        f"QA lab is over capacity in week(s): "
        f"{', '.join(str(w) for w in over_weeks)}."
    )

st.divider()

# ---------------------------------------------------------------------------
# Gate progress + PM workload
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Gate progress")
    st.caption("One segment per gate, colored by review status.")
    st.plotly_chart(gate_progress_bars(progress, gates), width="stretch")

with right:
    st.subheader("Program manager load")
    st.caption(f"Projects closing within {horizon} weeks free that PM up.")
    pm = lm.pm_workload(progress, CURRENT_WEEK, horizon).rename(
        columns={
            "program_manager": "PM",
            "active_projects": "Active",
            "launches": "Launches",
            "prototypes": "Protos",
            "closing_soon": "Closing",
            "red_projects": "Red",
        }
    )
    st.dataframe(pm, width="stretch", hide_index=True)

    st.subheader("Status summary")
    summary = (
        progress.groupby("current_status", as_index=False)["project_id"]
        .count()
        .rename(columns={"current_status": "Status", "project_id": "Projects"})
    )
    st.dataframe(summary, width="stretch", hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Coming due
# ---------------------------------------------------------------------------
st.subheader(f"Coming due — next {horizon} weeks (and anything overdue)")
if due.empty:
    st.info("Nothing due in this window.")
else:
    tbl = due.copy()
    tbl["When"] = tbl.apply(
        lambda r: f"{int(r['weeks_late'])} wk overdue"
        if r["is_overdue"]
        else ("this week" if r["when"] == 0 else f"in {int(r['when'])} wk"),
        axis=1,
    )
    tbl = tbl[
        ["project_id", "project_name", "project_type", "plant", "program_manager",
         "gate", "due_week", "When", "status", "qa_lab_hours"]
    ].rename(
        columns={
            "project_id": "ID",
            "project_name": "Project",
            "project_type": "Type",
            "plant": "Plant",
            "program_manager": "PM",
            "gate": "Gate",
            "due_week": "Due wk",
            "status": "Status",
            "qa_lab_hours": "QA lab h",
        }
    )
    st.dataframe(tbl, width="stretch", hide_index=True)

with st.expander("What this page assumes, and what it still needs"):
    st.markdown(
        """
**Modeled here**

- Launches and prototypes share one table, because they share the QA lab.
- Gate review status is a simple R/Y/G carried on each open gate. Completed
  gates display as complete regardless of the RAG they held while open.
- QA lab hours are booked entirely to the week a gate is due. Real lab work
  spreads across several weeks — that refinement needs the lab's input.

**Placeholders**

- Project names, PM names, customers and gate names are invented.
- The gate list is a generic 6-step launch and 3-step prototype path, not
  NN's actual gate model.
- QA lab capacity is a single number for the whole network.
- Only the QA lab is modeled. Other shared resources (gage lab, tooling,
  PPAP coordinator) would follow the same pattern.

**Open questions**

- What are the real gate names and how many are there?
- Does gate work draw on other shared resources worth tracking?
- Is Marshall in scope? It came up in the review-meeting discussion but is
  not one of the three sites on the capacity page.
- Who updates this, and how often? The monthly review cadence suggests the
  data lands as an export rather than live.
"""
    )
