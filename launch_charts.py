"""
Plotly figure builders for the Launch Portfolio page.

Streamlit-free, so figures can be rendered headlessly for a static preview
or dropped into a deck.
"""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import plotly.graph_objects as go

import gate_schedule as gs
import launch_model as lm
from config import (
    GATE_COLORS,
    PROJECT_STATUS_ICON,
    PROTOTYPE_TAG,
    SIMPLE_LAUNCH_TAG,
)

TYPE_COLORS = {"Launch": "#416AB9", "Prototype": "#35B0F1"}


def row_label(r) -> str:
    """Project label, tagged so simple launches and prototypes stand out."""
    if r.project_type == "Prototype":
        tag = f" {PROTOTYPE_TAG}"
    elif r.launch_type == "Simple":
        tag = f" {SIMPLE_LAUNCH_TAG}"
    else:
        tag = ""
    icon = PROJECT_STATUS_ICON.get(r.project_status, "")
    return f"{icon} {r.project_id}  {r.project_name}{tag}"


def gate_timeline(
    progress: pd.DataFrame,
    gates: pd.DataFrame,
    as_of: date,
    show_six_month: bool = True,
) -> go.Figure:
    """
    Projects on Y, calendar dates on X. Each gate is a numbered dot on its due
    date, colored by status. The 6 month review is a diamond on a dashed tail
    past Gate 4 — visible, but clearly not part of the launch itself.
    """
    fig = go.Figure()

    order = progress.sort_values(["plant", "sop_due_date", "project_id"])
    labels = {r.project_id: row_label(r) for r in order.itertuples()}

    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)
    g = g[g["due_date"].notna()]
    if not show_six_month:
        g = g[g["gate_code"] != gs.SIX_MONTH_CODE]

    # Spans: solid through the launch, dashed out to the 6 month review.
    for r in order.itertuples():
        rows = g[g["project_id"] == r.project_id]
        if rows.empty:
            continue
        launch_rows = rows[rows["gate_code"] != gs.SIX_MONTH_CODE]
        if not launch_rows.empty:
            fig.add_scatter(
                x=[launch_rows["due_date"].min(), launch_rows["due_date"].max()],
                y=[labels[r.project_id]] * 2,
                mode="lines",
                line=dict(
                    color="#DDE1E7", width=8,
                    dash="dot" if r.launch_type == "Simple" else "solid",
                ),
                hoverinfo="skip", showlegend=False,
            )
        six = rows[rows["gate_code"] == gs.SIX_MONTH_CODE]
        if not six.empty and not launch_rows.empty:
            fig.add_scatter(
                x=[launch_rows["due_date"].max(), six["due_date"].iloc[0]],
                y=[labels[r.project_id]] * 2,
                mode="lines",
                line=dict(color="#DDE1E7", width=2, dash="dash"),
                hoverinfo="skip", showlegend=False,
            )

    for status in lm.GATE_STATUSES:
        sub = g[g["status"] == status]
        if sub.empty:
            continue
        is_six = sub["gate_code"] == gs.SIX_MONTH_CODE
        fig.add_scatter(
            x=sub["due_date"], y=sub["label"],
            mode="markers+text", name=status,
            text=sub["gate_code"], textposition="middle center",
            textfont=dict(color="white", size=9, family="Arial Black"),
            marker=dict(
                size=[26 if s else 24 for s in is_six],
                color=GATE_COLORS[status],
                symbol=["diamond" if s else "circle" for s in is_six],
                line=dict(width=1.5, color="white"),
            ),
            customdata=sub[["gate_name", "plan_date", "adjusted_date", "actual_date"]],
            hovertemplate=(
                "%{y}<br>%{customdata[0]}"
                "<br>Due %{x|%d %b %Y}"
                "<br>Plan %{customdata[1]} · adjusted %{customdata[2]}"
                "<br>Actual %{customdata[3]}"
                f"<br><b>{status}</b><extra></extra>"
            ),
        )

    # add_vline() cannot take a datetime.date when it also draws an
    # annotation, so the line and label are added separately.
    stamp = pd.Timestamp(as_of)
    fig.add_shape(
        type="line", x0=stamp, x1=stamp, xref="x", yref="paper", y0=0, y1=1,
        line=dict(color="#1A1D21", width=2, dash="dot"),
    )
    fig.add_annotation(
        x=stamp, xref="x", yref="paper", y=1.02, showarrow=False,
        text="today", font=dict(size=11, color="#1A1D21"),
    )

    fig.update_layout(
        height=max(380, 38 * len(order) + 130),
        margin=dict(l=10, r=10, t=54, b=10),
        xaxis_title=None, yaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="closest",
    )
    fig.update_xaxes(tickformat="%b %Y", dtick="M1", tickangle=-40)
    fig.update_yaxes(categoryorder="array", categoryarray=list(labels.values())[::-1])
    return fig


def gate_status_bars(progress: pd.DataFrame, gates: pd.DataFrame) -> go.Figure:
    """One bar per project, one segment per gate, numbered and status-colored."""
    order = progress.sort_values(["pct_complete", "project_id"], ascending=[False, True])
    labels = {r.project_id: row_label(r) for r in order.itertuples()}

    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)
    g["seq"] = g.groupby("project_id")["gate_no"].rank(method="first").astype(int)

    fig = go.Figure()
    for seq in range(1, int(g["seq"].max()) + 1):
        sub = g[g["seq"] == seq].set_index("label").reindex(labels.values())
        fig.add_bar(
            y=sub.index,
            x=sub["gate_code"].notna().astype(int),
            orientation="h",
            text=sub["gate_code"].fillna(""),
            textposition="inside", insidetextanchor="middle",
            textfont=dict(color="white", size=11, family="Arial Black"),
            marker=dict(
                color=[
                    GATE_COLORS.get(s, "rgba(0,0,0,0)") if pd.notna(s) else "rgba(0,0,0,0)"
                    for s in sub["status"]
                ],
                line=dict(color="white", width=2),
            ),
            showlegend=False,
            customdata=sub[["gate_name", "status", "due_date"]].values,
            hovertemplate=(
                "%{y}<br>%{customdata[0]}<br>%{customdata[1]} · due %{customdata[2]}"
                "<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="stack",
        height=max(340, 32 * len(order) + 110),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Gates", yaxis_title=None, bargap=0.3,
    )
    fig.update_xaxes(dtick=1)
    fig.update_yaxes(categoryorder="array", categoryarray=list(labels.values())[::-1])
    return fig


def qa_lab_chart(load: pd.DataFrame, capacity: float) -> go.Figure:
    """Shared-resource view. Hidden on the page by default."""
    fig = go.Figure()
    if load.empty:
        return fig
    weeks = sorted(load["week_start"].unique())
    for ptype in lm.PROJECT_TYPES:
        sub = load[load["project_type"] == ptype].set_index("week_start")["hours"]
        fig.add_bar(
            x=weeks, y=[float(sub.get(w, 0.0)) for w in weeks],
            name=ptype, marker_color=TYPE_COLORS[ptype],
            hovertemplate=f"{ptype}<br>w/c %{{x|%d %b}}: %{{y:,.0f}} h<extra></extra>",
        )
    fig.add_scatter(
        x=weeks, y=[capacity] * len(weeks), mode="lines", name="Lab capacity",
        line=dict(color="#D62728", width=2, dash="dash"),
    )
    fig.update_layout(
        barmode="stack", height=330, margin=dict(l=10, r=10, t=36, b=10),
        xaxis_title=None, yaxis_title="QA lab hours",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(tickformat="%d %b")
    return fig
