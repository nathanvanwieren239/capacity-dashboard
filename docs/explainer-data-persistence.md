# Where the data lives: persistence, concurrency, and what breaks

*An explainer on the storage decisions facing the NN Launch Tracker dashboard,
written to be read aloud.*

---

## The situation

There is a dashboard. It replaces the reporting layer of an Excel workbook
that two manufacturing plants use to track product launches through a series
of review gates. The Excel file still exists, and still creaks — it is heavy
with conditional formatting and cross-sheet formulas, and it freezes during
the very meetings it is supposed to support.

The dashboard reads launch data, draws a timeline of gate reviews, and lets a
small number of authorised people edit dates. Right now it stores everything
in two plain text files: one listing projects, one listing the gates belonging
to those projects. Comma-separated values. The simplest possible database,
which is to say: not a database at all.

That was a deliberate choice while the thing was a prototype. It is about to
stop being a prototype. It is moving off a public demo host onto an internal
company server, and it is about to start holding real launch data instead of
invented placeholder data.

So the question becomes: when we move this to a real server, will the data
actually stick around?

The short answer is yes. The useful answer is that "sticking around" and
"being safe" are two different properties, and only one of them comes for free.

---

## What persistence actually means

On the current demo host, the application runs inside a container — a
disposable, self-contained box holding the program and everything it needs.
The important word is disposable. Every time new code is deployed, the old box
is thrown away and a fresh one is built from scratch. The box can also be
recycled at any time simply because nobody has used the app in a while.

Anything written inside that box dies with the box.

This is not a bug. It is the entire design philosophy of that kind of hosting.
The box is meant to be identical every time it is built, which means it cannot
be allowed to accumulate state. If it did, two copies of the same application
would drift apart, and the whole promise of reproducibility would collapse.

In manufacturing terms: it is a soft-jaw setup you cut fresh for every job.
Fast, repeatable, and you would never expect it to still be there next week.

Moving to a persistent internal server changes this. Now there is a real
filesystem, on a real machine, that survives restarts. Files written on Tuesday
are still there on Wednesday. That part genuinely is solved by the move.

But with one enormous caveat, which is worth saying out loud to whoever
administers that server: **the directory the application writes to must be
genuinely persistent.** If the app gets containerised for the internal server —
which is a very normal thing for an IT department to do — and the data
directory ends up inside the container rather than on a mounted volume outside
it, then absolutely nothing has changed. Same disposable box, different
address. The application will look like it works, right up until the first
redeploy silently erases three weeks of gate updates.

That is not a hypothetical failure mode. It is the single most common way this
exact category of application loses data.

---

## The problem nobody notices until it hurts

Assume the server is real and the volume is mounted properly. The data
persists. Now here is the failure that is much harder to see coming.

The application does not run one copy per user. It runs a single program, and
each person browsing it gets a session inside that one program. When someone
saves a change, the code does three things in sequence: it reads the entire
projects file into memory, it modifies the one row that changed, and it writes
the entire file back out.

Read. Modify. Write.

That sequence is fine when one person does it. Now picture two people doing it
at overlapping moments — which is precisely what will happen, because edit
access is intended for two or three people who will be sitting in the same
monthly review meeting looking at the same dashboard.

Ryan opens the file to change a PPAP date. A second later, before he saves,
Lothian opens the same file to change a project status. Ryan saves — his
version, containing his PPAP change, is written to disk. Then Lothian saves —
but Lothian's copy in memory was read *before* Ryan's change existed. Her
version does not contain it. Her write lands on top and Ryan's edit is gone.

No error appears. No warning. No conflict dialog. The file is perfectly valid.
It simply contains one fewer change than two people believe they made. Ryan
will find out three weeks later when he notices the date reverted, and he will
reasonably conclude the software is unreliable — which, in this specific
respect, it is.

Computer people call this a lost update, or more generally a race condition:
two operations racing, and the outcome depending on who happens to finish
last. It is the same shape of problem as two operators pulling from the same
bin of parts without a system: both of them counted twelve on the shelf, both
of them took ten, and neither of them is wrong about what they saw.

The fix is the same as it would be on the floor. You do not fix it by asking
people to be careful. You fix it by making the operation exclusive — one
person holds the bin, the other waits.

In software this is a lock. Before reading the file, the application claims it.
Anyone else attempting to save waits — for milliseconds, imperceptibly — until
the first save completes and releases it. The second person then reads the
*updated* file, applies their change on top, and writes. Both changes survive.

This is a small piece of code. It is also the difference between a tool people
trust and a tool people quietly stop using.

---

## Torn writes, and why renaming is safer than writing

There is a second, quieter risk in the same neighbourhood.

When the application saves, it opens the data file and writes over it from the
beginning. For a moment — a short moment, but a real one — the file on disk is
neither the old version nor the new version. It is half of each. If the process
is interrupted at exactly that instant, by a server restart or a crash or an
administrator being efficient, what remains on disk is a truncated file. Not
corrupted in an obvious way. Just... cut off partway through. Possibly in the
middle of a row.

This is called a torn write, and the standard remedy is elegant enough to be
satisfying: **do not modify the file at all.** Write the complete new version
to a temporary file alongside it. Verify it wrote successfully. Then rename the
temporary file over the top of the original.

The rename is the trick. On essentially every operating system, renaming a
file over another is atomic — indivisible. There is no observable moment where
it is half-done. Either the old file is there, complete, or the new file is
there, complete. An interruption at any point leaves you with one intact
version rather than one broken one.

The manufacturing parallel is close to exact. You do not modify a fixture while
a part is clamped in it. You build the second fixture on the bench, confirm it
is right, and swap it in during a changeover. The swap is quick and total.
There is never a moment where the machine is running against half a fixture.

---

## The undo problem

The third gap is the absence of any way back.

The dashboard keeps an audit log — every change, who made it, what the old
value was, what the new value is. That log is genuinely useful. If someone asks
why an on-time percentage moved, the answer is in there.

But an audit log is a record, not a mechanism. It tells you what happened. It
does not undo it.

The scenario that matters: the dashboard can import the entire tracker workbook
in one action, replacing everything currently loaded. That is a deliberate
feature and a useful one. It is also, by construction, the single most
destructive button in the application. Import the wrong file, or a file whose
formulas have broken — which has already happened once during development, where
fifty of fifty-six rows came through with reference errors — and confirm it,
and the previous contents are simply gone.

The remedy is unglamorous and effective: before every write, copy the current
files into a backup folder stamped with the date and time. Keep the last
several dozen. Storage cost is negligible; these are small text files. The
value is that a catastrophic mistake becomes a two-minute recovery instead of
a reconstruction exercise.

Nobody enjoys building backup systems. Everybody who has needed one and not had
one builds one immediately afterwards.

---

## The bigger fork: is this a database or a mirror?

The three fixes above — locking, atomic writes, backups — are perhaps an hour
of work, and they keep the data in plain text files that anyone can open in
Excel and read. That readability has real value during a period when people are
still deciding whether they trust the tool.

But there is a more fundamental option, and whether it is worth taking depends
on a question that has not been settled yet.

The alternative is to stop using text files and use SQLite instead. SQLite is a
proper database that lives in a single file. No server to administer, no
separate service to install, nothing for IT to maintain. It is the most widely
deployed database in existence, largely because it is invisible — it is inside
phones, browsers, aircraft.

What it provides that text files cannot is transactions. A transaction is a
group of changes treated as one indivisible unit: either all of them land or
none of them do. The database itself handles concurrent writers, guarantees
that a write either completed or did not, and makes torn writes structurally
impossible rather than merely unlikely.

In other words, SQLite solves all three problems properly, as a designed
property rather than as three patches.

So why not simply do that? Because of the unresolved question underneath.

If this dashboard becomes the **source of truth** — the place where launch data
actually lives, where the front office enters new projects, where gate dates are
recorded first — then it is a database application and it should use a database.
The text files are a liability.

But if the dashboard remains a **mirror** — if the Excel workbook on SharePoint
stays authoritative, and this reads a copy of it to produce charts and metrics —
then the storage layer is a cache, not a system of record. Losing it would be
annoying rather than serious, because the truth lives elsewhere and you re-import.
Hardening it heavily would be effort spent in the wrong place.

Those are genuinely different products with different risk profiles, and the
stakeholders have not chosen between them. There is a real tension in the
discussion: a preference for the dashboard to passively consume data from a
defined source of truth, set against a reasonable objection that splitting entry
across two locations is how data drifts apart.

That tension is unresolved, and it is the actual decision. The storage question
is downstream of it.

---

## The structural saving grace

One design decision made earlier makes all of this considerably less
frightening than it might otherwise be.

Every read and write in the application is funnelled through a single module.
Nothing else in the codebase touches a file directly. The charts do not know
where data comes from. The metrics do not know. The page layout does not know.
They all ask that one module, and it answers.

This means the storage layer can be replaced without touching anything else.
Swap text files for SQLite, or for a connection to a SharePoint-hosted workbook,
or for whatever the company standardises on — and the change is confined to one
file. Everything downstream continues working unchanged.

That is not an accident, and it is worth protecting. The moment some convenient
shortcut reads a data file directly from the charting code, that flexibility is
gone and the eventual migration becomes a rewrite instead of a substitution.

It is the software equivalent of designing a fixture with a standard interface
rather than bolting it directly to one specific machine. Slightly more thought
up front. Enormously cheaper when the situation changes — and the situation
always changes.

---

## Where this leaves things

Moving to an internal server solves persistence, on one condition: the data
directory must be on genuinely durable storage, not inside a disposable
container. That condition needs stating explicitly to whoever sets up the
server, because the failure is silent and delayed.

It does not solve concurrency, atomicity, or recoverability. Those need three
small deliberate additions — a lock, an atomic write, and rolling backups —
and they should be in place before real launch data goes in rather than after
the first lost edit.

The larger question of whether this becomes a database or stays a mirror is a
business decision, not a technical one, and it should be settled with the
stakeholders before more effort goes into the storage layer either way.

And the thing that makes all of this tractable is that the storage decision was
isolated from the start. It can be changed later, cheaply, which means it does
not have to be gotten perfectly right today. It only has to be gotten
*deliberately* right — which is a much lower bar, and a much better way to
build something you will have to live with.
