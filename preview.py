"""
Render the Launch Portfolio charts to static files without booting Streamlit.

    python preview.py

Writes preview/launch_preview.html (interactive, open in a browser) and PNGs
alongside it. Useful for a quick look, or for pasting a chart into a deck.
PNG export needs `kaleido`; the HTML works without it.
"""

from __future__ import annotations

from pathlib import Path

import launch_charts as lc
import launch_model as lm
from config import CURRENT_WEEK, YEAR

OUT_DIR = Path(__file__).parent / "preview"
LAB_CAPACITY = 120.0


def build():
    projects, gates_raw = lm.load_bundled()
    gates = lm.annotate_gates(gates_raw, CURRENT_WEEK)

    active = projects[projects["sop_actual_week"].isna()]
    active_gates = gates[gates["project_id"].isin(active["project_id"])]

    progress = lm.project_progress(active, active_gates)
    gate_zero = (
        active_gates.sort_values("gate_no")
        .groupby("project_id")["due_week"].first().rename("gate_zero_week")
    )
    progress = progress.merge(gate_zero, on="project_id", how="left")

    weeks = list(range(CURRENT_WEEK, 53))
    qa = lm.qa_lab_load(active_gates, active, weeks)

    return {
        "timeline": lc.gate_timeline(progress, active_gates, weeks),
        "qa_lab": lc.qa_lab_chart(qa, weeks, LAB_CAPACITY),
        "status_bars": lc.gate_status_bars(progress, active_gates),
    }, lm.scorecard(projects, gates), qa


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    figs, sc, qa = build()

    qa_by_week = qa.groupby("week")["hours"].sum()
    peak_week = int(qa_by_week.idxmax())
    peak_hours = float(qa_by_week.max())

    for name, fig in figs.items():
        fig.write_html(OUT_DIR / f"{name}.html", include_plotlyjs="cdn")
        try:
            fig.write_image(OUT_DIR / f"{name}.png", scale=2, width=1500)
        except Exception as exc:  # kaleido missing or browser unavailable
            print(f"  (png skipped for {name}: {exc})")

    header = f"""<!doctype html><meta charset="utf-8">
<title>Launch Portfolio preview</title>
<style>
 body{{font-family:system-ui,Segoe UI,Arial;margin:28px;color:#1A1D21;
      max-width:1500px}}
 h1{{margin:0 0 4px}} .sub{{color:#5b6470;margin-bottom:22px}}
 .kpis{{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:26px}}
 .kpi{{border:1px solid #E3E6EA;border-radius:10px;padding:12px 18px;min-width:170px}}
 .kpi b{{display:block;font-size:26px}} .kpi span{{color:#5b6470;font-size:13px}}
 h2{{margin:30px 0 2px;font-size:19px}} .cap{{color:#5b6470;font-size:14px;margin-bottom:6px}}
 .warn{{background:#FFF4E5;border-left:4px solid #E8A33D;padding:10px 14px;
       border-radius:4px;margin:10px 0}}
</style>
<h1>🚀 Launch Portfolio — preview</h1>
<div class="sub">Week {CURRENT_WEEK} of {YEAR} · synthetic data · static render of the
live page (no filters, no entry forms)</div>
<div class="kpis">
  <div class="kpi"><b>{sc['gate_on_time']:.0%}</b><span>Gate reviews on time<br>
    ({sc['gates_closed']} closed, vs ORIGINAL date)</span></div>
  <div class="kpi"><b>{sc['launch_on_time']:.0%}</b><span>Launches on time<br>
    ({sc['launches_closed']} launched)</span></div>
  <div class="kpi"><b>{sc['prr_total']}</b><span>PRRs logged<br>
    (first 12 months after SOP)</span></div>
  <div class="kpi"><b>{sc['dates_moved']}</b><span>Dates moved<br>
    (gates with an adjusted date)</span></div>
</div>
"""

    sections = [
        (
            "Gate timeline",
            "Each dot is a gate at its due week, numbered by gate. Green complete · "
            "yellow in progress · red behind. ◇ SIMPLE rows skip gates 1–3 and start "
            "at PPAP (P); their spans are dotted. Leading circle is project status.",
            "timeline",
        ),
        (
            "Shared resource load — QA lab",
            "Hours booked to the week each gate falls. A part family submitting PPAP "
            "together lands as one spike.",
            "qa_lab",
        ),
        (
            "Gate status",
            "One segment per gate, numbered, colored by status.",
            "status_bars",
        ),
    ]

    body = []
    for title, caption, key in sections:
        body.append(f'<h2>{title}</h2><div class="cap">{caption}</div>')
        if key == "qa_lab":
            body.append(
                f'<div class="warn">QA lab over capacity in week {peak_week}: '
                f"{peak_hours:.0f} h against a {LAB_CAPACITY:.0f} h/week "
                "placeholder capacity.</div>"
            )
        body.append(
            figs[key].to_html(full_html=False, include_plotlyjs=(key == "timeline"))
        )

    out = OUT_DIR / "launch_preview.html"
    out.write_text(header + "\n".join(body), encoding="utf-8")
    print(f"wrote {out}")
    print(f"peak QA lab: week {peak_week} at {peak_hours:.0f} h")


if __name__ == "__main__":
    main()
