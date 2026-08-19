"""
Launch Portfolio page.

Load here is milestone EVENTS landing in the same week and pulling on a
shared support resource - the QA lab above all - not machine hours. That is
why prototypes sit in the same table as launches: they draw on the same lab.

Gate status is derived from dates (complete / in progress / behind), and is
deliberately separate from the project-level status the PM assesses.
"""

from __future__ import annotations

import pandas as pd
import streamlit as st

import auth
import launch_model as lm
import store
from launch_charts import gate_status_bars, gate_timeline, qa_lab_chart
from config import CURRENT_WEEK, SIMPLE_LAUNCH_TAG, YEAR


@st.cache_data
def _bundled():
    return lm.load_bundled()


# ---------------------------------------------------------------------------
# Data + controls
# ---------------------------------------------------------------------------
projects_all, gates_all = _bundled()

st.sidebar.divider()
st.sidebar.subheader("Portfolio view")

plants = st.sidebar.multiselect(
    "Plants", sorted(projects_all["plant"].unique()),
    default=sorted(projects_all["plant"].unique()),
    help="Lothian views both sites; each plant meeting filters to one.",
)
types = st.sidebar.multiselect("Project type", lm.PROJECT_TYPES, default=lm.PROJECT_TYPES)
launch_types = st.sidebar.multiselect(
    "Launch type", lm.LAUNCH_TYPES + ["n/a"], default=lm.LAUNCH_TYPES + ["n/a"],
    help="Simple launches skip gates 1-3 and start at PPAP.",
)
pms = st.sidebar.multiselect(
    "Program manager", sorted(projects_all["program_manager"].unique()),
    default=sorted(projects_all["program_manager"].unique()),
)
hide_launched = st.sidebar.toggle("Hide launched projects", value=True)
horizon = st.sidebar.slider("Look-ahead (weeks)", 2, 20, 8)
lab_capacity = st.sidebar.number_input(
    "QA lab capacity (h/week)", 20, 600, 120, 10,
    help="Placeholder. Needs the real number from the lab.",
)

if not (plants and types and pms and launch_types):
    st.warning("Select at least one option in each filter.")
    st.stop()

# Scope = everything matching the filters, launched or not. The scorecard
# measures history, so it must keep launched projects even when the timeline
# hides them.
scope = projects_all[
    projects_all["plant"].isin(plants)
    & projects_all["project_type"].isin(types)
    & projects_all["launch_type"].isin(launch_types)
    & projects_all["program_manager"].isin(pms)
]
projects = scope[scope["sop_actual_week"].isna()] if hide_launched else scope

if projects.empty:
    st.warning("No projects match those filters.")
    st.stop()

scope_gates = lm.annotate_gates(
    gates_all[gates_all["project_id"].isin(scope["project_id"])], CURRENT_WEEK
)

gates = lm.annotate_gates(
    gates_all[gates_all["project_id"].isin(projects["project_id"])], CURRENT_WEEK
)
progress = lm.project_progress(projects, gates)

# Gate 0 week drives the left edge of each timeline row.
gate_zero = (
    gates.sort_values("gate_no").groupby("project_id")["due_week"].first()
    .rename("gate_zero_week")
)
progress = progress.merge(gate_zero, on="project_id", how="left")

weeks = list(range(CURRENT_WEEK, 53))
qa_load = lm.qa_lab_load(gates, projects, weeks)
qa_by_week = qa_load.groupby("week", as_index=False)["hours"].sum()
due = lm.coming_due(gates, projects, CURRENT_WEEK, horizon)

# ---------------------------------------------------------------------------
# Header
# ---------------------------------------------------------------------------
st.title("🚀 Launch Portfolio")
st.caption(
    f"Week {CURRENT_WEEK} of {YEAR} · {len(projects)} projects · "
    f"{int((projects['launch_type'] == 'Simple').sum())} simple launches · "
    f"{int((projects['project_type'] == 'Prototype').sum())} prototypes · "
    "synthetic data"
)

peak = qa_by_week.loc[qa_by_week["hours"].idxmax()] if not qa_by_week.empty else None
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Gates due in next {horizon} wks", int((due["when"] >= 0).sum()))
k2.metric("Gates behind schedule", int(gates["is_behind"].sum()))
k3.metric(
    "Peak QA lab week",
    f"Wk {int(peak['week'])}" if peak is not None else "—",
    delta=f"{peak['hours']:.0f} h vs {lab_capacity} cap" if peak is not None else None,
    delta_color="inverse",
)
k4.metric("Projects at Red", int((progress["project_status"] == "Red").sum()))

st.divider()

# ---------------------------------------------------------------------------
# Timeline
# ---------------------------------------------------------------------------
st.subheader("Gate timeline")
st.caption(
    "Each dot is a gate at its due week, numbered by gate. "
    f"Green complete · yellow in progress · red behind. "
    f"{SIMPLE_LAUNCH_TAG} rows skip gates 1–3 and start at PPAP (**P**). "
    "Dotted spans are simple launches. The leading circle is project status."
)
st.plotly_chart(gate_timeline(progress, gates, weeks), width="stretch")

st.divider()

# ---------------------------------------------------------------------------
# QA lab load
# ---------------------------------------------------------------------------
st.subheader("Shared resource load — QA lab")
st.caption(
    "Hours booked to the week each gate falls. A part family submitting PPAP "
    "together lands as one spike."
)
st.plotly_chart(qa_lab_chart(qa_load, weeks, float(lab_capacity)), width="stretch")

over = qa_by_week[qa_by_week["hours"] > lab_capacity]["week"].tolist()
if over:
    st.warning(f"QA lab over capacity in week(s): {', '.join(str(w) for w in over)}.")

st.divider()

# ---------------------------------------------------------------------------
# Status bars + PM load
# ---------------------------------------------------------------------------
left, right = st.columns([3, 2])

with left:
    st.subheader("Gate status")
    st.caption("One segment per gate, numbered, colored by status.")
    st.plotly_chart(gate_status_bars(progress, gates), width="stretch")

with right:
    st.subheader("Scorecard")
    st.caption("Includes launched projects even when hidden above.")
    sc = lm.scorecard(scope, scope_gates)
    c1, c2 = st.columns(2)
    c1.metric(
        "Gate reviews on time",
        f"{sc['gate_on_time']:.0%}" if sc["gates_closed"] else "—",
        help=f"{sc['gates_closed']} closed gates, measured against the "
             "ORIGINAL committed date.",
    )
    c2.metric(
        "Launches on time",
        f"{sc['launch_on_time']:.0%}" if sc["launches_closed"] else "—",
        help=f"{sc['launches_closed']} launched projects.",
    )
    c3, c4 = st.columns(2)
    c3.metric("PRRs logged", sc["prr_total"], help="First 12 months after SOP.")
    c4.metric(
        "Dates moved", sc["dates_moved"],
        help="Gates with an adjusted date. On-time is measured against the "
             "original, so moving a date does not repair the metric.",
    )

    st.subheader("Program manager load")
    pm = lm.pm_workload(progress, CURRENT_WEEK, horizon).rename(
        columns={
            "program_manager": "PM", "active_projects": "Active",
            "launches": "Launches", "prototypes": "Protos",
            "closing_soon": "Closing", "red_projects": "Red",
        }
    )
    st.dataframe(pm, width="stretch", hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Coming due
# ---------------------------------------------------------------------------
st.subheader(f"Coming due — next {horizon} weeks (and anything behind)")
if due.empty:
    st.info("Nothing due in this window.")
else:
    t = due.copy()
    t["When"] = t.apply(
        lambda r: f"{int(r['weeks_late'])} wk behind"
        if r["is_behind"]
        else ("this week" if r["when"] == 0 else f"in {int(r['when'])} wk"),
        axis=1,
    )
    t["Moved"] = t["was_moved"].map({True: "yes", False: ""})
    t = t[
        ["project_id", "project_name", "launch_type", "plant", "program_manager",
         "job_number", "gate_code", "gate_name", "original_week", "due_week",
         "Moved", "When", "qa_lab_hours"]
    ].rename(
        columns={
            "project_id": "ID", "project_name": "Project", "launch_type": "Type",
            "plant": "Plant", "program_manager": "PM", "job_number": "Job #",
            "gate_code": "Gate", "gate_name": "Gate name",
            "original_week": "Orig wk", "due_week": "Due wk",
            "qa_lab_hours": "QA lab h",
        }
    )
    st.dataframe(t, width="stretch", hide_index=True)

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
    plant_options = sorted(projects_all["plant"].unique())
    pm_options = sorted(projects_all["program_manager"].unique())

    st.caption(
        "Changes are written to the tracker files and appear immediately. "
        "Every change is recorded in the audit log below."
    )

    tab_edit, tab_gate0, tab_proto = st.tabs(
        ["Edit existing", "Add New Gate Zero", "Add New Prototype"]
    )

    # -- edit existing ------------------------------------------------------
    with tab_edit:
        options = projects_all.sort_values("project_id")
        pick = st.selectbox(
            "Project",
            options["project_id"].tolist(),
            format_func=lambda i: (
                f"{i} — {options.loc[options['project_id'] == i, 'project_name'].iloc[0]}"
            ),
        )
        rec = options[options["project_id"] == pick].iloc[0]

        with st.form("edit_project"):
            c1, c2, c3 = st.columns(3)
            e_name = c1.text_input("Project name", rec["project_name"])
            e_job = c2.text_input("Job number", str(rec["job_number"]))
            e_plant = c3.selectbox(
                "Plant", plant_options, index=plant_options.index(rec["plant"])
            )
            c4, c5, c6 = st.columns(3)
            e_pm = c4.selectbox(
                "Program manager", pm_options, index=pm_options.index(rec["program_manager"])
            )
            lt_opts = lm.LAUNCH_TYPES + ["n/a"]
            e_lt = c5.selectbox(
                "Launch type", lt_opts,
                index=lt_opts.index(rec["launch_type"])
                if rec["launch_type"] in lt_opts else 0,
            )
            status_opts = ["Green", "Yellow", "Red"]
            e_status = c6.selectbox(
                "Project status", status_opts,
                index=status_opts.index(rec["project_status"])
                if rec["project_status"] in status_opts else 0,
            )
            c7, c8 = st.columns(2)
            e_sop = c7.number_input(
                "Actual SOP week (0 = not launched)", 0, 52,
                int(rec["sop_actual_week"]) if pd.notna(rec["sop_actual_week"]) else 0,
            )
            e_prr = c8.number_input("PRR count", 0, 50, int(rec["prr_count"]))
            e_comments = st.text_area("Comments", str(rec["comments"] or ""), height=68)

            save = st.form_submit_button("Save project fields")

        if save:
            try:
                changes = store.update_project(
                    role, pick,
                    {
                        "project_name": e_name.strip(),
                        "plant": e_plant,
                        "program_manager": e_pm,
                        "job_number": e_job.strip(),
                        "launch_type": e_lt,
                        "project_status": e_status,
                        "sop_actual_week": pd.NA if e_sop == 0 else int(e_sop),
                        "prr_count": int(e_prr),
                        "comments": e_comments.strip(),
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

        # -- gates ----------------------------------------------------------
        # Deliberately OUTSIDE the form above: st.data_editor cannot add or
        # delete rows inside a form, and its edits do not register until the
        # form is submitted. Its own save button keeps the two independent.
        st.markdown("**Gates**")
        st.caption(
            "Edit any cell. Use the bottom row to add a gate and the trash "
            "icon to remove one. Gate code is the label shown in the timeline "
            "dot, so keep it to one or two characters."
        )
        st.warning(
            "Changing **Original** rewrites the committed date the on-time "
            "metric is measured against — it does not record a slip, it erases "
            "one. Put slips in **Adjusted**. Original edits are tagged "
            "`baseline` in the audit log.",
            icon="⚠️",
        )

        # reset_index is required: with num_rows="dynamic" a non-range index
        # makes the editor ask the user to supply index values for new rows.
        gsub = (
            gates_all[gates_all["project_id"] == pick]
            .sort_values("gate_no")[store.GATE_EDIT_COLUMNS]
            .reset_index(drop=True)
            .copy()
        )
        for col in ("adjusted_week", "actual_week"):
            gsub[col] = gsub[col].astype("float")

        edited = st.data_editor(
            gsub,
            width="stretch",
            hide_index=True,
            num_rows="dynamic",
            column_config={
                "gate_no": st.column_config.NumberColumn(
                    "Order", min_value=0, max_value=99, step=1, width="small",
                    help="Sort order. Must be unique within the project.",
                ),
                "gate_code": st.column_config.TextColumn(
                    "Code", width="small", max_chars=2,
                    help="Shown inside the timeline dot, e.g. 0 1 2 3 P 4.",
                ),
                "gate_name": st.column_config.TextColumn("Name", width="medium"),
                "original_week": st.column_config.NumberColumn(
                    "Original", min_value=1, max_value=52, step=1, width="small",
                    help="The committed date. On-time is measured against this.",
                ),
                "adjusted_week": st.column_config.NumberColumn(
                    "Adjusted", min_value=1, max_value=52, step=1, width="small",
                    help="Revised date. Records a slip without hiding it.",
                ),
                "actual_week": st.column_config.NumberColumn(
                    "Actual", min_value=1, max_value=52, step=1, width="small",
                    help="Completion week. Blank means the gate is still open.",
                ),
                "qa_lab_hours": st.column_config.NumberColumn(
                    "QA lab h", min_value=0.0, step=1.0, format="%.1f",
                    width="small",
                ),
            },
            key=f"gates_{pick}",
        )

        if st.button("Save gate changes", key=f"save_gates_{pick}"):
            try:
                gate_changes = store.replace_gates(role, pick, edited)
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

    # -- add gate zero ------------------------------------------------------
    with tab_gate0:
        with st.form("gate_zero"):
            c1, c2, c3 = st.columns(3)
            name = c1.text_input("Project name")
            job = c2.text_input("Job number")
            plant = c3.selectbox("Plant", plant_options, key="g0_plant")
            c4, c5, c6 = st.columns(3)
            ltype = c4.selectbox("Launch type", lm.LAUNCH_TYPES)
            pm_sel = c5.selectbox("Program manager", pm_options, key="g0_pm")
            family = c6.text_input("Part family (optional)")
            c7, c8, c9 = st.columns(3)
            g0 = c7.number_input("Gate 0 week", 1, 52, CURRENT_WEEK)
            ppap = c8.number_input("PPAP week", 1, 52, min(CURRENT_WEEK + 12, 52))
            sop = c9.number_input("SOP week", 1, 52, min(CURRENT_WEEK + 16, 52))
            comments = st.text_area("Comments", height=68, key="g0_comments")
            go_ = st.form_submit_button("Add Gate Zero")

        if go_:
            if not name.strip():
                st.error("Project name is required.")
            elif not (g0 <= ppap <= sop):
                st.error("Weeks must run Gate 0 ≤ PPAP ≤ SOP.")
            else:
                pid = store.create_project(
                    role=role, project_name=name.strip(), project_type="Launch",
                    launch_type=ltype, plant=plant, program_manager=pm_sel,
                    job_number=job.strip(), family=family.strip(),
                    gate_zero_week=int(g0), ppap_week=int(ppap),
                    sop_week=int(sop), comments=comments.strip(),
                )
                st.cache_data.clear()
                st.success(f"Created {pid} — {name.strip()}.")
                st.rerun()

    # -- add prototype ------------------------------------------------------
    with tab_proto:
        with st.form("prototype"):
            c1, c2, c3 = st.columns(3)
            pname = c1.text_input("Prototype name")
            pjob = c2.text_input("Job number", key="p_job")
            pplant = c3.selectbox("Plant", plant_options, key="p_plant")
            c4, c5, c6 = st.columns(3)
            ppm = c4.selectbox("Program manager", pm_options, key="p_pm")
            pstart = c5.number_input("Kickoff week", 1, 52, CURRENT_WEEK, key="p_start")
            pend = c6.number_input(
                "Target completion week", 1, 52, min(CURRENT_WEEK + 8, 52), key="p_end"
            )
            pcomments = st.text_area("Comments", height=68, key="p_comments")
            pgo = st.form_submit_button("Add Prototype")

        if pgo:
            if not pname.strip():
                st.error("Prototype name is required.")
            elif pstart > pend:
                st.error("Kickoff week must not be after target completion.")
            else:
                pid = store.create_project(
                    role=role, project_name=pname.strip(), project_type="Prototype",
                    launch_type="n/a", plant=pplant, program_manager=ppm,
                    job_number=pjob.strip(), family="",
                    gate_zero_week=int(pstart), ppap_week=None,
                    sop_week=int(pend), comments=pcomments.strip(),
                )
                st.cache_data.clear()
                st.success(f"Created {pid} — {pname.strip()}.")
                st.rerun()

    # -- audit log ----------------------------------------------------------
    audit = store.read_audit()
    with st.expander(f"Audit log ({len(audit)} entries)"):
        if audit.empty:
            st.caption("No changes recorded yet.")
        else:
            st.dataframe(
                audit.iloc[::-1].head(200), width="stretch", hide_index=True
            )
            st.download_button(
                "Download audit log",
                audit.to_csv(index=False).encode(),
                file_name="audit_log.csv",
                mime="text/csv",
            )
        st.caption(
            "The log records the role that made each change, not the person — "
            "these are shared role passwords, not named accounts. Named logins "
            "are part of moving this behind the intranet."
        )

    st.warning(
        "**Where this saves.** Changes write to the tracker CSVs on the machine "
        "running the app. That is durable locally or on an internal server. On "
        "Streamlit Community Cloud the container is rebuilt on every deploy and "
        "can be recycled at any time, so edits made on the hosted demo will be "
        "lost. Only `store.py` needs to change once the source of truth is "
        "settled.",
        icon="⚠️",
    )

with st.expander("What this page assumes, and what it still needs"):
    st.markdown(
        """
**Reflects the 14 Aug review**

- Gate model is 0 → 1 → 2 → 3 → PPAP (**P**) → 4, with Gate 4 as SOP sign-off.
- Simple launches skip gates 1–3, start at PPAP, and still require Gate 4.
  Tagged `◇ SIMPLE` with a dotted span.
- Gate dots are numbered and colored complete / in progress / behind.
- Project status is assessed separately from gate status and shown as the
  leading circle.
- Plants are Kentwood and Marshall.
- Two logins: viewer and editor. Only editors see the entry forms.

**Deliberate modeling choice**

On-time is measured against the **original** committed date, not the
adjusted one. Measured against the adjusted date, any project could stay
green by moving its own target — which is exactly the accountability gap
that motivates restricting edit access.

**Still placeholder**

- All names, job numbers and customers are invented.
- Gate names are generic; the real gate titles should replace them.
- QA lab hours per gate are guesses, and all hours land in a single week.
  Real lab work spreads out.
- One lab capacity number covers both plants.
- PRR counts are entered by hand here. Pulling them from Galaxy by part
  number is the automation Mike Chambers would enable.
- Weeks are used throughout rather than real dates.

**Open**

- Real gate names and whether Gate 3 always means parts fed back.
- Does a simple launch ever need its own PPAP date distinct from the family's?
- Where the source of truth lives — SharePoint Excel, Google Sheet, or a
  dedicated entry page here.
"""
    )
