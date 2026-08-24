# Test plan

How to verify this yourself, what each test proves, and what to do when one
fails.

Two parts: an automated suite you run with one command, and a short list of
things that genuinely need a human.

---

## Part 1 — the automated suite

```powershell
cd C:\Users\nleev\Dashboarding
.\.venv\Scripts\Activate.ps1
python run_tests.py
```

Takes about 20 seconds. `--quick` skips the three slowest (they boot the app
for real). `--keep` leaves the temporary workspace behind if you want to poke
at it.

### It cannot damage your data

Every test runs against a *copy* of the application in a temp directory, built
fresh each time with no `data/` folder. Your real database is never opened.

That matters because one of the tests deliberately deletes a database and
rebuilds it — which is the whole point of it, and not something you want
happening to your working copy by accident.

### What you should see

```
11 passed, 0 failed, 0 skipped
```

Each line prints what it actually proved rather than just "ok", so the output
is worth reading rather than skimming. It's also worth keeping — it is
evidence you can point at.

### What each test proves

**1 · modules import** — nothing is syntactically broken and there are no
circular imports. Catches the class of mistake where an edit looks fine and
the app won't start.

**2 · fresh install builds its own database** — deploy to an empty directory
and it creates its own schema and demo data. This is the path IT will hit on
first run, and the one most likely to be untested.

**3 · gate dates match the tracker sheet** — takes the real example from the
workbook (kickoff 17 Dec 2024, PPAP 4 Apr 2025) and asserts gate 1 lands on
22 Jan and gate 2 on 27 Feb, which is exactly what the spreadsheet contains.
Also checks gate 3 equals PPAP, gate 4 equals SOP, and that a simple launch
has only `0 / SL / 4 / 6M`.

This is the most valuable test in the suite. It proves the tool encodes the
rule the business already follows rather than something that merely looks
plausible.

**4 · concurrent edits cannot overwrite each other** — fires twenty
simultaneous writes at two projects and then checks the *audit chain*: every
entry's "old value" must equal the previous entry's "new value". If two writes
had overlapped, that chain breaks and the test says exactly where.

This is the gap you told Ryan you were closing. This is the proof.

**5 · backups are written and self-verify** — a snapshot is taken and must
contain the database, the CSVs and a manifest, and pass SQLite's own
integrity check.

**6 · DESTROYED database rebuilt from backup** — the one you asked about. It:

- makes an edit tagged `RESTORE-CANARY` so there's something identifiable
- takes a snapshot
- deletes `tracker.db`, its two journal files, and all three loose CSVs, so
  nothing can quietly bootstrap from leftovers
- confirms the database is genuinely gone
- rebuilds from the snapshot's **CSVs alone** — not the database copy
- asserts the project count, gate count and project IDs all match
- asserts the audit history is the same length
- finds the canary edit
- and compares every gate date column row by row for exact equality

If that passes, "we can recover" is a fact rather than a hope.

**7 · corrupted backups are detected** — deliberately writes 200 null bytes
into the middle of a backup database and confirms verification fails. Then
truncates a CSV by three rows and confirms the row-count mismatch is caught.
Then restores both and confirms the snapshot verifies clean again.

A backup that silently rots is worse than no backup, because you find out at
the worst possible moment.

**8 · database rejects orphaned records** — tries to insert a gate belonging
to a project that doesn't exist and expects it to be refused, then confirms
deleting a project removes its gates.

**9 · app boots, both roles, both pages** — logs in as viewer and as editor,
confirms both pages render, confirms the editor sees the entry forms and the
viewer does *not*, and confirms a wrong password is rejected with nothing
rendered.

**10 · filter combinations** — runs the sidebar filter cases that have broken
before, including prototype-only, which was a real bug.

**11 · passwords from environment variables** — deletes the secrets file and
logs in using environment variables only. This is the path a container uses,
so if it breaks, the Docker deployment breaks.

### When something fails

The failing test prints the assertion message and a short traceback. They're
written to say what went wrong in plain terms — for example a concurrency
failure names the project and the exact entry where the chain broke.

Re-run with `--keep` and inspect the workspace it leaves behind.

---

## Part 2 — the things a human has to do

The suite covers logic. These cover reality.

### A · Click through the app yourself

```powershell
streamlit run app.py
```

Sign in as `editor`. Then:

- **Pick a project** from *Edit existing*. Check the heading above the gate
  dates names the project you chose — that was a real usability bug.
- **Record a gate.** Put a date in **Actual** for an open gate, save, and
  watch the dot turn green on the timeline.
- **Record a slip.** Put a future date in **Adjusted** on another gate, save,
  and confirm the gate moves along the timeline.
- **Watch the scorecard.** The two on-time numbers should diverge as you
  record things late — that divergence is the point of having both.
- **Check the blue.** Gates due within 14 days should be light blue. There
  should be six in the demo data.
- **Sign out, sign in as `viewer`.** Confirm the entry section is replaced by
  a read-only notice and there are no editing controls anywhere.

`st.data_editor` — used in the *Advanced* gate expander — cannot be driven by
the automated harness. If you use that expander, click it by hand.

### B · Two people editing at once

The automated test proves the mechanism. This proves the experience.

Get Ryan on a call, both open the app, both edit *different* gates on the
*same* project, and both save within a few seconds of each other. Then open
the audit log and confirm both changes are there.

Then do it again on the *same* gate and see what happens — the second save
wins, which is correct, but it's worth knowing that's the behaviour so nobody
is surprised by it later.

### C · Import a clean workbook

```powershell
python tracker_import.py "path\to\clean-tracker.xlsm"
```

The copy used in development had `#REF!` in 50 of 56 rows, so the mapping has
only ever been verified against damaged data. With a clean export:

- Check the project count matches the sheet.
- Spot-check three or four projects — plant, PM, job number, gate dates.
- Compare the on-time percentages against whatever the spreadsheet reports.

Any disagreement is either a bug or a difference in how the metric is
defined, and both are much cheaper to find now.

### D · Restore, done by somebody else

Ask Ryan — or anyone — to restore from a backup using only `DEPLOY.md`,
without you helping.

That tests the documentation rather than the code. If they get stuck, the
documentation is wrong, and you would rather find that out now than during an
incident.

### E · Container deployment

You don't currently have Docker locally, which is fine — see the note below.
Once it can be built, the two tests that matter:

**Build it.**
```bash
docker build -t launch-tracker:test .
docker compose up -d
```
Open `http://localhost:8501`, confirm the login page appears.

**Then the important one — prove the volume works.**
```bash
# make a change through the UI, then:
docker compose down
docker compose up -d --build
```
Your change must still be there. If it isn't, the data directory is inside the
container rather than on a volume, and that is the failure that silently
destroys everything on every redeploy.

Do this before real data goes anywhere near it.

---

## On Docker not being installed

`docker` isn't on your machine, and that is worth thinking about before you
try to fix it.

Docker Desktop requires a paid subscription for companies above a fairly low
size threshold, so installing it on a corporate machine is a licensing
question rather than just a download. Free alternatives exist — Podman
Desktop, Rancher Desktop, or the Docker engine directly inside WSL2 — but all
of them mean installing something on a work machine, possibly needing admin.

**The pragmatic answer is not to block on this.** The container files are a
convenience for whoever deploys it, not a requirement of the application.
Chambers almost certainly has Docker already and can build it in two minutes.

What matters is honesty about their status. Rather than presenting them as
tested, say plainly that they are provided as a starting point and haven't
been built locally because Docker isn't installed. That is a completely
normal thing to say, it costs nothing, and it is far better than having him
discover it.

Everything else — the application, the database, the backups, the restore —
has been tested and you can say so without qualification.

---

## What to run, and when

| When | What |
|---|---|
| After any code change | `python run_tests.py --quick` |
| Before showing anyone | `python run_tests.py` in full |
| Before handing to IT | Full suite, plus a manual click-through |
| Before real data | Everything above, plus the container volume test |
| Before retiring the spreadsheet | All of it, plus a parallel monthly cycle at each plant |
| Every few months | Full suite, plus a restore performed by someone else |
