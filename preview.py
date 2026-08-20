"""
Render the Launch Portfolio charts to static files without booting Streamlit.

    python preview.py

Writes preview/launch_preview.html — interactive, open it in a browser.
Useful for a quick look, or for pasting a chart into a deck.
"""

from __future__ import annotations

from pathlib import Path

import launch_charts as lc
import launch_model as lm
from config import today

OUT_DIR = Path(__file__).parent / "preview"


def build():
    now = today()
    projects, gates_raw = lm.load_bundled()
    gates = lm.annotate_gates(gates_raw, now)
    progress = lm.project_progress(projects, gates)

    active = progress[progress["sop_actual_date"].isna()]
    active_gates = gates[gates["project_id"].isin(active["project_id"])]

    figs = {
        "timeline": lc.gate_timeline(active, active_gates, now),
        "status_bars": lc.gate_status_bars(active, active_gates),
    }
    return figs, lm.scorecard(progress, gates, now), now


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    figs, sc, now = build()

    for name, fig in figs.items():
        fig.write_html(OUT_DIR / f"{name}.html", include_plotlyjs="cdn")

    header = f"""<!doctype html><meta charset="utf-8">
<title>Launch Portfolio preview</title>
<style>
 body{{font-family:system-ui,Segoe UI,Arial;margin:28px;color:#1A1D21;max-width:1500px}}
 h1{{margin:0 0 4px}} .sub{{color:#5b6470;margin-bottom:22px}}
 .kpis{{display:flex;gap:28px;flex-wrap:wrap;margin-bottom:26px}}
 .kpi{{border:1px solid #E3E6EA;border-radius:10px;padding:12px 18px;min-width:180px}}
 .kpi b{{display:block;font-size:26px}} .kpi span{{color:#5b6470;font-size:13px}}
 h2{{margin:30px 0 2px;font-size:19px}} .cap{{color:#5b6470;font-size:14px;margin-bottom:6px}}
</style>
<h1>Launch Portfolio — preview</h1>
<div class="sub">{now:%d %b %Y} · synthetic data · static render of the live page
(no filters, no entry forms)</div>
<div class="kpis">
  <div class="kpi"><b>{sc['gate_on_time']:.0%}</b><span>Gate reviews on time<br>
    ({sc['gates_closed']} closed, vs adjusted then plan)</span></div>
  <div class="kpi"><b>{sc['gate_on_time_vs_plan']:.0%}</b><span>…against original plan<br>
    (gap = reliance on moved dates)</span></div>
  <div class="kpi"><b>{sc['launch_on_time']:.0%}</b><span>Launches on time<br>
    ({sc['launches_closed']} launched)</span></div>
  <div class="kpi"><b>{sc['prr_12mo']}</b><span>PRRs, 12 mo post-SOP<br>
    (across {sc['prr_projects']} projects)</span></div>
</div>
"""

    sections = [
        (
            "Gate timeline",
            "Each dot is a gate on its due date, numbered by gate. Green complete · "
            "yellow in progress · red behind. ◇ SIMPLE rows run 0 → SL → 4. The "
            "diamond on the dashed tail is the 6 month post-SOP review.",
            "timeline",
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
        body.append(
            figs[key].to_html(full_html=False, include_plotlyjs=(key == "timeline"))
        )

    out = OUT_DIR / "launch_preview.html"
    out.write_text(header + "\n".join(body), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
