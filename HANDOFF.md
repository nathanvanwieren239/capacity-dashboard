# Launch Tracker — handoff

**Last updated:** 24 August 2026 · **Author:** Nathan Van Wieren

For picking this up on another machine, or handing it to someone else
entirely. Covers how to run it, how it's built, the decisions that are
load-bearing, what's proven, and what isn't.

---

## 1. What this is

A Streamlit web application that replaces the **Gate Zero / Project Launch
Tracker** Excel workbook used for monthly launch reviews. The workbook had
grown slow enough to freeze during the meetings it supports.

Two decisions define the project:

- **It is the source of truth.** Not a mirror of the spreadsheet — the
  authoritative home of launch data. The spreadsheet gets retired.
- **It launches under the company president**, across the three Michigan
  plants, rather than as a departmental tool.

Both raise the bar. Neither changed the technology.

Two pages:

| Page | State |
|---|---|
| **Launch Portfolio** | The real tool. Timeline, gate status, scorecard, data entry, workbook import |
| **Machine Capacity (future state)** | A separate concept on invented data. Not connected. Kept because it was liked as a direction |

**All bundled data is synthetic.** No real part numbers or customer names are
in the repository or on any external host.

---

## 2. Where things stand

**Built and verified** — all of this is covered by `run_tests.py`:

- SQLite storage with real transactions, foreign keys, tested concurrency
- Real-date gate model matching the tracker sheet exactly
- Auto-calculated gate dates, verified to reproduce the sheet to the day
- Timeline, gate status bars, scorecard, coming-due list, project detail
- Two roles (viewer / editor) with an append-only audit log
- Full editing: project fields, gate dates, add/remove gates
- Importer for the real workbook, tolerant of damaged formulas
- Hourly backups with integrity verification and a **tested restore**

**Written but unverified** — container deployment files (Dockerfile, compose,
`DEPLOY.md`). The volume mount is correct on paper. The image has never been
built. Say so plainly to anyone you hand it to.

**Not done:**

- Internal hosting — the conversation with IT is the current blocker
- Docker image never actually built (no Docker on the dev machine)
- Automated ingest from the Gate Zero form
- PRR counts pulled from Galaxy
- Named accounts / SSO — currently shared passwords per role
- No real data loaded anywhere
- No parallel monthly cycle run yet

---

## 3. Running it

```powershell
git clone https://github.com/nathanvanwieren239/capacity-dashboard.git
cd capacity-dashboard
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `.streamlit/secrets.toml` — gitignored, so it won't come with the clone:

```toml
APP_PASSWORD_VIEWER = "viewer"
APP_PASSWORD_EDITOR = "editor"
```

```powershell
streamlit run app.py
```

Opens on `localhost:8501`. The database builds itself on first run. Sign in as
`editor` to see the entry and edit forms.

Passwords can also come from environment variables of the same names, which is
how the container is configured.

**Deployment:** see `DEPLOY.md`. **Testing:** see `docs/TEST-PLAN.md`.

---

## 4. Architecture

Layered so the Streamlit code stays thin and the logic stays testable.

```
app.py                  entry: page config, auth, logo, navigation, daily backup
config.py               plants, colours, DUE_SOON_DAYS, today()
auth.py                 two-role gate; reads secrets file or environment

views/launch_page.py    Launch Portfolio UI      (largest file, ~1000 lines)
views/capacity_page.py  Machine Capacity UI

gate_schedule.py        gate routes + plan-date arithmetic   <- start here
launch_model.py         all launch/gate maths, Streamlit-free
launch_charts.py        Plotly figures, renderable headlessly
launch_data.py          synthetic data generator + column contract

store.py                the ONLY module that writes data
db.py                   SQLite connections, transactions, row-level writes
schema.sql              three tables, foreign keys, indexes
migrate_to_sqlite.py    one-time CSV -> database conversion, with verification
safe_io.py              per-write backups (its lock/atomic helpers now unused)
daily_backup.py         interval snapshots, verification, health, restore
tracker_import.py       reads the real Excel workbook

run_tests.py            the whole test suite, isolated from real data
preview.py              renders charts to static HTML without Streamlit

Dockerfile              container image, non-root, healthcheck
docker-compose.yml      deployment definition — the volume mount matters
DEPLOY.md               deployment guide for whoever stands it up
```

Two rules worth preserving:

1. **`store.py` is the only writer.** Proven by the migration from CSV files
   to SQLite: `store.py` and `db.py` changed, and not one chart, metric,
   filter or page did. Keep it that way and the storage can move again —
   to SQL Server, to SharePoint — without a rewrite.
2. **The model and chart layers never import Streamlit.** That's what makes
   them testable and lets `preview.py` render charts headlessly.

---

## 5. The domain model

The part that isn't obvious, and the part most worth reading before changing
anything.

### Gate routes

| Route | Gates |
|---|---|
| Full launch | `0` Project Initiation → `1` → `2` → `3` PPAP → `4` SOP → `6M` |
| Simple launch | `0` → `SL` → `4` → `6M` (skips 1–3) |
| Prototype | `0` → `S` → `R` — **invented placeholder** |

**Gate 3 *is* PPAP. Gate 4 *is* SOP.** Confirmed against the real workbook,
where the Gate 3 columns and the PPAP columns hold identical dates, as do
Gate 4 and SOP. Gate Zero and Project Initiation are also the same date.

A simple launch is used for part families: one part takes a full launch, the
rest follow on the same timeline. Its SL date equals the PPAP date. Gate 4
sign-off is still required.

### Plan dates are calculated

```
Gate 1 = kickoff + 1/3 × (PPAP − kickoff)
Gate 2 = kickoff + 2/3 × (PPAP − kickoff)
Gate 3 = PPAP      Gate 4 = SOP      6M = SOP + 6 months
```

Verified against the sheet: kickoff 2024-12-17, PPAP 2025-04-04 produces
Gate 1 on 2025-01-22 and Gate 2 on 2025-02-27 — exactly what the workbook
contains. There's a test asserting this.

### Three dates per gate

`plan_date` (auto) · `adjusted_date` (the slip) · `actual_date` (what happened)

**Due date** = adjusted if present, otherwise plan.
**On-time** = actual ≤ due date.

### Four gate states, in precedence order

| State | Colour | Meaning |
|---|---|---|
| Complete | green | an actual date is recorded |
| Behind | red | open, due date passed |
| Due soon | light blue | open, due within `DUE_SOON_DAYS` (14) |
| In progress | yellow | open, due further out |

Behind beats due soon deliberately — a late gate stays red rather than being
softened to blue.

Gate status is derived from dates, not stored, except that a hand-typed
status on the imported sheet (`G`/`Y`/`N/A`) is honoured as an override.

Project status (R/Y/G) is assessed by the PM and is **separate** from gate
status. Project phase (In-Process / Complete / On Hold / Not Awarded Yet) is
separate again.

---

## 6. Decisions that are load-bearing

Don't reverse these without understanding why they exist.

**On-time is shown two ways.** The headline is on-time against the adjusted
date, falling back to plan — that's what was specified. A second tile shows
the same gates against the *original* commitment. They differ by about
seventeen points on demo data, and that gap is the share of the on-time record
that depends on dates having been moved. Without the second number, a project
stays green by moving its own target.

**Plan-date edits are tagged `baseline` in the audit log**, distinct from
ordinary edits, for the same reason.

**Prototypes are a launch type, not `n/a`.** Labelling them `n/a` read as a
bug. The launch-type filter disables itself when launches aren't selected
rather than silently emptying the page.

**The gate editor uses plain date fields, not a grid.** Two earlier attempts
used `st.data_editor` inside `st.form`. That combination is broken — edits
don't register until submit and dynamic rows don't work at all — and it was
unreadable besides.

**Every edit block restates which project it's on**, because the picker
scrolls out of view.

**Data is generated, not committed.** `data/` is gitignored; the app builds
its own on first run. Keeps real part numbers out of a hosted repository.

**`store.py` is the only writer.** See section 4.

---

## 7. What's proven, and how

```powershell
python run_tests.py
```

Eleven tests, about twenty seconds, running against an isolated copy so your
real data is never touched. Full detail in `docs/TEST-PLAN.md`.

The ones that matter most:

- **Gate dates match the tracker sheet**, to the day, on the real example.
- **Twenty concurrent writes** all land, with the audit chain intact end to
  end — each write's old value equalling the previous write's new value. That
  is what proves edits can't silently overwrite each other.
- **A database deleted outright**, along with its journals and all loose CSVs,
  rebuilt from a snapshot's CSVs alone — every project, gate, date and audit
  entry recovered identically, including a canary edit made beforehand.
- **Corrupted backups are detected** — verified by writing null bytes into a
  backup and by truncating a CSV.

What the suite does **not** cover: `st.data_editor` (not introspectable by the
test harness), the Docker build, and anything requiring two humans.

---

## 8. Known limitations and traps

**Streamlit Community Cloud does not persist writes.** The current public
deployment is a demo only. Edits made there are lost on redeploy.

**The container's data directory must be a mounted volume.** If it ends up
inside the image, every redeploy silently erases everything. `docker-compose.yml`
does this correctly; the trap is anyone deploying differently.

**Backups are on the same machine as the database.** That covers a bad edit,
not a lost server. Set `TRACKER_BACKUP_DIR` to a network path — this is the
main outstanding ask of IT.

**Shared role passwords, not named accounts.** The audit log records that *an*
editor changed something, not which one. The real risk isn't external access
(the network handles that) — it's a role change, where someone's account stays
active but they should no longer be editing.

**The Docker image has never been built.** No Docker on the dev machine.
Written carefully, but unverified.

**`requirements.txt` uses `>=` not `==`.** A rebuild months from now could
pull a breaking Streamlit release. Consider `pip freeze` before handing over.

**`today()` is `date.today()`.** Synthetic data is generated relative to it,
so the demo always looks current — but regenerating on a different day
produces different dates.

---

## 9. Open questions

None of these block go-live; all should be decided rather than defaulted.

1. **The prototype gate route** (`0 → S → R`) is invented. No real one exists.
2. **The PRR metric** is a raw count within 12 months of SOP. A rate was
   suggested, but the denominator — per project, per part, per million
   shipped — was never settled.
3. **Can the Gate Zero form push rows in** rather than being retyped?
4. **Can PRR counts come from Galaxy** by part number?
5. **SSO or named accounts** for the six editors?
6. **Records retention.** Automotive launch documentation carries obligations
   measured in years. Current backup retention is 24 months of monthlies,
   which may not be enough — a conversation with whoever owns quality records.

---

## 10. What has to be true before the spreadsheet is retired

1. Real data loaded, and its numbers agree with the spreadsheet's
2. A full monthly cycle run in parallel at every plant
3. A restore performed by somebody who is not the author
4. Backups existing somewhere other than the machine running the app
5. Metric definitions agreed and written down
6. A written answer to "what do we do when it's down"

---

## 11. People

| Person | Role |
|---|---|
| **Ryan Butkus** | Product launch engineer. Shaped the gate model; the reason it's correct. Roughly peer level |
| **Lothian** | Ryan's manager, over the plants. Key reviewer |
| **President** | Sponsor. Nathan's manager |
| **Zoe** | Enters Gate Zero data into the Excel tracker |
| **Mike Chambers** | IT. Built Galaxy, 25+ years. Contact for hosting and data triggers |
| **Craig** | Possible third editor |

Edit access is intended for Ryan, Lothian and possibly Craig.

**One rule worth keeping:** no metric reaches the president through this
dashboard before it has reached him through the normal reporting line. The
tool makes that reporting easier and better-evidenced; it doesn't route around
it. The author sits closer to the president than the process owners do, and
ignoring that is how a useful tool becomes a resented one.

---

## 12. History

| Date | What happened |
|---|---|
| 12 Aug | Capacity dashboard skeleton, synthetic data |
| 12 Aug | Launch Portfolio page added |
| 14 Aug | Review: numbered gate dots, simple-launch marker, two logins, entry forms, PRRs |
| 19 Aug | Review: real dates, Gate 3 = PPAP, `0/SL/4`, 6-month review, auto-calculated dates, filter fixes |
| 20 Aug | Gate editor rebuilt as plain date fields; workbook importer; schema aligned to the real sheet |
| 21 Aug | Storage hardened: locking, atomic writes, rolling backups |
| 23 Aug | Migrated to SQLite; daily backups with tested restore; go-live documentation |
| 24 Aug | Due-soon gate state; container deployment files; test suite |

Meeting transcripts are the authority on intent. This document summarises but
does not replace them.

---

## 13. Quick reference

```powershell
streamlit run app.py                    # run it
python run_tests.py                     # prove it works
python run_tests.py --quick             # faster, skips app boot
python launch_data.py                   # regenerate synthetic data
python tracker_import.py "file.xlsm"    # import the real workbook (local only)
python daily_backup.py                  # take a snapshot
python daily_backup.py --health         # is the backup arrangement working?
python daily_backup.py --verify         # are the backups restorable?
python daily_backup.py --list           # what snapshots exist
python daily_backup.py --restore <dir>  # restore from one
python preview.py                       # static chart preview, no Streamlit
docker compose up -d --build            # deploy
```

Repo: `https://github.com/nathanvanwieren239/capacity-dashboard` (private)

**Documentation:** `DEPLOY.md` · `docs/TEST-PLAN.md` ·
`docs/IT-brief-launch-tracker.md` · `docs/go-live-plan.md` ·
`docs/explainer-*.md` (written to be listened to)
