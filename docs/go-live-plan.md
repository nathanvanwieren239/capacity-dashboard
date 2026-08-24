# The launch plan: getting this into service

*The sequence, the decisions inside each step, and what has to be true before
moving on. Written to be read aloud, and to be worked from.*

---

## The shape of the thing

This is going live under the company president, across three Michigan
buildings, as the authoritative home of launch data. The spreadsheet gets
retired.

There are four groups of people involved and each has a distinct role. The
launch engineer owns the process — he shaped the gate model and he is the
reason it is correct. His manager runs the plants that already use the
tracker. The president provides the mandate. And the author owns the tool.

That is an unusually complete set. Most tools that reach an executive have a
gap somewhere in that chain — no process owner, or no mandate, or no clear
ownership. Nothing here needs inventing; it needs sequencing.

The whole plan is five steps, and the order matters more than the content of
any one of them.

---

## Step one: sound out IT, without asking for anything

This is the step most people get backwards, so it is worth being clear about
why it comes first and why it is not a request.

The instinct is to secure the plant manager's buy-in and then go to IT with a
mandate. That is the right *second* IT conversation. But going in cold, having
promised somebody a date, is how you end up committed to something the
infrastructure cannot support.

So the first conversation is deliberately not an ask. It is fifteen minutes of
finding out what is possible, so that nothing gets promised that cannot be
delivered.

Say explicitly that nothing needs deciding today. That single sentence lowers
the temperature of the entire conversation, because nobody has to take
responsibility for anything.

What you want to leave with is not a commitment. It is three things: whether
internal hosting is realistic at all and roughly what shape it takes,
somewhere that backups could live, and — most valuable — their answer to the
question *if this ended up used by three plants, what would you want to see
from me first?* That last answer is your actual specification for what ready
means in this organisation, in their words, before you have failed to meet any
of it.

Two things not to do. Do not mention the president; using executive weight in
a fact-finding conversation is a threat whether you intend it that way or not,
and you cannot take it back. And do not demo unless asked — volunteering one
turns a five-minute constraint check into an evaluation, and evaluation is
what you want happening after there is a mandate, not before.

**Move on when:** you know whether hosting is realistic, and what their bar is.

---

## Step two: the plant manager

Now show it to the person who runs the plants, having already checked what is
possible.

The framing that protects everyone is that this is work the launch engineer
shaped. That is true, it costs nothing to say, and it changes how the tool
lands with the people who will actually have to fill it in. Mandate can compel
use; it cannot compel enthusiasm, and a tracker people resent gets filled in
badly.

Three things to get out of this conversation.

Does he want it — genuinely, as opposed to politely. What does he need it to
do that it does not do yet. And what does he consider the headline metric,
because that decision has to be made by somebody who owns the outcome rather
than by the person who built the tool.

Bring the metric question up yourself. The tool shows on-time two ways, and
they differ by seventeen points on the demonstration data. One measures
against the date last agreed; the other against the date originally committed.
Both are legitimate and they answer different questions. Letting him choose
which leads, and understanding why, is how you avoid that difference becoming
an argument in front of an executive later.

Also raise the reporting rule here, because it protects him and it is better
coming from you: no number reaches the president through the dashboard before
it has reached him through the normal line. If on-time drops at a plant, the
person accountable for that plant reports it. The tool makes that reporting
easier and better-evidenced; it does not route around it.

**Move on when:** he wants it, you know what the headline metric is, and you
know what he needs added.

---

## Step three: back to IT, with a mandate

Now the ask is real, and it is much stronger than it would have been a week
earlier: *the plant manager wants this live for three sites, here is roughly
when, here is what I checked with you about last time.*

There are five things to request, and it is worth asking for all of them in
one conversation rather than returning three times. Executive sponsorship has
a short half-life — it is most useful before the project becomes routine.

**Somewhere to run it.** A small virtual machine, or a container on whatever
platform already exists. One process, one port, no licences, nothing to buy.

**Storage that genuinely persists.** This is the one to be immovable about,
and to say in plain words: *if this gets containerised, the data directory has
to be on a mounted volume, not inside the container.* Containers are designed
to be rebuilt identically on every deployment, and anything written inside one
dies when it is. Get this wrong and the application will appear to work
perfectly until a redeploy silently erases every gate update since the last
one. It is quiet, delayed and total, and one sentence prevents it.

**A backup destination away from the machine.** Either the data folder gets
included in whatever backup regime already exists, or a network path to mirror
snapshots to. Whichever is easier for them. The application already snapshots
itself hourly, verifies each snapshot's integrity, and has a tested restore —
what is missing is somewhere off the box to put copies, which is the only
thing they need to provide.

**Identity for six people.** Not everyone — only the editors. Everyone else
can stay on a shared read-only password, because the audit trail only records
changes and viewers cannot make any. The specific question is whether
registering an application in the company's identity system is
straightforward. If yes, take it; the audit log then names a person rather
than a role. If it is a whole project, build named accounts as an interim and
agree a way of being told when somebody leaves — because that, rather than
password strength, is the actual risk with a private user list.

**One named person in IT** who knows how it is deployed and could restart or
restore it. This is the best available answer to the problem that the tool
currently depends on one individual, and it will never be easier to ask for
than while the sponsorship is fresh. It also makes IT a stakeholder rather
than a landlord, which is worth a great deal over time.

On everything else — how it is deployed, what the machine is called, patching,
monitoring, whether it sits behind a proxy — defer visibly and early. That is
genuinely their expertise, and conceding the things you do not care about
earns standing on the two that you do.

**Move on when:** you have a host, persistent storage, and a backup
destination. Identity and the named contact can follow.

---

## Step four: deploy, import, and prove it

The technical sequence, in order, with the reasoning attached.

Stand it up on the host and set real passwords, not the development ones.

Then confirm the storage genuinely persists before trusting it with anything.
Write a file, have it redeployed, check the file survived. This takes ten
minutes and it is the difference between finding out now and finding out in
six weeks with real data.

Point it at the backup destination and turn snapshots up to hourly. Confirm a
snapshot appears in both places.

Then import a clean export of the real workbook — clean being the operative
word, because the copy used in testing had broken formulas in most rows. Check
the resulting numbers against what the spreadsheet reports. Disagreements here
are the cheapest bugs you will ever find.

Then, before relying on any of it, perform a restore on a copy. Not because
the restore is untested — it has been, thoroughly — but because a restore
procedure that only its author has run is a document rather than a capability.
Ideally have somebody else do it, working from the documentation alone.

Register the backup as a scheduled task so it does not depend on somebody
opening the application.

**Move on when:** real data is loaded, the numbers agree with the spreadsheet,
and a restore has been performed successfully.

---

## Step five: parallel running, then the president

Run one full monthly cycle at each plant, using the tool alongside the
spreadsheet rather than instead of it.

This is the single most important item in the entire plan and the one most
likely to be skipped under pressure. Every disagreement between the two
systems is either a bug in the tool or a gap in how the process is actually
being recorded, and you want to find both while the spreadsheet is still there
to fall back on.

Consider offering a staged rollout even if the mandate covers all three
buildings — one plant for a cycle, then the rest. It is far easier to recover
from, it gives you a genuine success to point at before a wider audience forms
its opinion, and offering it yourself demonstrates judgement. If the answer is
all three immediately, that is a legitimate call, but the offer costs nothing.

Then the president.

Demo differently for him than for anyone else. The launch engineer cares about
gate editing; a president cares about three things — are launches on time,
where is the risk, and what is coming. Lead with the timeline and the
scorecard. Do not demonstrate data entry: it makes the tool look like a data
entry system rather than a management view, and it invites questions about who
types what.

Do not bring architecture upward. Not the database choice, not the platform
question. Executives should be asked for mandate and priority, never for
technical decisions, because asking invites an answer and an offhand
suggestion from a president becomes a directive whether it was meant as one or
not.

Ask for three things: a stated expectation that this is now the tracker, so
adoption at plant level is not optional; a named IT contact assigned rather
than requested; and an agreed date when parallel running ends. That last one
converts "we'll see how it goes" into a plan with an end state.

And say one thing before the parallel cycle rather than after: *the numbers
from the tool and the spreadsheet will disagree in the first month, and every
disagreement is worth investigating, because it is either a fault in my tool
or a gap in how the process is being recorded.*

Predicted, that is diligence and it makes you look like somebody who has done
this before. Discovered, it is a bug, and it costs credibility at exactly the
moment there is least to spare.

---

## What has to be true before the spreadsheet is retired

A short list, and none of it is negotiable.

Real data is loaded and its numbers agree with the spreadsheet's. A full
monthly cycle has run in parallel at every plant. A restore has been performed
by somebody who is not the author. Backups exist somewhere other than the
machine running the application. The metric definitions are agreed and written
down. And there is a written answer to what happens when the tool is
unavailable, even if that answer is simply to use yesterday's export.

When all six of those are true, the spreadsheet can be retired. Until then it
stays, and it is cheap insurance.

---

## The decisions still outstanding

Four things nobody has settled, none of which are technical.

The prototype gate route is invented, because no real one has been defined.
The post-launch problem metric needs a denominator — per project, per part, or
per million shipped — and those give very different answers. Whether the
intake form can push rows in directly rather than being retyped. And whether
the problem report counts can be pulled from the system that already holds
them.

None of these block go-live. All of them should be decided by somebody who
owns the process rather than by default, which is what happens when a question
is never explicitly asked.
