"""
Launch Portfolio page.

Gate status is derived from dates (complete / in progress / behind) and is
deliberately separate from the project status the PM assesses.

Due date falls back: adjusted date if one exists, otherwise the plan date.
On-time is measured against that, per the 19 Aug review. The scorecard also
shows on-time against the original plan, so the gap between the two says how
much of the record rests on dates that were moved.
"""

from __future__ import annotations

from datetime import timedelta

import pandas as pd
import streamlit as st

import auth
import gate_schedule as gs
import launch_model as lm
import store
import tracker_import
from config import PROJECT_STATUS_ICON, SIMPLE_LAUNCH_TAG, today
from launch_charts import gate_status_bars, gate_timeline, qa_lab_chart

NOW = today()


def _d(value):
    """date_input rejects pandas NaT, so empty dates must become None."""
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date()


@st.cache_data
def _bundled():
    return lm.load_bundled()


projects_all, gates_all = _bundled()

# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------
st.sidebar.divider()
st.sidebar.subheader("Portfolio view")

plant_opts = sorted(projects_all["plant"].dropna().unique())
plants = st.sidebar.multiselect(
    "Plants", plant_opts, default=plant_opts,
    help="Lothian views every site; each plant meeting filters to one.",
)

types = st.sidebar.multiselect(
    "Project type", lm.PROJECT_TYPES, default=lm.PROJECT_TYPES
)

# Launch type only applies to launches. When launches are filtered out it is
# disabled rather than left to silently empty the page - that was the bug
# raised in review.
launch_selectable = "Launch" in types
launch_opts = ["Full", "Simple"]
launch_types = st.sidebar.multiselect(
    "Launch type", launch_opts,
    default=launch_opts,
    disabled=not launch_selectable,
    help=(
        "Full or simple. Prototypes have neither, so they are controlled by "
        "Project type above."
        if launch_selectable
        else "Only applies to launches. Add Launch to Project type to use this."
    ),
)

pm_opts = sorted(projects_all["program_manager"].dropna().unique())
pms = st.sidebar.multiselect("Program manager", pm_opts, default=pm_opts)

hide_launched = st.sidebar.toggle("Hide launched projects", value=True)
show_six_month = st.sidebar.toggle(
    "Show 6 month reviews", value=True,
    help="Post-SOP monitoring, shown as a diamond on a dashed tail.",
)
horizon_days = st.sidebar.slider(
    "Look-ahead (days)", 14, 180, 60, step=7,
    help="Window for 'coming due' and for flagging projects closing soon.",
)

show_qa = st.sidebar.toggle(
    "Show QA lab load", value=False,
    help="Shared-resource view. Hidden by default — the lab data is invented.",
)
lab_capacity = 120.0
if show_qa:
    lab_capacity = float(
        st.sidebar.number_input("QA lab capacity (h/week)", 20, 600, 120, 10)
    )

if not (plants and types and pms):
    st.warning("Select at least one plant, project type and program manager.")
    st.stop()

# Prototypes are matched on project type; launches additionally on launch type.
is_launch = projects_all["project_type"] == "Launch"
type_match = projects_all["project_type"].isin(types)
launch_match = ~is_launch | projects_all["launch_type"].isin(
    launch_types if launch_selectable else []
)

scope = projects_all[
    projects_all["plant"].isin(plants)
    & type_match
    & launch_match
    & projects_all["program_manager"].isin(pms)
]

scope_gates = lm.annotate_gates(
    gates_all[gates_all["project_id"].isin(scope["project_id"])], NOW
)
scope_progress = lm.project_progress(scope, scope_gates) if len(scope) else scope

if scope.empty:
    st.warning("No projects match those filters.")
    st.stop()

projects = (
    scope_progress[scope_progress["sop_actual_date"].isna()]
    if hide_launched
    else scope_progress
)
if projects.empty:
    st.warning("Every matching project has launched. Turn off 'Hide launched'.")
    st.stop()

gates = scope_gates[scope_gates["project_id"].isin(projects["project_id"])]
progress = projects
due = lm.coming_due(gates, scope, NOW, horizon_days)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🚀 Launch Portfolio")
st.caption(
    f"{NOW:%d %b %Y} · {len(projects)} projects · "
    f"{int((projects['launch_type'] == 'Simple').sum())} simple launches · "
    f"{int((projects['project_type'] == 'Prototype').sum())} prototypes · "
    "synthetic data"
)

open_due = due[due["days_out"].notna() & (due["days_out"] >= 0)]
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Gates due in {horizon_days} days", len(open_due))
k2.metric("Gates behind schedule", int(gates["is_behind"].sum()))
k3.metric("Projects at Red", int((progress["project_status"] == "Red").sum()))
six_open = gates[
    (gates["gate_code"] == gs.SIX_MONTH_CODE) & (~gates["is_complete"])
]
k4.metric("6 month reviews open", len(six_open))

st.divider()

# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
st.subheader("Gate timeline")
st.caption(
    "Each dot is a gate on its due date, numbered by gate. "
    "Green complete · yellow in progress · red behind. "
    f"{SIMPLE_LAUNCH_TAG} rows run 0 → SL → 4 and skip gates 1–3. "
    "The diamond on the dashed tail is the 6 month post-SOP review. "
    "Leading circle is project status."
)
st.plotly_chart(
    gate_timeline(progress, gates, NOW, show_six_month), width="stretch"
)

st.divider()

# ---------------------------------------------------------------------------
# Status bars + scorecard
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Gate status")
    st.caption("One segment per gate, numbered, colored by status.")
    st.plotly_chart(gate_status_bars(progress, gates), width="stretch")

with right:
    st.subheader("Scorecard")
    st.caption("Includes launched projects even when hidden above.")
    sc = lm.scorecard(scope_progress, scope_gates, NOW)

    c1, c2 = st.columns(2)
    c1.metric(
        "Gate reviews on time",
        f"{sc['gate_on_time']:.0%}" if sc["gates_closed"] else "—",
        help=f"{sc['gates_closed']} closed gates, against the adjusted date "
             "where one exists, otherwise the plan date.",
    )
    c2.metric(
        "…against original plan",
        f"{sc['gate_on_time_vs_plan']:.0%}" if sc["gates_closed"] else "—",
        delta=(
            f"{(sc['gate_on_time_vs_plan'] - sc['gate_on_time']):.0%} vs adjusted"
            if sc["gates_closed"] else None
        ),
        help="Same gates measured against the date first committed. The gap "
             "is how much of the on-time record depends on moved dates.",
    )
    c3, c4 = st.columns(2)
    c3.metric(
        "Launches on time",
        f"{sc['launch_on_time']:.0%}" if sc["launches_closed"] else "—",
        help=f"{sc['launches_closed']} launched projects.",
    )
    c4.metric(
        "PRRs, 12 mo post-SOP", sc["prr_12mo"],
        help=f"Across {sc['prr_projects']} projects launched in the last "
             "12 months. Currently entered by hand; Galaxy could feed this.",
    )
    st.caption(f"Dates moved: **{sc['dates_moved']}** gates carry an adjusted date.")

    st.subheader("Program manager load")
    pm = lm.pm_workload(progress, NOW, horizon_days).rename(
        columns={
            "program_manager": "PM", "active_projects": "Active",
            "launches": "Launches", "prototypes": "Protos",
            "closing_soon": "Closing", "red_projects": "Red",
        }
    )
    st.dataframe(pm, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# QA lab (hidden by default)
# ---------------------------------------------------------------------------
if show_qa:
    st.divider()
    st.subheader("Shared resource load — QA lab")
    st.caption("QA lab hours per gate are invented. Needs real numbers.")
    qa = lm.qa_lab_load(gates, scope, NOW, NOW + timedelta(days=270))
    st.plotly_chart(qa_lab_chart(qa, lab_capacity), width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# Coming due
# ---------------------------------------------------------------------------
st.subheader(f"Coming due — next {horizon_days} days (and anything behind)")
if due.empty:
    st.info("Nothing due in this window.")
else:
    t = due.copy()
    t["When"] = t.apply(
        lambda r: f"{int(r['days_late'])} d behind"
        if r["is_behind"]
        else ("today" if r["days_out"] == 0 else f"in {int(r['days_out'])} d"),
        axis=1,
    )
    t["Moved"] = t["was_moved"].map({True: "yes", False: ""})
    t = t[
        ["project_id", "project_name", "launch_type", "plant", "program_manager",
         "job_number", "gate_code", "gate_name", "plan_date", "due_date",
         "Moved", "When"]
    ].rename(
        columns={
            "project_id": "ID", "project_name": "Project", "launch_type": "Type",
            "plant": "Plant", "program_manager": "PM", "job_number": "Job #",
            "gate_code": "Gate", "gate_name": "Gate name",
            "plan_date": "Plan", "due_date": "Due",
        }
    )
    st.dataframe(t, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Project detail
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Project detail")
detail_id = st.selectbox(
    "Project", scope["project_id"].tolist(),
    format_func=lambda i: (
        f"{PROJECT_STATUS_ICON.get(scope.loc[scope['project_id'] == i, 'project_status'].iloc[0], '')} "
        f"{i} — {scope.loc[scope['project_id'] == i, 'project_name'].iloc[0]}"
    ),
    key="detail_pick",
)
d = scope[scope["project_id"] == detail_id].iloc[0]

dc1, dc2, dc3 = st.columns(3)
dc1.markdown(
    f"**Part** {d['customer_part_number']}  \n"
    f"**Description** {d['description']}  \n"
    f"**Customer** {d['customer']}  \n"
    f"**Plant / Div** {d['plant']} / {d['div']}"
)
dc2.markdown(
    f"**PM** {d['program_manager']}  \n"
    f"**Sales** {d['sales_person']}  \n"
    f"**Job #** {d['job_number']}  \n"
    f"**Opportunity** {d['opportunity_number']}"
)
dc3.markdown(
    f"**QMSI #** {d['qmsi_number']} rev **{d['qmsi_revision']}**  \n"
    f"**RPN** {d['rpn']}  \n"
    f"**Launch risk** {d['launch_risk']}  \n"
    f"**Peak annual sales** ${float(d['peak_annual_sales'] or 0):,.0f}"
)
st.caption(
    f"CapEx ${float(d['qmsi_capex'] or 0):,.0f} · CER {d['cer_number']} "
    f"${float(d['cer_amount'] or 0):,.0f} ({d['cer_status']}) · "
    f"PRRs {int(d['prr_count'])} "
    f"({d['prr_start_date'] or '—'} → {d['prr_end_date'] or '—'})"
)
if str(d["notes"]).strip():
    st.info(f"**Notes** {d['notes']}")

st.dataframe(
    scope_gates[scope_gates["project_id"] == detail_id][
        ["gate_code", "gate_name", "plan_date", "adjusted_date",
         "actual_date", "due_date", "status"]
    ].rename(
        columns={
            "gate_code": "Gate", "gate_name": "Name", "plan_date": "Plan",
            "adjusted_date": "Adjusted", "actual_date": "Actual",
            "due_date": "Due", "status": "Status",
        }
    ),
    width="stretch", hide_index=True,
)

# ---------------------------------------------------------------------------
# Data entry - editors only
# ---------------------------------------------------------------------------
st.divider()
st.subheader("Data entry")

if not auth.is_editor():
    st.info(
        "Read-only. Adding or editing records requires the editor login. "
        "Edit access is intended for Ryan, Lothian and possibly Craig."
    )
else:
    role = auth.current_role()
    st.caption(
        "Changes are written to the tracker files and appear immediately. "
        "Every change is recorded in the audit log below."
    )

    tab_edit, tab_gate0, tab_proto, tab_import = st.tabs(
        ["Edit existing", "Add New Gate Zero", "Add New Prototype",
         "Import tracker workbook"]
    )

    # -- edit existing --------------------------------------------------
    with tab_edit:
        def _pick_label(i: str) -> str:
            r = projects_all.loc[projects_all["project_id"] == i].iloc[0]
            icon = PROJECT_STATUS_ICON.get(r["project_status"], "")
            return f"{icon} {i} · {r['project_name']} · {r['plant']} · {r['program_manager']}"

        pick = st.selectbox(
            "Which project are you editing?",
            projects_all.sort_values(["plant", "project_name"])["project_id"].tolist(),
            format_func=_pick_label,
            key="edit_pick",
            help="Type to search by part number, description, plant or PM.",
        )
        rec = projects_all[projects_all["project_id"] == pick].iloc[0]

        with st.form("edit_project"):
            st.markdown(f"### Editing — {rec['project_name']}")
            st.caption(
                f"`{pick}` · {rec['plant']} · PM {rec['program_manager']} · "
                f"{rec['launch_type']} launch"
            )
            st.markdown("**Project**")
            c1, c2, c3 = st.columns(3)
            e_part = c1.text_input("Customer part number", str(rec["customer_part_number"]))
            e_desc = c2.text_input("Description", str(rec["description"]))
            e_job = c3.text_input("Job number", str(rec["job_number"]))

            c4, c5, c6 = st.columns(3)
            e_plant = c4.selectbox(
                "Plant", plant_opts,
                index=plant_opts.index(rec["plant"]) if rec["plant"] in plant_opts else 0,
            )
            e_div = c5.selectbox(
                "Div", ["MS", "PS"],
                index=["MS", "PS"].index(rec["div"]) if rec["div"] in ("MS", "PS") else 0,
            )
            e_pm = c6.selectbox(
                "Program manager", pm_opts,
                index=pm_opts.index(rec["program_manager"])
                if rec["program_manager"] in pm_opts else 0,
            )

            st.markdown("**Gate Zero form fields**")
            c7, c8, c9 = st.columns(3)
            e_qmsi = c7.text_input("QMSI #", str(rec["qmsi_number"]))
            e_qmsi_rev = c8.text_input("QMSI revision", str(rec["qmsi_revision"]))
            e_opp = c9.text_input("Opportunity #", str(rec["opportunity_number"]))

            c10, c11, c12 = st.columns(3)
            e_cust = c10.text_input("Customer", str(rec["customer"]))
            e_sales = c11.text_input("Sales person", str(rec["sales_person"]))
            e_rpn = c12.number_input("RPN", 0, 1000, int(rec["rpn"] or 0))

            c13, c14, c15 = st.columns(3)
            risk_opts = ["Low", "Medium", "High"]
            e_risk = c13.selectbox(
                "Launch risk", risk_opts,
                index=risk_opts.index(rec["launch_risk"])
                if rec["launch_risk"] in risk_opts else 0,
            )
            e_process = c14.text_input("Launch process", str(rec["launch_process"]))
            e_support = c15.text_input("Support required", str(rec["support_required"]))

            c16, c17, c18 = st.columns(3)
            e_sales_amt = c16.number_input(
                "Peak annual sales ($)", 0.0, 1e9,
                float(rec["peak_annual_sales"] or 0), step=10000.0,
            )
            e_capex = c17.number_input(
                "QMSI CapEx ($)", 0.0, 1e9, float(rec["qmsi_capex"] or 0), step=10000.0
            )
            e_cer_amt = c18.number_input(
                "CER amount ($)", 0.0, 1e9, float(rec["cer_amount"] or 0), step=10000.0
            )

            c19, c20 = st.columns(2)
            e_cer_status = c19.text_input("CER status", str(rec["cer_status"]))
            e_cer_no = c20.text_input("CER number", str(rec["cer_number"]))

            st.markdown("**Schedule seeds** — these drive every planned gate date")
            c21, c22, c23 = st.columns(3)
            e_g0 = c21.date_input("Gate Zero date", _d(rec["gate_zero_date"]) or NOW)
            e_ppap = c22.date_input(
                "PPAP date (Gate 3)", _d(rec["ppap_target_date"]) or NOW
            )
            e_sop = c23.date_input("SOP date (Gate 4)", _d(rec["sop_target_date"]) or NOW)

            st.markdown("**Status and outcome**")
            c24, c25, c26 = st.columns(3)
            lt_opts = ["Full", "Simple", "Prototype"]
            e_lt = c24.selectbox(
                "Launch type", lt_opts,
                index=lt_opts.index(rec["launch_type"])
                if rec["launch_type"] in lt_opts else 0,
            )
            status_opts = ["Green", "Yellow", "Red"]
            e_status = c25.selectbox(
                "Project status", status_opts,
                index=status_opts.index(rec["project_status"])
                if rec["project_status"] in status_opts else 0,
            )
            e_prr = c26.number_input("PRR count", 0, 200, int(rec["prr_count"]))
            e_notes = st.text_area("Notes", str(rec["notes"] or ""), height=68)

            save = st.form_submit_button("Save project fields")

        if save:
            try:
                changes = store.update_project(
                    role, pick,
                    {
                        "customer_part_number": e_part.strip(),
                        "description": e_desc.strip(),
                        "project_name": f"{e_part.strip()} — {e_desc.strip()}".strip(" —"),
                        "job_number": e_job.strip(),
                        "plant": e_plant, "div": e_div, "program_manager": e_pm,
                        "qmsi_number": e_qmsi.strip(),
                        "qmsi_revision": e_qmsi_rev.strip(),
                        "opportunity_number": e_opp.strip(),
                        "customer": e_cust.strip(), "sales_person": e_sales.strip(),
                        "rpn": int(e_rpn), "launch_risk": e_risk,
                        "launch_process": e_process.strip(),
                        "support_required": e_support.strip(),
                        "peak_annual_sales": float(e_sales_amt),
                        "qmsi_capex": float(e_capex), "cer_amount": float(e_cer_amt),
                        "cer_status": e_cer_status.strip(),
                        "cer_number": e_cer_no.strip(),
                        "gate_zero_date": e_g0, "ppap_target_date": e_ppap,
                        "sop_target_date": e_sop,
                        "launch_type": e_lt, "project_status": e_status,
                        "prr_count": int(e_prr), "notes": e_notes.strip(),
                    },
                )
            except Exception as exc:
                st.error(f"Could not save: {exc}")
            else:
                if changes:
                    st.cache_data.clear()
                    st.success("Saved: " + "; ".join(changes))
                    st.rerun()
                else:
                    st.info("Nothing changed.")

        # -- gate dates -----------------------------------------------------
        # Plain date fields, one row per gate. No grid: the spreadsheet-style
        # editor was unreadable and its edits did not register until submit.
        # The project picker is at the top of the tab and scrolls out of
        # sight, so every editable block restates which project it is on.
        st.markdown(f"### Gate dates — {rec['project_name']}")
        st.caption(
            f"`{pick}` · {rec['plant']} · PM {rec['program_manager']} · "
            f"Job {rec['job_number'] or '—'} · "
            f"{rec['launch_type']} launch · {rec['project_phase']}"
        )
        st.caption(
            "Three dates per gate, exactly like the tracker sheet. "
            "**Plan** is auto-calculated from the Gate Zero, PPAP and SOP "
            "dates above. **Adjusted** is a slip. **Actual** is when it "
            "actually happened. On-time uses Adjusted when set, otherwise Plan."
        )

        pick_gates = (
            gates_all[gates_all["project_id"] == pick]
            .sort_values("gate_no")
            .reset_index(drop=True)
        )

        with st.form(f"gate_dates_{pick}"):
            h = st.columns([2.4, 1.5, 1.5, 1.5, 1.1])
            h[0].caption("Gate")
            h[1].caption("Plan")
            h[2].caption("Adjusted")
            h[3].caption("Actual")
            h[4].caption("Clear")

            entries = []
            for gr in pick_gates.itertuples():
                c = st.columns([2.4, 1.5, 1.5, 1.5, 1.1])
                c[0].markdown(
                    f"**{gr.gate_code}** &nbsp; {gr.gate_name}",
                    unsafe_allow_html=True,
                )
                plan = c[1].date_input(
                    f"Plan {gr.gate_code}", value=_d(gr.plan_date),
                    key=f"pl_{pick}_{gr.gate_no}", label_visibility="collapsed",
                )
                adjusted = c[2].date_input(
                    f"Adjusted {gr.gate_code}", value=_d(gr.adjusted_date),
                    key=f"ad_{pick}_{gr.gate_no}", label_visibility="collapsed",
                )
                actual = c[3].date_input(
                    f"Actual {gr.gate_code}", value=_d(gr.actual_date),
                    key=f"ac_{pick}_{gr.gate_no}", label_visibility="collapsed",
                )
                clear_adj = c[4].checkbox(
                    "adj", key=f"ca_{pick}_{gr.gate_no}",
                    help="Clear the adjusted date on save.",
                )
                clear_act = c[4].checkbox(
                    "act", key=f"cc_{pick}_{gr.gate_no}",
                    help="Clear the actual date on save — reopens the gate.",
                )
                entries.append(
                    {
                        "gate_no": gr.gate_no,
                        "plan_date": plan,
                        "adjusted_date": None if clear_adj else adjusted,
                        "actual_date": None if clear_act else actual,
                    }
                )

            save_gates = st.form_submit_button(f"Save gate dates for {pick}")

        if save_gates:
            try:
                gate_changes = store.save_gate_dates(
                    role, pick, pd.DataFrame(entries)
                )
            except store.ValidationError as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Could not save gates: {exc}")
            else:
                if gate_changes:
                    st.cache_data.clear()
                    st.success("Saved: " + "; ".join(gate_changes))
                    st.rerun()
                else:
                    st.info("No gate changes to save.")

        if st.button(
            "Recalculate plan dates from Gate Zero / PPAP / SOP", key=f"rp_{pick}"
        ):
            try:
                replanned = store.replan_gates(role, pick)
            except Exception as exc:
                st.error(f"Could not replan: {exc}")
            else:
                if replanned:
                    st.cache_data.clear()
                    st.success("Replanned: " + "; ".join(replanned))
                    st.rerun()
                else:
                    st.info("Plan dates already match the schedule seeds.")

        with st.expander(f"Advanced — add or remove gates on {pick}"):
            st.caption(
                "Only needed when a project does not follow the standard "
                "route. Everything else is on the form above."
            )
            adv = pick_gates[
                ["gate_no", "gate_code", "gate_name", "plan_date"]
            ].copy()
            adv_edited = st.data_editor(
                adv, width="stretch", hide_index=True, num_rows="dynamic",
                column_config={
                    "gate_no": st.column_config.NumberColumn("Order", width="small"),
                    "gate_code": st.column_config.TextColumn(
                        "Code", width="small", max_chars=2,
                        help="Label inside the timeline dot.",
                    ),
                    "gate_name": st.column_config.TextColumn("Name"),
                    "plan_date": st.column_config.DateColumn("Plan", width="small"),
                },
                key=f"adv_{pick}",
            )
            if st.button("Save gate structure", key=f"sa_{pick}"):
                merged = adv_edited.merge(
                    pick_gates[
                        ["gate_no", "adjusted_date", "actual_date", "qa_lab_hours"]
                    ],
                    on="gate_no", how="left",
                )
                merged["qa_lab_hours"] = merged["qa_lab_hours"].fillna(0.0)
                try:
                    adv_changes = store.replace_gates(role, pick, merged)
                except store.ValidationError as exc:
                    st.error(str(exc))
                except Exception as exc:
                    st.error(f"Could not save: {exc}")
                else:
                    if adv_changes:
                        st.cache_data.clear()
                        st.success("Saved: " + "; ".join(adv_changes))
                        st.rerun()
                    else:
                        st.info("No structural changes to save.")

    # -- add gate zero --------------------------------------------------
    with tab_gate0:
        st.caption(
            "Mirrors the Gate Zero form. Gate dates are calculated on save: "
            "Gate 1 at one third and Gate 2 at two thirds of the days between "
            "kickoff and PPAP, Gate 3 = PPAP, Gate 4 = SOP, review at SOP + 6 "
            "months."
        )
        with st.form("gate_zero"):
            c1, c2, c3 = st.columns(3)
            n_part = c1.text_input("Customer part number")
            n_desc = c2.text_input("Description")
            n_job = c3.text_input("Job number")

            c4, c5, c6 = st.columns(3)
            n_plant = c4.selectbox("Plant", plant_opts, key="g0_plant")
            n_div = c5.selectbox("Div", ["MS", "PS"], key="g0_div")
            n_lt = c6.selectbox("Launch type", ["Full", "Simple"], key="g0_lt")

            c7, c8, c9 = st.columns(3)
            n_pm = c7.selectbox("Program manager", pm_opts, key="g0_pm")
            n_cust = c8.text_input("Customer", key="g0_cust")
            n_sales = c9.text_input("Sales person", key="g0_sales")

            c10, c11, c12 = st.columns(3)
            n_qmsi = c10.text_input("QMSI #", key="g0_qmsi")
            n_qmsi_rev = c11.text_input("QMSI revision", key="g0_qmsirev")
            n_opp = c12.text_input("Opportunity #", key="g0_opp")

            c13, c14, c15 = st.columns(3)
            n_g0 = c13.date_input("Gate Zero date", NOW, key="g0_date")
            n_ppap = c14.date_input(
                "PPAP date (Gate 3)", NOW + timedelta(days=180), key="g0_ppap"
            )
            n_sop = c15.date_input(
                "SOP date (Gate 4)", NOW + timedelta(days=210), key="g0_sop"
            )

            c16, c17, c18 = st.columns(3)
            n_rpn = c16.number_input("RPN", 0, 1000, 0, key="g0_rpn")
            n_risk = c17.selectbox("Launch risk", ["Low", "Medium", "High"], key="g0_risk")
            n_peak = c18.number_input(
                "Peak annual sales ($)", 0.0, 1e9, 0.0, step=10000.0, key="g0_peak"
            )

            c19, c20 = st.columns(2)
            n_process = c19.text_input("Launch process", key="g0_proc")
            n_support = c20.text_input("Support required", key="g0_sup")
            n_notes = st.text_area("Notes", height=68, key="g0_notes")

            go_ = st.form_submit_button("Add Gate Zero")

        if go_:
            if not n_part.strip() and not n_desc.strip():
                st.error("A customer part number or description is required.")
            else:
                try:
                    pid = store.create_project(
                        role=role,
                        fields={
                            "project_type": "Launch", "launch_type": n_lt,
                            "customer_part_number": n_part.strip(),
                            "description": n_desc.strip(),
                            "job_number": n_job.strip(), "plant": n_plant,
                            "div": n_div, "program_manager": n_pm,
                            "customer": n_cust.strip(),
                            "sales_person": n_sales.strip(),
                            "qmsi_number": n_qmsi.strip(),
                            "qmsi_revision": n_qmsi_rev.strip(),
                            "opportunity_number": n_opp.strip(),
                            "rpn": int(n_rpn), "launch_risk": n_risk,
                            "peak_annual_sales": float(n_peak),
                            "launch_process": n_process.strip(),
                            "support_required": n_support.strip(),
                            "gate_zero_date": n_g0, "ppap_target_date": n_ppap,
                            "sop_target_date": n_sop, "notes": n_notes.strip(),
                        },
                    )
                except store.ValidationError as exc:
                    st.error(str(exc))
                else:
                    st.cache_data.clear()
                    st.success(f"Created {pid}.")
                    st.rerun()

    # -- add prototype --------------------------------------------------
    with tab_proto:
        st.caption(
            "Prototypes are tracked because they consume the same QA lab, "
            "engineering and machine time as launches. The prototype gate "
            "route is a placeholder until a real one is agreed."
        )
        with st.form("prototype"):
            c1, c2, c3 = st.columns(3)
            p_part = c1.text_input("Part number", key="p_part")
            p_desc = c2.text_input("Description", key="p_desc")
            p_job = c3.text_input("Job number", key="p_job")

            c4, c5, c6 = st.columns(3)
            p_plant = c4.selectbox("Plant", plant_opts, key="p_plant")
            p_pm = c5.selectbox("Program manager", pm_opts, key="p_pm")
            p_cust = c6.text_input("Customer", key="p_cust")

            c7, c8 = st.columns(2)
            p_start = c7.date_input("Kickoff date", NOW, key="p_start")
            p_end = c8.date_input(
                "Target completion", NOW + timedelta(days=60), key="p_end"
            )
            p_notes = st.text_area("Notes", height=68, key="p_notes")
            pgo = st.form_submit_button("Add Prototype")

        if pgo:
            if not p_part.strip() and not p_desc.strip():
                st.error("A part number or description is required.")
            elif p_start > p_end:
                st.error("Kickoff cannot be after target completion.")
            else:
                try:
                    pid = store.create_project(
                        role=role,
                        fields={
                            "project_type": "Prototype",
                            "launch_type": "Prototype",
                            "customer_part_number": p_part.strip(),
                            "description": p_desc.strip(),
                            "job_number": p_job.strip(), "plant": p_plant,
                            "program_manager": p_pm, "customer": p_cust.strip(),
                            "gate_zero_date": p_start,
                            "ppap_target_date": p_end,
                            "sop_target_date": p_end,
                            "notes": p_notes.strip(),
                        },
                    )
                except store.ValidationError as exc:
                    st.error(str(exc))
                else:
                    st.cache_data.clear()
                    st.success(f"Created {pid}.")
                    st.rerun()

    # -- import the real tracker workbook --------------------------------
    with tab_import:
        st.caption(
            "Reads the **Project Launch Tracker** sheet and joins the "
            "**Gate Zero Summary** sheet on customer part number. This "
            "**replaces** everything currently loaded."
        )
        st.warning(
            "Only do this on a local or internal deployment. The workbook "
            "carries live part numbers and customer names, which should not "
            "be uploaded to a public host.",
            icon="🔒",
        )

        up = st.file_uploader(
            "Tracker workbook (.xlsm or .xlsx)", type=["xlsm", "xlsx"],
            key="tracker_upload",
        )
        if up is not None:
            try:
                imported_p, imported_g, import_warnings = tracker_import.parse(up)
            except tracker_import.ImportError_ as exc:
                st.error(str(exc))
            except Exception as exc:
                st.error(f"Could not read that workbook: {exc}")
            else:
                st.success(
                    f"Parsed **{len(imported_p)} projects** and "
                    f"**{len(imported_g)} gates**."
                )
                m1, m2, m3 = st.columns(3)
                m1.metric("Projects", len(imported_p))
                m2.metric("Gates", len(imported_g))
                m3.metric("Warnings", len(import_warnings))

                st.dataframe(
                    imported_p[
                        ["project_id", "project_name", "plant", "launch_type",
                         "program_manager", "project_phase", "project_status",
                         "gate_zero_date", "ppap_target_date", "sop_target_date"]
                    ].head(30),
                    width="stretch", hide_index=True,
                )

                if import_warnings:
                    with st.expander(f"{len(import_warnings)} warnings"):
                        for wmsg in import_warnings:
                            st.write("•", wmsg)

                st.caption(
                    "Nothing has been written yet. Confirm below to replace "
                    "the loaded data."
                )
                if st.button("Replace loaded data with this import"):
                    tracker_import.write(imported_p, imported_g)
                    store.append_audit(
                        [
                            {
                                "timestamp": pd.Timestamp.now().isoformat(
                                    timespec="seconds"
                                ),
                                "role": role, "action": "import",
                                "project_id": "*", "field": "workbook",
                                "old_value": "", "new_value": up.name,
                            }
                        ]
                    )
                    st.cache_data.clear()
                    st.success("Imported. Reloading.")
                    st.rerun()

    # -- audit log ------------------------------------------------------
    audit = store.read_audit()
    with st.expander(f"Audit log ({len(audit)} entries)"):
        if audit.empty:
            st.caption("No changes recorded yet.")
        else:
            st.dataframe(audit.iloc[::-1].head(200), width="stretch", hide_index=True)
            st.download_button(
                "Download audit log", audit.to_csv(index=False).encode(),
                file_name="audit_log.csv", mime="text/csv",
            )
        st.caption(
            "`baseline` marks a plan date changed by hand, `replan` an "
            "auto-recalculation, `seed` a change to Gate Zero / PPAP / SOP. "
            "The log records the role, not the person — these are shared role "
            "passwords, so named logins remain a reason to move internal."
        )

    st.warning(
        "**Where this saves.** Changes write to the tracker files on the "
        "machine running the app — durable locally or on an internal server. "
        "On Streamlit Community Cloud the container is rebuilt on every deploy, "
        "so edits made on the hosted demo will be lost.",
        icon="⚠️",
    )

with st.expander("What this reflects, and what it still needs"):
    st.markdown(
        """
**From the 19 Aug review**

- Real dates throughout. Manufacturing weeks are gone.
- Gate 3 is PPAP and Gate 4 is SOP, matching the tracker.
- Simple launches run **0 → SL → 4**, no gates 1–3.
- Gate 1 and Gate 2 plan dates are calculated at one third and two thirds of
  the days between kickoff and PPAP, with manual override and a recalculate
  button.
- Plan / Adjusted / Actual on every gate. On-time uses Adjusted where present,
  otherwise Plan.
- 6 month post-SOP review as a diamond on a dashed tail.
- Launch type `n/a` is now `Prototype`, and the launch type filter disables
  itself when launches are not selected — that was the filter bug.
- QMSI revision captured. Gate Zero form fields carried through: div, sales
  person, customer part number, description, opportunity #, RPN, CapEx and
  CER, peak annual sales, launch process, support required, launch risk.
- PRRs within 12 months of SOP as a headline metric.
- Plants are Kentwood, Marshall, Wellington and North Attleboro.
- QA lab view hidden behind a sidebar toggle.

**Still open**

- The prototype gate route is invented — 0, S, R. It needs a real one.
- The PRR metric is a count. Review suggested a rate or percentage; the
  denominator has not been decided.
- QA lab hours per gate are guesses.
- Pulling Gate Zero rows straight from the form, and PRR counts from Galaxy,
  are both still manual.
- All data here is synthetic.
"""
    )
