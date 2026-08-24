# Launch Tracker Dashboard — handoff

Last updated: 20 Aug 2026 · Author: Nathan Van Wieren

This document is for picking the project back up on a different machine, or
for handing it to someone else. It covers how to run it, how it's built, the
decisions that are load-bearing, and what's unresolved.

---

## 1. What this is

A Streamlit dashboard replacing the reporting layer of the **Gate Zero /
Project Launch Tracker** Excel workbook used by Kentwood and Marshall for
monthly launch reviews.

It does **not** replace the Excel file as the source of truth — not yet. It
reads a copy of it, visualises launch gate status, and allows editing. The
Excel workbook has become slow and fragile (heavy conditional formatting and
cross-sheet references) and freezes during meetings, which is what started
this.

Two pages:

| Page | State |
|---|---|
| **Launch Portfolio** | The real work. Gate timeline, status, scorecard, data entry, workbook import |
| **Machine Capacity (future state)** | A separate concept on entirely invented data. Not connected to the tracker. Kept because Ryan liked it as a direction |

**Everything currently bundled is synthetic.** No live part numbers or
customer names are committed to the repo.

---

## 2. Where things stand

Working and verified:

- **SQLite storage** with real transactions, foreign keys and backups

- Real-date gate model matching the tracker sheet
- Auto-calculated plan dates (verified to reproduce the sheet exactly)
- Gate timeline, gate status bars, scorecard, coming-due list, project detail
- Two-role login (viewer / editor)
- Full editing with an append-only audit log
- Importer for the real workbook
- Deployed on Streamlit Community Cloud from a private GitHub repo

Not done:

- Internal hosting (blocked on Mike Chambers)
- Automated ingest from Ryan's Gate Zero form
- PRR counts from Galaxy
- Named user accounts (currently shared role passwords)
- Any real data in the deployed instance

---

## 3. Getting it running

```powershell
git clone https://github.com/nathanvanwieren239/capacity-dashboard.git
cd capacity-dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` (gitignored, so it will not come down with
the clone):

```toml
APP_PASSWORD_VIEWER = "viewer"
APP_PASSWORD_EDITOR = "editor"
```

```powershell
streamlit run app.py
```

Opens on `localhost:8501`. Demo data regenerates automatically if `data/` is
empty. Sign in as `editor` to see the entry and edit forms.

**Deployed instance:** Streamlit Community Cloud, deployed from `main` of the
private repo. Pushing to `main` redeploys. Secrets are set separately in the
app's Settings → Secrets panel — they do **not** come from the repo. If the
app serves stale code after a push, use Manage app → ⋮ → Reboot.

---

## 4. Architecture

Deliberately layered so the Streamlit code stays thin and the logic stays
testable.

```
app.py                  entry: page config, auth, logo, navigation
config.py               plants, colors, today()
auth.py                 two-role password gate

views/launch_page.py    Launch Portfolio UI          (largest file, ~900 lines)
views/capacity_page.py  Machine Capacity UI

gate_schedule.py        gate routes + plan-date arithmetic   <- start here
launch_model.py         all launch/gate math, Streamlit-free
launch_charts.py        Plotly figures, renderable headlessly
launch_data.py          synthetic data generator + column contract
store.py                the ONLY module that writes data
db.py                   SQLite connections and transactions
schema.sql              table definitions
migrate_to_sqlite.py    one-time CSV -> database conversion
safe_io.py              backups (its lock/atomic helpers are now unused)
tracker_import.py       reads the real Excel workbook

capacity_model.py       future-state capacity page
synthetic_data.py       future-state capacity data
preview.py              renders charts to static HTML without Streamlit
```

Two rules worth preserving:

1. **`store.py` is the only writer.** This was proven out by the move from
   CSV files to SQLite: `store.py` and `db.py` changed, and not one chart,
   metric, filter or page did. If the source of truth ever moves to
   SharePoint, the same holds.
2. **The model and chart layers never import Streamlit.** That's what makes
   them testable and what lets `preview.py` render charts headlessly.

### Testing

There is no test suite, but Streamlit's own harness works well and was used
throughout:

```python
from streamlit.testing.v1 import AppTest
at = AppTest.from_file("app.py", default_timeout=400).run()
at.text_input[0].set_value("editor"); at.button[0].click().run()
print(len(at.exception), len(at.get("plotly_chart")))
```

Note: `st.data_editor` is **not** introspectable by AppTest. Anything built
on it has to be clicked by hand.

---

## 5. The domain model — the part that isn't obvious

### Gate routes

| Route | Gates |
|---|---|
| Full launch | `0` Project Initiation → `1` → `2` → `3` PPAP → `4` SOP → `6M` |
| Simple launch | `0` → `SL` → `4` → `6M` (skips 1–3) |
| Prototype | `0` → `S` → `R` — **invented placeholder** |

**Gate 3 is PPAP. Gate 4 is SOP.** Confirmed against the workbook: the Gate 3
columns and the PPAP columns hold identical dates, likewise Gate 4 and SOP.
Gate Zero date and Project Initiation date are also the same event.

A simple launch is used for part families: one part takes a full launch, the
rest follow as simple launches on the same timeline. Its SL date equals the
PPAP date. Gate 4 sign-off is still required.

### Plan dates are calculated

```
Gate 1 = kickoff + 1/3 × (PPAP − kickoff)
Gate 2 = kickoff + 2/3 × (PPAP − kickoff)
Gate 3 = PPAP      Gate 4 = SOP      6M = SOP + 6 months
```

Verified against the real sheet: kickoff 2024-12-17, PPAP 2025-04-04 (108
days) produces Gate 1 on 2025-01-22 and Gate 2 on 2025-02-27 — exactly what
the workbook contains.

### Three dates per gate

`plan_date` (auto) · `adjusted_date` (the slip) · `actual_date` (what happened)

**Due date falls back:** adjusted if present, otherwise plan.
**On-time** = actual ≤ due date.

Gate status is derived, not stored: complete → green, open and due in the
future → yellow, open and past due → red. A hand-typed status on the sheet
(`G`/`Y`/`N/A`) is honoured as an override when present.

Project status (R/Y/G) is assessed by the PM and is *separate* from gate
status. Project phase (In-Process / Complete / On Hold / Not Awarded Yet) is
separate again.

---

## 6. Decisions that are load-bearing

Don't reverse these without understanding why they're there.

**On-time is shown two ways.** Ryan specified on-time against the adjusted
date, falling back to plan. That's the headline metric. A second tile shows
the same gates measured against the *original* plan. The gap between them
(currently 91% vs 74% on demo data) is how much of the on-time record depends
on dates that were moved. Without the second number, a project can stay green
by moving its own target — which is the exact accountability concern that
motivated restricting edit access.

**Plan-date edits are tagged `baseline` in the audit log**, distinct from
ordinary edits, for the same reason.

**Prototypes are a launch type, not `n/a`.** Labelling them `n/a` read as a
bug in review. The launch-type filter also disables itself when launches
aren't selected, rather than silently emptying the page.

**The gate editor uses plain date fields, not a grid.** Two earlier attempts
used `st.data_editor` inside `st.form`. That combination is broken — edits
don't register until submit and dynamic rows don't work at all — and it was
unreadable besides. The current form is verbose but obvious.

**Every edit block restates which project it's on**, because the project
picker scrolls out of view.

**Data is synthetic and generated, not committed.** `data/*.csv` is
gitignored; the app regenerates on first run. This keeps live part numbers
out of a hosted repo.

---

## 7. Traps and known limitations

**Streamlit Community Cloud does not persist writes.** The container is
rebuilt on every deploy and can be recycled anytime, and `data/` is
gitignored. Edits made on the hosted demo are lost. This is why internal
hosting matters. There's a warning banner in the app.

**Never import the real workbook on the hosted instance.** It carries live
part numbers and customer names. Local or internal only. The app warns; the
enforcement is human.

**The sanitised workbook has broken formulas.** In `Simplified.xlsm`, 50 of
56 project rows have `#REF!` in columns A–G (plant, div, customer, part
number, description, RPN, Gate Zero date) because those columns are formula
driven and the sanitising broke the references. The importer recovers what
survived — job number, PM, gate dates, notes — labels the project by job
number, takes kickoff from the earliest gate date, and reports every guess.
A clean export would import far better.

**Shared role passwords, not named accounts.** The audit log records that
*an* editor changed a date, not which one. Real accountability needs named
logins, which is an argument for moving internal.

**`st.data_editor` can't be automated-tested.** The Advanced gate-structure
editor is the only remaining thing built on it.

**`today()` is `date.today()`.** Synthetic data is generated relative to it,
so the demo always looks current — but regenerating data on a different day
produces different dates.

---

## 8. Open questions

1. **Prototype gate route.** `0 → S → R` is invented. Ryan hasn't defined a
   real one.
2. **PRR calculation.** Currently a raw count within 12 months of SOP. Review
   suggested a rate or percentage; nobody has decided the denominator.
3. **Source of truth.** Entry in the dashboard, or entry in Excel with the
   dashboard reading it? Ryan wants one place. Options discussed: SharePoint
   Excel, Google Sheet, or a dedicated entry page here.
4. **Gate Zero ingest.** Ryan's upgraded form auto-populates a single
   sales-facing tab. Could it push rows here directly rather than being typed?
5. **Galaxy / PRR automation.** Mike Chambers built Galaxy and would be the
   one to set up a data trigger.
6. **Internal hosting.** Where does this live? Blocked on Chambers.

---

## 9. Next steps

Roughly in order:

1. Talk to **Mike Chambers** about a server spot. Work with him only —
   Ryan's guidance is that wider IT involvement could add months.
2. Get a **clean workbook export** (unbroken formulas) and re-run the import.
3. Settle the source-of-truth question with Ryan before building more entry
   features.
4. Define the prototype gate route.
5. Define the PRR metric properly.
6. Replace shared passwords with named accounts once hosted internally.

---

## 10. People and context

| Person | Role |
|---|---|
| **Ryan Butkus** | Product launch engineer. Primary stakeholder and reviewer |
| **Lothian** | Over both Marshall and Kentwood. Needs a cross-plant view. Key audience |
| **Zoe** | Enters Gate Zero data into the Excel tracker for both plants |
| **Mike Chambers** | IT. Built Galaxy, 25+ years. The contact for hosting and data triggers |
| **Craig** | Possible third editor alongside Ryan and Lothian |

Edit access is intended to be limited to Ryan, Lothian and possibly Craig, to
prevent date adjustments ahead of monthly reviews.

Kentwood and Marshall hold separate monthly review meetings. Ryan filters to
one plant per meeting; Lothian looks across both.

---

## 11. History

| Date | What happened |
|---|---|
| 12 Aug 2026 | Initial capacity dashboard skeleton, synthetic data |
| 12 Aug 2026 | Launch Portfolio page added after Ryan's messages about gate tracking |
| 14 Aug 2026 | Review with Ryan: numbered gate dots, simple-launch marker, two logins, entry forms, PRRs |
| 19 Aug 2026 | Review with Ryan: real dates, Gate 3 = PPAP, `0/SL/4`, 6-month review, auto-calculated gate dates, filter fixes |
| 20 Aug 2026 | Rebuilt gate editor as plain date fields; workbook importer; schema aligned to the real sheet |

Meeting transcripts and notes are the authority on intent — this document
summarises them but doesn't replace them.

---

## 12. Quick reference

```powershell
# run
streamlit run app.py

# regenerate synthetic data
python launch_data.py

# import a real workbook (local only)
python tracker_import.py "path\to\tracker.xlsm"

# static chart preview, no Streamlit
python preview.py

# deploy
git add -A ; git commit -m "..." ; git push
```

Repo: `https://github.com/nathanvanwieren239/capacity-dashboard` (private)
