# The launch tracker: where it stands and what happens next

*A full account of the project as it is now — what was built, what has been
proven, what is still open, and what it takes to put it into service across
three plants. Written to be read aloud.*

---

## Part one: the problem this exists to solve

Two manufacturing plants run monthly product launch reviews. The data behind
those reviews lives in an Excel workbook that tracks every launch through a
sequence of gate reviews — kickoff, three intermediate gates, a PPAP
submission, the start of production, and a review six months afterwards.

That workbook has become a problem in a very specific way. Years of
accumulated conditional formatting and formulas reaching across sheets have
made it slow enough that it freezes during the very meetings it exists to
support. People sit in a room waiting for a spreadsheet to respond. The tool
that is supposed to make the review efficient is the thing making it painful.

So a dashboard was built. It reads the same data, draws a timeline of every
project and every gate, computes the metrics the business is measured on, and
lets a small group of authorised people record dates directly. It runs in a
browser. It does not freeze. And it can answer questions the spreadsheet
could not practically be asked.

Two decisions since then have changed what this project is.

The first: **this becomes the source of truth.** Not a view onto the
spreadsheet, not a mirror that gets refreshed — the authoritative home of
launch data. The spreadsheet gets retired.

The second: **it launches under the company president, across the three
Michigan buildings**, rather than as a departmental tool for one launch
engineer.

Neither of those changed the technology. Both changed what "ready" means.

---

## Part two: what is built and verified

It is worth being precise about this, because when you are looking at what is
left it becomes easy to lose track of what is finished.

**The gate model matches the real process.** Full launches run gate zero
through gate four, plus a six-month review. Simple launches — used when a
family of similar parts shares one full launch and the others follow behind —
skip gates one through three entirely and run kickoff, simple launch, gate
four. Gate three *is* the PPAP submission. Gate four *is* the start of
production. None of this was assumed; all of it was checked against the actual
workbook, where the gate three columns and the PPAP columns hold identical
dates, as do gate four and the start of production.

**The gate dates calculate themselves, and the arithmetic is confirmed
correct.** Gate one falls one third of the way between kickoff and PPAP; gate
two, two thirds. Run against a real project spanning a hundred and eight days,
the tool produces exactly the dates the spreadsheet contains — to the day.
That is the strongest single piece of evidence in the project, because it
means the tool encodes the rule the business already follows rather than a
plausible approximation of it.

**Three dates per gate, matching the sheet.** A planned date, an adjusted date
for when things move, and an actual date for what happened. On-time is
measured against the adjusted date where one exists, and falls back to the
plan where it does not.

**A second on-time number, deliberately.** Alongside that, the tool shows
on-time measured against the *original* commitment. On the demonstration data
those differ by seventeen points. The gap is the share of the on-time record
that depends on dates having been moved. That number is the reason the second
metric exists, and it is discussed properly later, because it is the most
politically loaded thing in the application.

**Two roles.** Viewers see everything and change nothing. Editors additionally
get the entry and editing forms. Every change is written to an audit log with
a timestamp, the role, the field, and both old and new values. Changes to a
planned date — as opposed to recording a slip — are tagged distinctly, because
changing a plan rewrites history rather than recording it.

**Storage that behaves like a real system.** The data lives in a SQLite
database — a single file, no server, nothing for anyone to install. Every
change runs inside a transaction. Two people saving during the same meeting
cannot silently overwrite one another; that was verified by running twenty
simultaneous writes and confirming every one survived, in sequence, with the
audit trail intact end to end. A gate cannot belong to a project that does not
exist, and deleting a project removes its gates.

**Backups that have been restored from, not merely taken.** Snapshots run
hourly if configured to, holding both a copy of the database and CSV files of
every table. Each one verifies its own integrity when written. The restore
path was tested by deleting the database and every working file outright and
rebuilding from a snapshot's CSVs alone — every project, gate, date and the
full change history came back identical.

**An importer for the real workbook** that reads the tracker sheet and joins
the gate zero summary for the sales-side fields. It is deliberately tolerant
of damage, which turned out to matter: the sanitised copy provided for testing
had broken formulas in fifty of its fifty-six rows.

---

## Part three: the decision that raised the bar

Declaring this the source of truth removed a safety net that had been there
quietly all along.

As a mirror, losing this data would have been irritating and nothing more. The
spreadsheet was in charge; you would re-import and lose an afternoon. As the
system of record, losing it means losing the record itself. Not a copy. The
record.

That reframes the questions. It stops being "do we have backups" and becomes:
how much work can we afford to lose, how long can we be without it, and how
long must these records survive?

The first has an answer now — an hour, with hourly snapshots. The second is
modest; this is business-useful rather than business-critical, and a day
without it means using yesterday's export. The third is the one people forget.
Automotive launch and PPAP documentation carries retention obligations
measured in years, often the production life of the part plus one. A backup
regime that keeps thirty days is fine for accidents and useless for
compliance. That is a conversation with whoever owns records retention, and
the annual CSV archive is what satisfies it, because it outlives the
application.

There is one gap remaining and it is not technical. Every backup currently
sits on the same machine as the database. That protects against a bad edit or
a wrong import — the failures that are most likely. It protects against
nothing that destroys the machine. Closing that requires somewhere to put
copies, which is a request rather than a task.

---

## Part four: what executive sponsorship changed

Almost nothing about the technology. Almost everything about how to proceed.

**The advice about IT inverted.** Earlier the thinking was to work with a
single contact and avoid pulling in the wider organisation, because broader
involvement risked adding months. For a departmental tool proving itself,
that was sound. With presidential sponsorship it is actively dangerous — a
tool that quietly avoided governance becomes *the president's system that IT
never approved* the moment anything goes wrong, which converts every future
problem into a political event. The right move now is to go through the front
door and let the sponsorship make governance fast, which is precisely what
sponsorship is good for.

**Availability expectations rise.** Not to any formal standard, but somebody
other than the author needs to be able to restart it, and there needs to be a
written answer to "what do we do if it is down." The honest answer is probably
"use yesterday's export and re-enter" — but that answer needs to exist before
it is needed rather than being improvised.

**Support becomes a thing that needs defining.** "The author, when he has
time" is not a support model for something a president sponsors. It does not
require a team. It requires being explicit: who to contact, what the response
expectation is, and what happens during holidays.

**Accountability in the audit trail matters more.** Shared role passwords were
a reasonable development shortcut when the audience was two people who trusted
each other. Once an executive is looking at on-time percentages, those numbers
evaluate people, and the ability to say *this person changed this date on this
day* stops being a nicety.

---

## Part five: the metrics are the political risk

This deserves its own section because it is the most likely thing to go wrong
and it has nothing to do with software.

Until now, on-time percentages were interesting. The moment a president looks
at them, they evaluate somebody. Two consequences follow.

**The definitions must be agreed before anyone is measured.** The seventeen
point gap between on-time-against-adjusted and on-time-against-original is
genuinely informative — but it is also exactly the kind of number that starts
an argument if it appears unannounced in an executive review. Decide which is
the headline, what the other one is for, and be able to explain both in a
sentence each.

**Somebody will eventually be measured badly by a number that is wrong.** Not
through malice — through a data entry error, a legitimately rescheduled
project, a gate closed but not recorded. When that happens the first instinct
will be to blame the tool, and the tool's credibility is most fragile in its
first quarter. The defences are the audit log, which turns a dispute into a
lookup, and the parallel run, which lets you point at agreement rather than
argue about it.

There is also a structural risk worth naming plainly. The tool's author sits
closer to the president than the process owners do. That means when a number
reflects badly on a plant, the author is positioned as the person who told the
president — which is the fastest way to turn a useful tool into a resented one.

The rule that prevents it: **no metric reaches the president through the
dashboard before it has reached him through the normal reporting line.** If
on-time drops at a plant, the person responsible for that plant reports it.
The dashboard's job is to make that reporting easier and better-evidenced, not
to route around it. Saying that out loud, early, to the people it protects
costs nothing and buys a great deal.

---

## Part six: the identity question

A small but instructive decision, worth understanding because the reasoning
generalises.

Roughly six people need edit access; everyone else only needs to look. Six
named accounts with properly hashed passwords is perhaps an afternoon's work,
and the obvious question is why involve anyone else at all.

The answer is not the security argument you would expect. It is offboarding.
When someone leaves the company or changes roles, IT disables their network
account. Nobody tells the person maintaining a separate password list. That
account keeps working, and a former employee retains edit access to launch
records until somebody happens to remember the tool exists. That is the most
common finding when a homegrown tool is eventually audited.

There are two smaller costs. The author becomes the password reset desk,
permanently. And people reuse their network password, which means the
application ends up storing a hash of a corporate credential — a liability
that did not previously exist and cannot easily be given back.

The pragmatic answer has three parts. Viewers do not need named accounts at
all, because the audit log only records changes and viewers cannot make any —
so a shared read-only password is fine and the problem shrinks to six people.
For those six, ask whether single sign-on is straightforward, because the
company is evidently a Microsoft environment and the integration may be small.
If it is easy, take it. If it is not, build named accounts as an interim, and
— this is the part that matters — agree a way of being told when somebody
leaves.

There is also a reason to ask that has nothing to do with technology.
Identity is IT's domain. Asking signals you know that. Building your own
quietly, on a system the president sponsors, is exactly what reads as going
around them.

---

## Part seven: what still needs proving

Honest assessment, ordered by value.

**A clean import of the real workbook.** The test copy was damaged, and while
the importer recovered what it could, that is recovery rather than a proper
trial. Importing an undamaged export and confirming the resulting numbers
match what the spreadsheet reports is the highest-value remaining test, and it
costs almost nothing.

**A full monthly cycle run in parallel, at every plant.** Not a demonstration
— an actual review, with the usual people, using the tool alongside the
spreadsheet rather than instead of it. Every disagreement between the two is
either a bug or a misunderstanding of the process, and both are worth finding
before the spreadsheet is retired. This was previously advisable. With three
plants and an executive audience it is the single most important item.

**Two people editing at once, in a room.** The behaviour has been verified
programmatically and is correct. That is not the same as two humans in a
meeting both making changes.

**A restore performed by somebody else**, following only the documentation.
That tests the documentation rather than the code, and the answer determines
whether it is adequate.

**Agreement on what the numbers mean**, signed off before anyone is evaluated
against them.

---

## Part eight: what is genuinely open

**The prototype route is invented.** Prototypes were added because they
consume the same laboratory and engineering capacity as launches and are
currently tracked nowhere. But the gate sequence they follow is a placeholder,
because no real one has been defined. Something plausible is better than
nothing, but it should not be mistaken for something agreed.

**The post-launch problem metric needs a definition.** Currently a count of
problem reports in the twelve months after production starts. It was suggested
this should be a rate or a percentage instead, but the denominator has never
been settled — per project, per part, per million shipped. These give very
different answers and imply different judgements.

**Whether the intake form can feed the tool directly.** The gate zero form was
recently improved so sales fills in one tab and it populates the rest. If it
could push a row into the dashboard rather than being retyped, a whole
category of transcription error disappears. Technically straightforward; needs
a decision.

**Whether the problem report counts can be pulled automatically** from the
system that holds them, rather than being looked up by part number and typed
in. That is a data connection to a system somebody else owns, which makes it a
conversation rather than a task.

---

## Part nine: the honest summary

The tool works. The domain model is verified against the real process rather
than assumed. The storage is sound, the concurrent-editing behaviour is
correct under deliberate abuse, and the backups have been restored from rather
than merely taken. None of that is the hard part any more.

What remains is almost entirely organisational: somewhere internal to run it,
storage that genuinely persists, a backup destination away from the machine,
an identity arrangement, and a parallel cycle at each plant before any number
is reported upward.

Each of those is small. Together they are the entire distance between a
convincing demonstration and something three plants depend on.

And there is one thing worth saying that is not on any list. A system of
record backed up by a script its author wrote, running on a server its author
configured, restorable by a procedure only its author has performed, has a
single point of failure — and it is a person rather than a machine. That is
fine for a promising internal tool. It stops being fine once three plants
depend on it and the spreadsheet has been retired.

Fixing that is not more code. It is making the arrangement legible to somebody
else: backups where the organisation already watches, a restore procedure a
second person has actually performed, retention agreed with whoever owns
records, and documentation good enough that its author could disappear without
the launch records becoming unrecoverable.

Every one of those is a conversation. They are the real work of turning
something that functions into something an organisation can rely on.
