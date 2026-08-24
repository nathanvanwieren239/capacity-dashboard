# Backing up a system of record: what changes, and the options

*Written after the decision that this dashboard becomes the authoritative
home of launch data rather than a view onto a spreadsheet. That decision
changes what "good enough" means. Intended to be read aloud.*

---

## Why the decision changes everything

Up to this point the dashboard was a mirror. The Excel workbook was in charge,
and the dashboard read a copy of it. If the dashboard's data had been lost, it
would have been irritating — an afternoon of re-importing — but nothing would
actually have been destroyed, because the truth lived elsewhere.

Declaring this the source of truth removes that safety net entirely. From the
moment the first gate date is recorded here and nowhere else, losing this data
means losing the record. Not a copy of the record. The record.

That reframes the question. It stops being "do we have backups" and becomes
three sharper ones, which are the questions any organisation should be able to
answer about a system it depends on.

**How much work can we afford to lose?** If the server fails at four in the
afternoon, how far back does everyone have to redo? An hour of re-entry is
annoying. A month is a crisis, because nobody remembers what they typed three
weeks ago.

**How long can we be without it?** If it fails the morning of the Kentwood
review, is the answer twenty minutes or two days?

**How long must the records survive?** This is the one people forget. In
automotive manufacturing, launch and PPAP documentation carries retention
obligations — often the production life of the part plus a year, sometimes
longer depending on the customer. A backup regime that keeps thirty days is
fine for accidents and useless for compliance.

The first two have names in the trade: recovery point objective and recovery
time objective. They are worth using because they force the conversation to be
about numbers instead of feelings.

---

## What we have now, honestly assessed

The current arrangement, before this decision, was a snapshot taken once a day
holding both a copy of the database and a set of CSV files, kept for thirty
days with one snapshot per month preserved for two years, all sitting next to
the database on the same machine.

For a mirror, that was proportionate. For a system of record it has three
specific problems.

**A whole day of exposure.** Snapshots once a day means up to twenty-four
hours of work can vanish. The shape of the usage makes this worse than it
sounds: editing is not spread evenly through the month, it clusters around the
review meetings. Somebody sits down after a Kentwood review and enters forty
gate updates in one sitting. If the disk fails that evening, all forty are
gone, and reconstructing them means reconstructing a meeting from memory.

**Every copy is in one place.** This is the big one, and it is not really a
technical problem. Backups sitting beside the thing they are backing up
protect against exactly one category of failure — the mistake, the bad import,
the wrong edit. They protect against nothing that destroys the machine. The
old rule of thumb is three copies, on two kinds of media, with one somewhere
else. Right now there is one place.

**Nobody checks the backups are real.** A backup that has silently been
failing for six weeks looks identical to a backup that is working, until the
day it does not. Corruption is quiet.

The first and third are cheap to fix, and now have been. The second is a
conversation, not a task.

---

## What has been done about it

**Snapshots can now run hourly.** One setting. The mechanism is the same, it
simply runs more often, and because the data is tiny — a database measured in
tens of kilobytes — hourly costs essentially nothing in storage or time. That
takes the worst case from a day of lost work to an hour.

**Every snapshot verifies itself.** When a snapshot is taken, the copied
database is asked to check its own integrity, and the result is recorded
alongside it. There is also a command that walks every snapshot on disk and
confirms the files parse, the row counts match what the snapshot claims, and
the database passes its integrity check. This was tested by deliberately
corrupting a backup and confirming it was caught, and by deleting rows from a
CSV and confirming the count mismatch was flagged.

**The application reports on its own backups.** A panel shows whether the
newest snapshot is recent enough, whether it passed verification, and whether
an off-machine copy is configured. If any of those is wrong, it says so
prominently rather than staying quiet. A silently failing backup is now a
visible failing backup, which is the entire difference.

**Restore has been performed, not assumed.** The database and every working
file were deleted outright, and the system was rebuilt from a snapshot's CSV
files alone. Every project, every gate, every date and the full change history
came back identical. That test is what separates a backup from a hope.

What remains is the off-machine copy, and that requires somewhere to put it.

---

## The options

Five approaches, roughly in order of effort. They are not exclusive — the
sensible answer combines several.

### Option one: a network share

Point the application at a network path. Every snapshot is copied there
automatically as it is taken.

This is the cheapest meaningful improvement available. It costs one
configuration setting and a folder on a file server. It gets copies off the
machine, and if that file server is already covered by the company's backup
regime — which it almost certainly is — it inherits everything: off-site
replication, tape or cloud archive, whatever the organisation already does,
including retention that satisfies the record-keeping obligations.

The weakness is that a network share is a single destination. If it is
unreachable when a snapshot runs, that snapshot does not get mirrored. The
application reports this rather than failing silently, but it is worth knowing.

**Do this regardless of what else is chosen.** It is close to free and it
closes the largest hole.

### Option two: let the existing infrastructure back up the whole machine

Rather than the application copying files anywhere, ask for the server itself
to be included in whatever backup arrangement already exists — nightly image,
snapshotting, an agent, whatever the standard is.

The appeal is that it is somebody else's job. It gets professional retention,
off-site copies, and a restore procedure that people have practised, none of
which needs building or maintaining.

The catch is granularity and timing. A nightly machine image puts the exposure
back to twenty-four hours, and restoring one file from a whole-machine backup
is usually a request rather than something done in five minutes during a
meeting.

The two combine well: machine-level backup as the safety net, application
snapshots as the fast path for the ordinary case of "somebody made a mistake
this morning."

### Option three: continuous replication

There is a category of tool that watches a SQLite database and streams every
change to another location as it happens, allowing restoration to any point in
time — not just to the last snapshot, but to the state five minutes before
someone did something regrettable.

This takes the exposure from an hour to seconds.

Whether it is worth it depends on the change rate, and here the change rate is
low. A few dozen edits a month, concentrated around two meetings. The
difference between losing an hour and losing five minutes is, in practice, the
difference between redoing a few entries and redoing almost none. Both are
recoverable inside a coffee break.

It is the right answer for a system taking hundreds of transactions an hour.
It is over-engineering for this one, and it adds a component that must be
installed, monitored and understood by whoever inherits this. That maintenance
burden is a real cost in a tool with one author.

### Option four: move to a database server

If the company already runs a proper database server — SQL Server is the
common case in a Microsoft environment — the data could live there instead of
in a file.

The argument for it is governance rather than technology. A corporate database
is already backed up, already monitored, already has a restore procedure
somebody has rehearsed, and already sits inside whatever compliance framework
the organisation operates. Using it means the backup question stops being
yours. For a genuine system of record, that is a strong argument, and it is
stronger the more the organisation cares about audit and retention.

The argument against is dependency. It means a database administrator becomes
part of every change, credentials must be managed, a network path exists that
can break, and the deployment stops being "a folder with an app in it." It
also means a wider IT conversation — precisely the thing that risks turning a
few weeks into a few quarters.

The pragmatic reading: not now, but leave the door open. The application's
storage is deliberately isolated in one module, so this remains a substitution
rather than a rewrite whenever the organisation is ready.

### Option five: an export that outlives the application

Slightly different in kind, and worth doing regardless.

Every snapshot already includes CSV files, not just the database. This is
deliberate. In five years the Python may not run, the libraries will have
moved on, and whoever needs a launch record from 2026 may have no working copy
of the tool. Dated folders of CSV files remain readable by anything, forever,
including by a person with a spreadsheet.

For the compliance question specifically — records that must survive for the
production life of a part plus a year — this is the format that matters. A
yearly archive of CSV exports, placed wherever the quality function keeps its
retained records, satisfies retention obligations without depending on this
application still existing.

Worth raising with whoever owns records retention, because they will have a
view and it is better to hear it now.

---

## The recommendation

**Immediately, and cheaply:** turn on hourly snapshots and point the
application at a network share that is already backed up. That is one setting
and one folder request. It takes the worst case from a day of lost work to an
hour, and gets copies off the machine.

**As part of provisioning:** ask for the server to be included in the standard
backup regime. Not instead of the above — as well as. Two independent
mechanisms failing at once is much less likely than one.

**At go-live:** perform a restore, on a copy, with someone other than the
author driving from the documentation. Then do it again in six months. A
restore procedure nobody has practised is a document, not a capability.

**Annually:** archive a CSV export wherever quality records are kept, in
whatever format the retention policy expects.

**Leave alone for now:** continuous replication and moving to a database
server. Both are legitimate and both are more than this needs today. The
architecture keeps them available.

---

## The point that is not technical at all

There is one more thing, and it may be the most important.

A system of record backed up by a script its author wrote, running on a server
its author configured, restorable by a procedure only its author has
performed, has a single point of failure — and it is a person, not a machine.

That is fine while this is a promising internal tool. It stops being fine the
moment two plants depend on it and the spreadsheet has been retired.

The remedy is not more code. It is making the arrangement legible to somebody
else: the backup destination somewhere IT already watches, the restore
procedure written down and practised by a second person, the retention
schedule agreed with whoever owns records, and the whole thing documented well
enough that its author could be hit by a bus without the launch records
becoming unrecoverable.

Every one of those is a conversation rather than a task. They are the actual
work of turning something that functions into something an organisation can
rely on.
