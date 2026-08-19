# Manufacturing Capacity Dashboard — skeleton

First-pass build for internal review. **All data is synthetic.** Plant names,
work centers, programs, staffing ratios and OEE are invented placeholders.

## Run

```bash
pip install -r requirements.txt
python synthetic_data.py     # regenerates data/capacity.csv and data/demand.csv
streamlit run app.py
```

## Editing data — and where it saves

Signed in as **editor**, the Launch Portfolio page has a Data entry section:

- **Edit existing** — change project fields and gate dates for any project
- **Add New Gate Zero** — creates a launch and its full gate set
- **Add New Prototype** — creates a prototype and its gate set

Changes write to `data/projects.csv` and `data/gates.csv` and appear
immediately. Every change is appended to `data/audit_log.csv` with a
timestamp, the role that made it, and the old and new values.

The gate grid is fully editable: change any cell, add a gate with the bottom
row, delete one with the trash icon. That covers promoting a simple launch to
a full one, renaming gates to match the real process, and adjusting QA lab
hours per gate.

> **`original_week` is editable but load-bearing.** It's the commitment the
> on-time metric is measured against, so changing it rewrites history rather
> than recording a slip. Slips belong in `adjusted_week`. Original edits are
> tagged `baseline` in the audit log so they stay distinguishable from
> ordinary changes.

Gate saves are validated: gate numbers must be unique, codes can't be blank,
weeks must be 1–52, QA hours can't be negative, and a project must keep at
least one gate. A rejected save changes nothing and writes no audit entries.

⚠️ **Persistence caveat.** These writes are durable when the app runs on a
machine you control — your laptop, or an internal server. They are **not**
durable on Streamlit Community Cloud: that container is rebuilt on every
deploy and can be recycled at any time, and `data/*.csv` is gitignored, so a
fresh container regenerates synthetic data. Edits made on the hosted demo
will be lost.

All file access is isolated in `store.py`. When the source of truth is
settled — SharePoint Excel, a Google Sheet, or an internal database — that
one module changes and nothing else has to.

## Gate model

    Gate 0 → Gate 1 → Gate 2 → Gate 3 → PPAP (P) → Gate 4 (SOP sign-off)

A **simple launch** skips gates 1–3 and starts at PPAP, but still requires
Gate 4. Used for part families where one part takes a full launch and the
rest follow. Tagged `◇ SIMPLE` with a dotted timeline span.

Gate status is *derived from dates*, never stored:

| State | Color | Meaning |
|---|---|---|
| Complete | green | actual date recorded |
| In progress | yellow | open, due week still ahead |
| Behind | red | open, due week has passed |

Project-level status (green/yellow/red) is assessed separately by the PM and
shown as the leading circle on each row.

**On-time is measured against the ORIGINAL committed date**, not the adjusted
one. Measured against the adjusted date, any project could stay green by
moving its own target — which is the accountability gap that motivates
restricting edit access.

## Password

Two dummy login types, read from Streamlit secrets. Never stored in this repo.

```toml
APP_PASSWORD_VIEWER = "..."   # read only
APP_PASSWORD_EDITOR = "..."   # also gets the entry forms
```

**Locally:** copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml`. That file is gitignored.

**On Community Cloud:** app menu → Settings → Secrets, paste both lines,
reboot.

If nothing is configured the app refuses to start rather than serving openly.
The older single `APP_PASSWORD` key still works and maps to viewer.

These are shared passwords per role, not per-user accounts — so they can tell
you that *an* editor changed a date, not *which* one. Real accountability
needs named logins, which is an argument for moving this behind the intranet
before it carries live data.

## Files

| File | Purpose |
|---|---|
| `app.py` | Entrypoint: page config, auth, logo, page navigation |
| `config.py` | Shared constants (year, current week, paths, colors) |
| `auth.py` | Shared-password gate, reads `APP_PASSWORD` from secrets |
| `views/capacity_page.py` | Machine Capacity page |
| `views/launch_page.py` | Launch Portfolio page |
| `capacity_model.py` | All capacity math — no Streamlit, so it can be tested or reused |
| `launch_model.py` | Launch/gate/shared-resource math — also Streamlit-free |
| `launch_charts.py` | Plotly figure builders, renderable outside Streamlit |
| `store.py` | The only module that writes data. Swap this to change source of truth |
| `preview.py` | Renders the launch charts to `preview/` as static HTML |
| `synthetic_data.py` | Capacity demo data + the authoritative column contracts |
| `launch_data.py` | Portfolio demo data + its column contracts |
| `data/` | Generated CSVs. Replace with real extracts, same columns |
| `assets/` | NN logo + favicon, picked up automatically. Sidebar size is `LOGO_WIDTH_PX` in `app.py` |

## Pages

**Machine Capacity** — machine hours vs. demand, by work center. Load is
measured in hours against three capacity tiers.

**Launch Portfolio** — launch and prototype gate status. Load here is
milestone *events* landing in the same week and pulling on a shared support
resource (the QA lab), not machine hours. Same load-vs-capacity shape,
different unit, which is why it's a separate page.

Prototypes sit in the same table as launches because they draw on the same
lab. That was an explicit ask — there's currently no tracking for them.

## The model

Three capacity tiers, plotted as lines on every chart:

| Tier | Meaning |
|---|---|
| **True Capacity** | Theoretical ceiling: every asset, every shift, at target availability |
| **Fully Staffed Capacity** | The same assets with every shift completely crewed |
| **Current Capacity** | What the group delivers today, at present staffing and realized rate |

Invariant: `true ≥ fully staffed ≥ current`. Utilization % is measured against
whichever tier you pick in the sidebar; **Current Capacity** is the default
because it's the only one grounded in evidence rather than assumption.

The gap between Current and Fully Staffed is the hiring/coverage argument.
The gap between Fully Staffed and True is the shift-pattern and capital
argument. Keeping them separate is the point.

Demand stacks in three categories:

- **Released** — firm customer releases (tapers to forecast past the horizon)
- **Launch** — awarded business ramping in
- **Quoted** — open RFQs, shown at full value, *not* a commitment

## What this is meant to show

Released demand alone fits comfortably. Turn on **Launch** and seven work
centers go over. That's the intended conversation: the constraint isn't
today's schedule, it's what the launch ramp does to it.

## Known placeholders

- Current week hard-coded to 33 (`CURRENT_WEEK` in `app.py`)
- Setup/changeover buried inside demand hours rather than modeled separately
- Quoted demand not probability-weighted
- "Pool plants" sums capacity across sites, which assumes work can actually
  move — tooling, PPAP and customer approval usually say otherwise
- No persistence yet; uploads are per-session only

## Open questions driving the next revision

1. Resource granularity — machine, cell, or department?
2. Constraint — spindles or operator coverage? Does the ratio vary by site?
3. Can programs realistically move between the three plants?
4. Primary use: quoting, launch/capital planning, or weekly execution?
