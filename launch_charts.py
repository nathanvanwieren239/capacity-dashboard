"""
Plotly figure builders for the Launch Portfolio page.

Kept free of Streamlit so the figures can be rendered headlessly - for a
static preview, an emailed image, or a test - without booting the app.
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go

import launch_model as lm
from config import (
    CURRENT_WEEK,
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
    progress: pd.DataFrame, gates: pd.DataFrame, weeks: list[int]
) -> go.Figure:
    """
    Projects on Y, weeks on X. Each gate is a NUMBERED dot on its due week,
    colored by status. Simple launches show fewer dots - they skip 1-3.
    """
    fig = go.Figure()

    order = progress.sort_values(["plant", "sop_original_week", "project_id"])
    labels = {r.project_id: row_label(r) for r in order.itertuples()}

    for r in order.itertuples():
        sop = r.sop_actual_week if pd.notna(r.sop_actual_week) else r.sop_original_week
        fig.add_scatter(
            x=[r.gate_zero_week, sop],
            y=[labels[r.project_id]] * 2,
            mode="lines",
            line=dict(
                color="#DDE1E7",
                width=8,
                dash="dot" if r.launch_type == "Simple" else "solid",
            ),
            hoverinfo="skip",
            showlegend=False,
        )

    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)

    for status in lm.GATE_STATUSES:
        sub = g[g["status"] == status]
        if sub.empty:
            continue
        fig.add_scatter(
            x=sub["due_week"],
            y=sub["label"],
            mode="markers+text",
            name=status,
            text=sub["gate_code"],
            textposition="middle center",
            textfont=dict(color="white", size=11, family="Arial Black"),
            marker=dict(
                size=24, color=GATE_COLORS[status], line=dict(width=2, color="white")
            ),
            customdata=sub[
                ["gate_name", "original_week", "adjusted_week", "qa_lab_hours"]
            ],
            hovertemplate=(
                "%{y}<br>%{customdata[0]}"
                "<br>Due wk %{x} · original wk %{customdata[1]}"
                f"<br><b>{status}</b>"
                "<br>QA lab %{customdata[3]:.0f} h<extra></extra>"
            ),
        )

    fig.add_vline(
        x=CURRENT_WEEK,
        line=dict(color="#1A1D21", width=2, dash="dot"),
        annotation_text=f"Wk {CURRENT_WEEK}",
        annotation_position="top",
    )

    fig.update_layout(
        height=max(380, 38 * len(order) + 130),
        margin=dict(l=10, r=10, t=54, b=10),
        xaxis_title="Manufacturing week",
        yaxis_title=None,
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="closest",
    )
    fig.update_xaxes(range=[min(weeks) - 1, max(weeks) + 1], dtick=2)
    fig.update_yaxes(categoryorder="array", categoryarray=list(labels.values())[::-1])
    return fig


def gate_status_bars(progress: pd.DataFrame, gates: pd.DataFrame) -> go.Figure:
    """
    One horizontal bar per project, one segment per gate. The segment carries
    the gate number as its label and the status as its color.
    """
    order = progress.sort_values(["pct_complete", "project_id"], ascending=[False, True])
    labels = {r.project_id: row_label(r) for r in order.itertuples()}

    g = gates[gates["project_id"].isin(labels)].copy()
    g["label"] = g["project_id"].map(labels)
    g["seq"] = g.groupby("project_id")["gate_no"].rank(method="first").astype(int)

    fig = go.Figure()
    for seq in range(1, int(g["seq"].max()) + 1):
        sub = g[g["seq"] == seq].set_index("label").reindex(labels.values())
        present = sub["gate_code"].notna()
        fig.add_bar(
            y=sub.index,
            x=present.astype(int),
            orientation="h",
            text=sub["gate_code"].fillna(""),
            textposition="inside",
            insidetextanchor="middle",
            textfont=dict(color="white", size=12, family="Arial Black"),
            marker=dict(
                color=[
                    GATE_COLORS.get(s, "rgba(0,0,0,0)")
                    if pd.notna(s)
                    else "rgba(0,0,0,0)"
                    for s in sub["status"]
                ],
                line=dict(color="white", width=2),
            ),
            showlegend=False,
            customdata=sub[["gate_name", "status", "due_week"]].values,
            hovertemplate=(
                "%{y}<br>%{customdata[0]}"
                "<br>%{customdata[1]} · due wk %{customdata[2]}<extra></extra>"
            ),
        )

    fig.update_layout(
        barmode="stack",
        height=max(340, 32 * len(order) + 110),
        margin=dict(l=10, r=10, t=30, b=10),
        xaxis_title="Gates",
        yaxis_title=None,
        bargap=0.3,
    )
    fig.update_xaxes(dtick=1)
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
        height=330,
        margin=dict(l=10, r=10, t=36, b=10),
        xaxis_title="Manufacturing week",
        yaxis_title="QA lab hours",
        legend=dict(orientation="h", yanchor="bottom", y=1.0, xanchor="right", x=1),
        hovermode="x unified",
    )
    fig.update_xaxes(dtick=2)
    return fig
