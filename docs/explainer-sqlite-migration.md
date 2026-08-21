# Option 4: moving the tracker to SQLite

*What it involves, what changes, what doesn't, and how much work it actually is.*

Written after implementing options 1–3 (locking, atomic writes, rolling
backups), which are now in place. This explains the remaining step.

---

## The short version

**Effort: roughly half a day.** One new file of about 150 lines, one deleted
concern, and no changes anywhere else in the application.

**What it buys:** the three problems that options 1–3 patch become
structurally impossible rather than handled. Plus query-ability, which turns
out to matter more than it sounds.

**What it costs:** the data stops being readable in Excel and Notepad.

**The one reason to wait:** if the Excel workbook stays the source of truth
and this dashboard is only ever a mirror, the storage layer is a cache and
hardening it further is effort in the wrong place. That decision is still open
with Ryan.

---

## What SQLite actually is

Worth clearing up, because the word "database" makes people think of servers,
licences, and IT tickets.

SQLite is none of those. It is a single file on disk, and a library that reads
and writes it. There is no server process, no installation, no service to
administer, no port to open, no credentials to manage. Python ships with it
built in — it is already on every machine running this app, including the
company server, whether or not anyone installs anything.

It is the most widely deployed database in the world by a wide margin. It is
inside every phone, every browser, most aircraft avionics, and a great deal of
industrial equipment. It is specifically designed for exactly this situation:
an application that needs real data guarantees but does not need, and should
not have, a database server behind it.

From an IT perspective, deploying this changes nothing. It is still "a folder
with an app in it." The data file simply goes from two CSVs to one `.db`.

---

## What actually changes in the code

Almost nothing, and that is by design.

Every read and write in this application already goes through a single module,
`store.py`. The charts do not touch files. The metrics do not touch files. The
page layout does not touch files. They all call that one module, and it deals
with the details.

That means the migration is a substitution, not a rewrite:

- **`store.py`** — rewritten internally. Same function names, same arguments,
  same return values. `create_project()`, `update_project()`,
  `save_gate_dates()`, `replan_gates()`, `replace_gates()` all keep their
  signatures. Callers cannot tell the difference.
- **`launch_model.py`** — the two loader functions read from the database
  instead of parsing CSVs. Everything downstream still receives the same
  dataframes it does today.
- **A new `schema.sql`** — about thirty lines defining three tables:
  projects, gates, and the audit log.
- **A one-time migration script** — reads the current CSVs, writes the
  database, verifies the row counts match. Run once, keep it around for
  reproducibility.

**Unchanged:** every chart, every metric, every filter, both pages, the login
system, the workbook importer, the preview script, and all the gate
arithmetic. They neither know nor care where the rows come from.

`safe_io.py` — the locking and atomic-write module just built — largely
retires. SQLite does all of that internally and better. The backup function
stays, because a snapshot of a single `.db` file is even simpler than
snapshotting two CSVs.

---

## What it buys, concretely

### The three problems stop being problems

Options 1–3 are patches around the fact that CSV files have no concept of a
transaction. Each one is correct, and each one is something we have to
maintain and reason about.

SQLite has transactions as a foundational property. A group of changes either
all commit or none do. Concurrent writers are serialised by the database
itself, correctly, without an advisory lock file that could be left stale by a
crash. A write either completed or did not — there is no torn state to protect
against, because the database maintains its own journal and recovers itself on
the next open.

The distinction matters: right now, correctness depends on remembering to hold
the lock around the *whole* read-modify-write, every time, in every new
function anyone ever adds. With a database, forgetting is not an available
failure mode.

### Rewriting the whole file stops happening

Today, changing one date rewrites both entire CSV files. At 22 projects that
is invisible. At the real scale — 56 projects in the sanitised workbook, more
in the live one, growing over years, with a gate history and an audit log that
only ever gets longer — rewriting everything on every keystroke-level save
starts to be noticeable, and the audit log is the file that grows without
bound.

A database updates the row that changed.

### Querying becomes possible

This is the benefit that is hard to see until it is there.

Right now, every question the dashboard answers is computed by loading
everything into memory and filtering with pandas. That is fine, and it is fast
enough. But it means every new question requires new Python.

With a database, questions can be asked directly:

- "Which gates slipped more than 30 days, by plant, last quarter?"
- "What is the average kickoff-to-SOP duration by launch type?"
- "Show every project where the adjusted date moved more than twice."

That last one is precisely the accountability question underneath the on-time
metric — the one Ryan cares about — and today it would need bespoke code.

It also opens a door worth knowing about: Power BI, which came up in review as
an alternative platform, connects to SQLite directly. If the company ever
decides to standardise on Power BI, having the data in a database rather than
CSV files means it can read the same source rather than needing an export
pipeline. That is not a reason to migrate on its own, but it is a real option
that CSVs do not give.

### Referential integrity

A gate row belongs to a project. Right now nothing enforces that. A bug, or a
partial write, or a hand-edited CSV could leave gate rows pointing at a project
that does not exist, and the application would either crash or silently drop
them.

A database enforces it. A gate cannot reference a project that is not there,
and deleting a project can be defined to remove its gates automatically. The
class of bug disappears rather than being tested for.

---

## What it costs

**The data stops being human-readable.** Today, anyone can open
`projects.csv` in Excel and look. That has genuine value while people are
still deciding whether they trust this tool — being able to check the
dashboard against the raw rows is reassuring in a way that matters.

This is a real loss and worth mitigating deliberately. Two ways:

1. Keep a **CSV export button** in the app. One click, current data, opens in
   Excel. Ten minutes to build.
2. Note that **DB Browser for SQLite** is a free tool that opens the file in a
   spreadsheet-like grid. Useful for anyone technical who needs to poke at it,
   though not something to expect a general user to install.

With the export button in place, the practical loss is small: nobody actually
needs the *storage format* to be readable, they need to be able to *get the
data out*, and that stays true.

**Slightly more concepts to hold.** SQL is a second language in the codebase
alongside Python. It is a well-known one and the queries here would be simple,
but it is not nothing for whoever maintains this next.

**A migration to get wrong.** Running the conversion, verifying it, and being
confident nothing was dropped is a real if small piece of work. Mitigated by
keeping the CSVs as a backup until the database has been in use long enough to
trust.

---

## What it does not fix

Worth being explicit, because it is easy to oversell a database.

**It does not answer the source-of-truth question.** If the Excel workbook
stays authoritative and this stays a mirror, a database is a nicer cache. It
does not change the fact that data is being maintained in two places, which is
the thing Ryan objected to.

**It does not give named accounts.** The audit log will still record that *an*
editor made a change, not which one. That needs real authentication, which
comes with internal hosting, not with the storage layer.

**It does not remove the need for backups.** A single-file database is easier
to snapshot, but "I imported the wrong workbook and confirmed it" is still a
recoverable-only-if-you-have-a-backup situation.

---

## The recommendation

Do it, but sequence it correctly.

**Now:** options 1–3 are in place. The application is safe on a persistent
server with two or three concurrent editors. That was the blocking concern and
it is resolved. Nothing prevents deploying internally today.

**Next:** settle the source-of-truth question with Ryan. Is this the system of
record, or a view onto the Excel workbook? Everything downstream depends on it.

**Then:** if the answer is "system of record," migrate to SQLite. Half a day,
low risk, and it removes an entire category of thing-to-be-careful-about. If
the answer is "mirror," leave it on CSVs — the hardening already done is
proportionate for a cache, and the effort belongs on the import pipeline
instead.

The reason this is a comfortable position to be in rather than an anxious one
is that the storage layer was isolated from the beginning. That decision was
cheap when it was made and it is what makes this a substitution rather than a
rewrite. It also means the decision does not have to be made under pressure —
the migration will be the same half a day whether it happens next week or next
quarter.

---

## Rough plan, if it goes ahead

1. Write `schema.sql` — three tables, indexes on project id and gate code.
2. Write `migrate_to_sqlite.py` — read CSVs, write the database, assert the
   row counts and a checksum of key fields match. Keep it in the repo.
3. Rewrite `store.py` internals against the database. Signatures unchanged.
4. Point the two loaders in `launch_model.py` at the database.
5. Add a CSV export button to the app.
6. Retire the locking half of `safe_io.py`; keep the backup half.
7. Verify: run the existing test approach against both pages and both roles,
   plus the concurrency test that currently proves the lock works — it should
   pass unchanged, which is the point.
8. Keep the CSVs untouched alongside the database for a few weeks.
