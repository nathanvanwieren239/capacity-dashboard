# The conversation with IT

*There are two of them, and running them in the right order matters more than
anything you say in either. Written to be read aloud.*

---

## The mistake worth avoiding first

The obvious plan is to get the plant manager's buy-in and then go to IT with a
mandate. That instinct is right about the mandate and wrong about the order.

You need to know what is possible *before* you promise anybody a date.
Otherwise you commit to something the infrastructure cannot support, and you
find out afterwards, in front of the person you committed to.

So there are two conversations. The first is deliberately not a request — it
is fifteen minutes of finding out what the constraints are. The second, after
the plant manager has said yes, is the actual ask, and it is far stronger for
having a name attached to it.

That sequencing does something else worth noticing. Coming back a second time,
having done what you said you would do, is how a working relationship starts.
The first conversation is as much about establishing that you are somebody who
checks before committing as it is about the answers.

---

## Who you are actually talking to, and what they are worried about

This is the part most engineers get wrong, so it deserves real attention.

When somebody from the business arrives at IT with a tool they built, the
default reaction is not obstruction. It is pattern recognition, and the
pattern is a genuinely bad one that most IT departments have lived through
more than once.

It goes like this. A capable person in operations builds something useful. It
solves a real problem, so people start using it. Over a year or two it becomes
load-bearing — a process depends on it, then a department, then a report that
goes upward. It was never documented, because it never needed to be. It runs
on a machine nobody catalogued. Its data was never backed up, because backups
were not part of the original weekend project. Then that person changes roles
or leaves, and IT inherits an undocumented, unsupported, business-critical
system they had no part in creating and cannot maintain.

That is what is being quietly assessed. Not whether the tool is good. Whether
it becomes their problem in eighteen months.

Once you understand that, the strategy becomes obvious: demonstrate quickly
and concretely that you are not that story. And you are unusually well placed
to, because it happens to be true. The tool is documented. The backups exist
and have been restored from. The domain model is written down and verified
against the real process. There is a handoff document. The storage layer is
isolated so it could be moved to a corporate database without a rewrite. And
every real part number was replaced with an invented one before anything went
to a public host.

Lead with that. Not as a list of credentials, but as a frame: *I know what
this could turn into, and here is what I have already done so it does not.*

That single move converts a request for permission into a conversation between
two people managing the same risk.

---

## The first conversation: fifteen minutes, no ask

Open by removing the need for a decision. Something close to:

*I am not asking you for anything today. I want to sanity-check something
before I take it further. You know the launch tracker spreadsheet the plants
use — the one that locks up during the monthly reviews? We have got that data
into a small internal web tool and it is working. Before I show it to the
plant manager I want to understand what it would actually take to run it here,
so I do not promise him something unrealistic.*

Four things happen in that paragraph. No decision is required. A problem he may
already know about gets named. The launch engineer gets credited, which
matters because word travels. And you have signalled that you check with him
*before* committing rather than after.

Then describe the shape rather than the technology.

*It is genuinely small — one process, one data file. No database server, no
licences, nothing to buy. It makes no outbound network calls. It would need to
be on the internal network because the real data has customer names and part
numbers in it, which is why the version I have been testing on is entirely
invented data.*

That last clause pre-empts the security question by answering it before it is
asked, which is the highest-leverage sentence available to you.

### The five questions

Ask them as questions and write the answers down where he can see you doing it.

First: if something like this were going to run here, what is the normal way —
is there a virtual machine platform or a container setup you would want me
targeting?

Second: whatever that is, how does backup work for it? Can an application's
data folder be included, or should I be writing copies to a share that is
already covered?

Third: is there single sign-on that can sit in front of an internal web
application? About six people need to make changes; everyone else only needs
to look. What I care about is that the audit trail records which *person*
changed a date rather than just which role.

Fourth: what is the expectation on patching — do you handle the operating
system while I handle the application, or would you want a different split?

Fifth, and the one that matters most: if this ended up being used by three
plants, what would you want to see from me before you would be comfortable
with that?

That fifth question converts a gatekeeper into an advisor. His answer is your
actual specification for what "ready" means in this organisation, in his own
words, given to you before you have failed to meet any of it.

### Say the sentence

Work it in naturally, but say it out loud:

*One thing I would flag now, because it is how these usually go wrong — if it
ends up containerised, the data folder has to be on a mounted volume rather
than inside the container. Otherwise a redeploy wipes it silently and nobody
notices for weeks.*

Volunteering that, unprompted, is worth more than any credential. It is the
specific thing that tells an infrastructure person you have seen this before
and you are not going to be their problem.

### Close by setting up the next conversation

*I am showing the plant manager in the next week or two. If he wants it, can I
come back to you with what he has asked for and we will work out what is
realistic?*

He will say yes. It costs him nothing and it is how he would want to be
treated.

### Three things not to do

**Do not ask for a server.** You do not yet know what you need, because the
plant manager has not said what he wants.

**Do not mention the president.** Not in this conversation. Using executive
weight in a fact-finding exercise is a threat whether you intend it that way or
not, and you cannot take it back. It will land far better later as *the plant
manager wants this, and it has visibility above him* than as an opening move.

**Do not demo unless he asks.** If he asks, absolutely show him. But
volunteering one turns a five-minute constraint check into a thirty-minute
evaluation, and evaluation is what you want happening after there is a
mandate.

---

## The second conversation: the actual ask

Now you have a name attached and a rough date. Ask for everything at once
rather than returning three times — sponsorship is most useful early, before
the project becomes routine.

**A place to run it.** Small, internal, whatever platform they already use.

**Storage that genuinely persists.** Say the mounted-volume sentence again,
even though you said it last time. It is the failure that is silent and total,
and repetition costs nothing.

**A backup destination away from the machine.** Either the data folder gets
included in whatever regime already exists, or a network path to mirror
snapshots to. Make clear what you are *not* asking for: the application
already snapshots itself hourly, verifies each snapshot's integrity, and has a
restore that has been performed rather than assumed. The only missing piece is
somewhere off the box to put copies.

**Identity, for six people.** Framed narrowly, because narrow asks get
answered. Everyone else stays on a shared read-only password.

**One named person** who knows how it is deployed and could restart or restore
it. This is the honest answer to the concern he had in the first conversation
without ever saying it — that the tool depends on one individual. Asking makes
IT a stakeholder rather than a landlord, which is worth more over two years
than any technical point.

And concede visibly on everything else. Deployment method, machine naming,
patching, monitoring, proxies — that is genuinely their expertise. Deferring
on what you do not care about is what earns standing on the two things you do:
storage that persists, and backups that exist somewhere else.

---

## Objections, and honest answers

**"We don't support Python."**

You are not asking them to. It runs as a self-contained environment with its
dependencies pinned. If their policy is that they patch the operating system
and you patch the application, that works — say so and mean it. What you are
asking them to support is a virtual machine, which they already know how to
do.

**"Why not Power BI? We already have it."**

A fair question deserving a real answer rather than a deflection. Power BI
reads data and displays it, and is very good at that. It does not do data
entry. The whole point of this tool is that people record gate dates in it —
which is what makes it the system of record rather than a report. Getting
write-back in that stack means adding a Power App and a proper back end, which
is licences, a different skill set, and a considerably larger project.

Then offer the constructive version, because it is genuinely a good idea:
these are not competing. This handles entry and editing; Power BI could read
the same database for executive reporting. That answer shows you have thought
about their platform rather than ignored it, and it gives them somewhere to
put their expertise.

**"Can't you just add your own user accounts?"**

You can, and for six people it is an afternoon's work. The reason not to is
not password security — it is offboarding. When somebody leaves or changes
roles, IT disables their network account and nobody tells the person
maintaining a separate list. That account keeps working, and a former employee
retains edit access until somebody remembers the tool exists.

Two smaller costs: you become the password reset desk permanently, and people
reuse their network password, which means you end up storing a hash of a
corporate credential.

If single sign-on is difficult, named accounts are a perfectly reasonable
interim — but then the thing to agree is a way of being told when somebody
leaves. That, rather than password strength, is the actual risk.

**"This should go through a proper project process."**

Sometimes true, often reflexive. Counter with scale, made concrete: smaller
than most departmental file shares, nothing to buy, nothing to license,
nothing to integrate, no data leaving the building.

But phrase it as a question rather than an argument: *is there a lightweight
path for something this size, or does everything go the same route?* That
gives him room to offer the smaller option rather than having to defend the
larger one.

**"What happens when you move on?"**

The most legitimate question you will be asked, and the one to be most
prepared for, because it is exactly the pattern being matched against.

Three parts. There is a handoff document covering the architecture, the domain
model, and the decisions with their reasoning. The data exports to plain CSV
files readable by anything, with or without this application ever running
again. And the storage is isolated to a single module specifically so the
whole thing could be repointed at a corporate database without touching
anything else.

None of that makes you replaceable. It makes the *data* survivable without
you, which is the actual concern.

**"Is the data sensitive?"**

Yes — customer names, part numbers, launch schedules, sales figures. That is
precisely why you are having this conversation rather than leaving it on a
public host. Volunteering that is much stronger than conceding it.

**"We'd need a security review."**

Say yes and mean it, then make it easy. No outbound network calls. No external
runtime dependencies. No stored credentials beyond a configuration file. Meant
to sit entirely inside the network. If they want it behind single sign-on,
that is something you *want*, not something you are tolerating.

**"Who supports it if it breaks?"**

Be honest: you do, for now. Do not oversell. But define the terms — a two-hour
outage does not matter here. If it is down, people use yesterday's export for a
day. It is business-useful rather than business-critical, and saying so
yourself lowers the perceived risk and buys credibility for the claims you do
make.

---

## On governance, and the advice that reversed

There was earlier thinking that the right approach was to work with one
contact and avoid pulling in the wider IT organisation, because broader
involvement could add months. For a departmental tool proving itself, that was
sound.

With an executive sponsor it inverts, and it is worth understanding why rather
than simply reversing.

A tool that quietly avoided governance is a manageable irregularity while
nobody important is watching. The same tool, with executive backing, holding
the company's launch records across three plants, becomes something much worse
the moment anything goes wrong: *the president's system that IT never
approved*. That converts every future problem — an outage, a data question, a
security review — into a political event rather than a technical one. And it
puts your contact in the position of having been circumvented on something
highly visible.

So: still make him your primary contact and your ally, but ask him what the
*proper* route is for something with this sponsorship and scope, rather than
asking him to keep it quiet. Asked in those terms, the question is a gift — it
lets him bring his own department along rather than carrying an exception on
your behalf.

Executive sponsorship is precisely the thing that makes governance fast. A
request that would sit in a queue for a quarter gets attention when it has a
sponsor. Trade two weeks of process for being unambiguously sanctioned.

---

## If the answer is slow, or no

Have the fallback ready before you need it, and mention it lightly rather than
as leverage.

It runs on a laptop. A review can be conducted by screen share. That is not a
good permanent arrangement — the data would live on one machine and only one
person could edit it — but it means nothing is blocked while infrastructure is
arranged, and it lets you say *we can start getting value from this either
way* without any edge in your voice.

That sentence removes the urgency that makes people defensive. A request that
must be answered this week gets resisted. A request that would be nice to
answer this month gets considered.

And a genuine no is information rather than defeat. If internal hosting is not
available at all, the real conversation is a different one — probably about
the Microsoft platform they already run — and it is much better to learn that
in week one than in month six.

---

## What a good outcome looks like

You are not trying to leave the room with a server. You are trying to leave
with three things: a named next step with a date on it however small,
somewhere to put backups even if it is only a network folder today, and an
understanding of what this would need to satisfy in order to grow — so that
when it does grow, you are building toward it rather than retrofitting.

Get those three and the conversation succeeded, regardless of whether anything
was provisioned that day.

One last thing worth holding onto. This is not a transaction. It is the first
conversation in what will probably be a long working relationship. The tool
will need things later — data from other systems, a proper identity
arrangement, perhaps a move to a corporate database. How this goes determines
how easy every one of those is.

Being the person who arrived prepared, asked narrowly, deferred on their
territory, and then did exactly what they said they would do is worth
considerably more over two years than winning any particular point in the
first meeting.
