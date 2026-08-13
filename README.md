# Manufacturing Capacity Dashboard — skeleton

First-pass build for internal review. **All data is synthetic.** Plant names,
work centers, programs, staffing ratios and OEE are invented placeholders.

## Run

```bash
pip install -r requirements.txt
python synthetic_data.py     # regenerates data/capacity.csv and data/demand.csv
streamlit run app.py
```

## Password

The app is gated by a single shared password read from Streamlit secrets.
It is never stored in this repo.

**Locally:** copy `.streamlit/secrets.toml.example` to
`.streamlit/secrets.toml` and set a real value. That file is gitignored.

**On Community Cloud:** app menu → Settings → Secrets, paste
`APP_PASSWORD = "..."`, then reboot the app.

If no password is configured the app refuses to start rather than serving
openly. Note this is a shared password, not per-user accounts, and there is
no lockout on repeated attempts.

## Files

| File | Purpose |
|---|---|
| `app.py` | Streamlit UI only |
| `auth.py` | Shared-password gate, reads `APP_PASSWORD` from secrets |
| `capacity_model.py` | All capacity math — no Streamlit, so it can be tested or reused |
| `synthetic_data.py` | Demo data generator + the authoritative column contracts |
| `data/` | Generated CSVs. Replace with real extracts, same columns |
| `assets/` | NN logo + favicon, picked up automatically. Sidebar size is `LOGO_WIDTH_PX` in `app.py` |

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
