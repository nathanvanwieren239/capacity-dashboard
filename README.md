# NN Launch Tracker — development build

**All data is synthetic.** Part numbers, customers, people and dates are
invented. Nothing here is live plant data.

Two pages:

- **Launch Portfolio** — the working tool. Gate status, timeline, scorecard,
  data entry.
- **Machine Capacity (future state)** — a separate concept for machine-hour
  capacity, on entirely invented data. Not connected to the tracker.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Demo data regenerates automatically if `data/` is empty.

## Logins

Two dummy roles, read from Streamlit secrets. Never stored in this repo.

```toml
APP_PASSWORD_VIEWER = "..."   # read only
APP_PASSWORD_EDITOR = "..."   # also gets the entry and edit forms
```

**Locally:** copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` (gitignored).
**On Community Cloud:** app menu → Settings → Secrets.

The app refuses to start with nothing configured. These are shared passwords
per role, not named accounts — the audit log can say *an* editor changed a
date, not which one. Named logins remain a reason to move this internal.

## Gate model

Everything runs on **real dates**.

| Route | Gates |
|---|---|
| Full launch | `0` Project Initiation → `1` → `2` → `3` PPAP → `4` SOP → `6M` review |
| Simple launch | `0` → `SL` → `4` → `6M` (no gates 1–3) |
| Prototype | `0` → `S` → `R` — **placeholder**, no agreed route yet |

**Gate 3 is PPAP. Gate 4 is SOP.** The 6 month review is SOP + 6 months and
draws as a diamond on a dashed tail, so post-launch monitoring stays visible
without cluttering the launch.

### Planned dates are calculated

From the three Gate Zero dates — kickoff, PPAP and SOP:

```
Gate 1 = kickoff + 1/3 × (PPAP − kickoff)
Gate 2 = kickoff + 2/3 × (PPAP − kickoff)
Gate 3 = PPAP      Gate 4 = SOP      6M = SOP + 6 months
```

Auto-populated on creation, editable afterwards, with a **Recalculate plan
dates** button that re-derives them when the seed dates move. Lives in
`gate_schedule.py`.

### Three dates per gate

`Plan` (auto) · `Adjusted` (the slip) · `Actual` (what happened).

Due date falls back: **Adjusted if present, otherwise Plan.** On-time is
measured against that. The scorecard also shows on-time **against the
original plan** — the gap between the two is how much of the on-time record
depends on dates that were moved.

Gate status is derived, never stored: green complete, yellow in progress,
red behind. Project status (R/Y/G) is assessed separately by the PM and shows
as the leading circle on each row.

## Editing data — and where it saves

Signed in as **editor**, the Launch Portfolio page has a Data entry section:

- **Edit existing** — project fields, the Gate Zero form fields, schedule
  seeds, and a plain Plan/Adjusted/Actual date grid. An *Advanced* expander
  changes which gates a project has, for anything off the standard route.
- **Add New Gate Zero** — creates a launch and calculates its whole schedule.
- **Add New Prototype** — creates a prototype.

Changes write to `data/projects.csv` and `data/gates.csv` and appear
immediately. Every change is appended to `data/audit_log.csv` with a
timestamp, role, field, old and new value. Actions are tagged: `baseline` for
a hand-edited plan date, `replan` for an auto-recalculation, `seed` for a
change to the Gate Zero / PPAP / SOP dates.

⚠️ **Persistence caveat.** Writes are durable on a machine you control — your
laptop or an internal server. They are **not** durable on Streamlit Community
Cloud: the container is rebuilt on every deploy and `data/*.csv` is
gitignored, so a fresh container regenerates synthetic data. Edits made on the
hosted demo will be lost.

All file access is isolated in `store.py`. When the source of truth is settled
— the Gate Zero Summary sheet on SharePoint, or an internal database — that
one module changes and nothing else has to.

## Files

| File | Purpose |
|---|---|
| `app.py` | Entrypoint: page config, auth, logo, navigation |
| `config.py` | Shared constants — plants, colors, `today()` |
| `auth.py` | Two-role password gate |
| `views/launch_page.py` | Launch Portfolio page |
| `views/capacity_page.py` | Machine Capacity (future state) page |
| `gate_schedule.py` | Gate routes and the plan-date arithmetic |
| `launch_model.py` | Launch/gate math — Streamlit-free, testable |
| `launch_charts.py` | Plotly figures, renderable outside Streamlit |
| `launch_data.py` | Synthetic portfolio data + the column contract |
| `store.py` | The only module that writes. Swap to change source of truth |
| `preview.py` | Renders the launch charts to `preview/` as static HTML |
| `capacity_model.py`, `synthetic_data.py` | The future-state capacity page |

## Known placeholders

- The prototype gate route (`0 → S → R`) is invented.
- QA lab hours per gate are guesses. That view is hidden behind a sidebar
  toggle by default.
- The PRR metric is a raw count within 12 months of SOP. Review suggested a
  rate or percentage; the denominator hasn't been decided.
- All names, part numbers, customers and job numbers are fake.

## Open questions

1. What is the real prototype gate route?
2. What is the right PRR calculation — count, rate per project, or per part?
3. Can Gate Zero rows be pushed straight from Ryan's form rather than typed?
4. Can PRR counts be pulled from Galaxy by part number?
5. Where does this get hosted internally?
