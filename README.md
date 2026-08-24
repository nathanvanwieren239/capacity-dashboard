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

## Test

```bash
python run_tests.py           # 11 tests, ~20s, isolated from your real data
python run_tests.py --quick   # skips the three that boot the app
```

Covers gate arithmetic against the real sheet, concurrent editing, backup
verification, restore from total deletion, corruption detection, foreign keys
and both roles. Full detail in **[docs/TEST-PLAN.md](docs/TEST-PLAN.md)**.

## Deploy

```bash
export APP_PASSWORD_VIEWER='...'
export APP_PASSWORD_EDITOR='...'
docker compose up -d --build
```

Full instructions in **[DEPLOY.md](DEPLOY.md)** — configuration, storage,
backups, reverse proxy, and troubleshooting.

> **The one thing that matters:** everything the app writes lives in
> `/app/data`, which **must** be a mounted volume. Inside the container it is
> destroyed on every redeploy, silently. `docker-compose.yml` does this
> correctly already.

Passwords are read from the environment, or from `.streamlit/secrets.toml`
if one is present. `.dockerignore` excludes both `data/` and any secrets file,
so neither can be baked into an image.

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

Gate status is derived, never stored — four states in precedence order:

| State | Colour | Meaning |
|---|---|---|
| Complete | green | an actual date is recorded |
| Behind | red | open, and the due date has passed |
| Due soon | light blue | open, due within `DUE_SOON_DAYS` (default 14) |
| In progress | yellow | open, due further out |

Behind wins over due soon, so a gate that is already late stays red rather
than being softened to blue. `DUE_SOON_DAYS` lives in `config.py`.

Project status (R/Y/G) is assessed separately by the PM and shows as the
leading circle on each row.

## Editing data — and where it saves

Signed in as **editor**, the Launch Portfolio page has a Data entry section:

- **Edit existing** — project fields, the Gate Zero form fields, schedule
  seeds, and a **plain gate date form**: one row per gate with three date
  pickers (Plan / Adjusted / Actual) and clear checkboxes. An *Advanced*
  expander adds or removes gates, for anything off the standard route.
- **Add New Gate Zero** — creates a launch and calculates its whole schedule.
- **Add New Prototype** — creates a prototype.
- **Import tracker workbook** — reads the real Project Launch Tracker sheet.

### Importing the real tracker

```bash
python tracker_import.py "path/to/tracker.xlsm"
```

or use the *Import tracker workbook* tab as an editor. It reads the
**Project Launch Tracker** sheet and joins **Gate Zero Summary-NA&SA** on
customer part number for launch process and sales fields. Column mapping is
documented at the top of `tracker_import.py`.

The importer is deliberately tolerant: columns A–G are formula-driven, and in
a sanitised copy those formulas come back as `#REF!`. Rather than dropping
those rows it keeps whatever survived — job number, PM, gate dates, notes —
labels the project by job number, recovers the kickoff from the earliest gate
date, and reports exactly what it had to guess. Nothing is written until you
confirm.

🔒 Import only on a local or internal deployment. The workbook carries live
part numbers and customer names.

Changes write to `data/projects.csv` and `data/gates.csv` and appear
immediately. Every change is appended to `data/audit_log.csv` with a
timestamp, role, field, old and new value. Actions are tagged: `baseline` for
a hand-edited plan date, `replan` for an auto-recalculation, `seed` for a
change to the Gate Zero / PPAP / SOP dates.

### Storage

Data lives in **SQLite** — one file, `data/tracker.db`. No server, nothing
for IT to install; SQLite ships with Python.

Every mutating function in `store.py` runs inside a `BEGIN IMMEDIATE`
transaction:

- **Concurrent editors serialise.** Two people saving at once queue rather
  than one silently overwriting the other.
- **A crash rolls back.** There is no half-written state to recover from.
- **Targeted writes.** Changing one date updates one row instead of
  rewriting the whole dataset.
- **Foreign keys.** A gate cannot reference a project that does not exist,
  and deleting a project removes its gates.

Verified with 20 concurrent writers: all 20 changes landed and the audit
chain was intact end to end — each write's old value matching the previous
write's new value.

#### Backups

Two layers:

**Per-write snapshots** — `safe_io.backup()` snapshots before every write into
`data/backups/`, keeping the most recent 40, using SQLite's own backup API so
the copy is consistent even mid-transaction.

**Daily snapshots** — `daily_backup.py` writes a dated folder to
`data/backups/daily/` holding both `tracker.db` (exact restore) and CSVs of
every table (readable by anything, forever), plus a `manifest.json` of row
counts. Runs automatically on first use each day; also a CLI for a scheduler.

```bash
python daily_backup.py                 # today's snapshot, if not already taken
python daily_backup.py --list          # what exists
python daily_backup.py --restore data/backups/daily/2026-08-23
```

Configuration (environment variables):

| Variable | Default | Notes |
|---|---|---|
| `TRACKER_SNAPSHOT_HOURS` | `24` | Set to `1` for hourly. Recommended once this is the system of record |
| `TRACKER_BACKUP_DIR` | unset | Network path to mirror every snapshot to |
| `TRACKER_KEEP_SNAPSHOTS` | `60` | Recent snapshots retained |
| `TRACKER_KEEP_MONTHLY` | `24` | First-of-month snapshots retained |

Every snapshot records a SQLite `integrity_check` result in its manifest.
`--verify` walks all snapshots and confirms the CSVs parse, row counts match
the manifest, and the database copy is sound. Tested by deliberately
corrupting a backup and by deleting rows from a CSV — both caught.

```bash
python daily_backup.py --verify   # are the backups actually restorable?
python daily_backup.py --health   # is the arrangement working at all?
```

Backup health is surfaced in the app (editor → Export and backups): snapshot
age, verification result, and whether an off-machine copy exists. A silently
failing backup becomes a visible one.

Restore is available in the app (editor → Export and backups) and has been
**verified end to end**: the database and all working files were deleted, then
rebuilt from a snapshot's CSVs alone — projects, gates, every date and the
full audit history came back identical.

> ⚠️ Snapshots live beside the database. That covers a bad edit or import; it
> does **not** cover losing the machine. Set `TRACKER_BACKUP_DIR` to a network
> path and every snapshot is mirrored there, or get `data/` into the company's
> existing backup regime.

The data is not openable in Excel any more, so the editor view has an
**Export to CSV** expander that downloads projects, gates and the audit log.

#### Migrating from the old CSV store

```bash
python migrate_to_sqlite.py            # convert data/*.csv into data/tracker.db
python migrate_to_sqlite.py --verify   # confirm the database matches the CSVs
```

Verifies row counts and a checksum of the key fields before declaring
success, and leaves the CSVs untouched. A fresh install needs none of this —
the app builds the database on first run.

⚠️ **Persistence caveat.** Writes are durable on a machine you control — your
laptop or an internal server. They are **not** durable on Streamlit Community
Cloud: the container is rebuilt on every deploy and `data/*.csv` is
gitignored, so a fresh container regenerates synthetic data. Edits made on the
hosted demo will be lost.

If this gets containerised for the internal server, `data/` **must** be on a
mounted volume, not inside the container — otherwise nothing has changed.

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
| `store.py` | The only module that writes. Same signatures regardless of backend |
| `db.py` | SQLite connections, transactions, row-level writes |
| `schema.sql` | Three tables, foreign keys, indexes |
| `migrate_to_sqlite.py` | One-time CSV → database conversion, with verification |
| `safe_io.py` | Per-write backups. Its lock and atomic-write helpers are now unused by `store` |
| `daily_backup.py` | Daily dated snapshots in both formats, retention, and restore |
| `tracker_import.py` | Reads the real Gate Zero / Project Launch Tracker workbook |
| `preview.py` | Renders the launch charts to `preview/` as static HTML |
| `capacity_model.py`, `synthetic_data.py` | The future-state capacity page |

## Known placeholders

- The prototype gate route (`0 → S → R`) is invented.
- QA lab hours per gate are guesses. That view is hidden behind a sidebar
  toggle by default.
- The PRR metric is a raw count within 12 months of SOP. Review suggested a
  rate or percentage; the denominator hasn't been decided.
- All bundled data is invented. Real data arrives via the importer.
- The per-gate status typed on the sheet (G/Y/N/A) is honoured as an
  override; otherwise status is derived from the dates.

## Open questions

1. What is the real prototype gate route?
2. What is the right PRR calculation — count, rate per project, or per part?
3. Can Gate Zero rows be pushed straight from Ryan's form rather than typed?
4. Can PRR counts be pulled from Galaxy by part number?
5. Where does this get hosted internally?
