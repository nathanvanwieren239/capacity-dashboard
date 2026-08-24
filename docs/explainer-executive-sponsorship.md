# What changes when the president is the sponsor

*An addendum to the go-live planning, written after the decision to launch
under the company president across the three Michigan buildings rather than
as a departmental tool for one launch engineer. Intended to be read aloud.*

---

## The short version

Almost everything about the technology stays the same. Almost everything about
how you should behave changes.

Up to now this has been a good tool built by a capable engineer for a
colleague who wanted it. That is a low-stakes arrangement. If it had failed,
two people would have shrugged and gone back to the spreadsheet.

Sponsored by the president, across three plants, holding the authoritative
record of every launch — that is a different object entirely. Not because the
code changed, but because the consequences of it being wrong now travel
upward, and because a much wider group of people are about to form opinions
about it.

The good news is that the technical work already done is proportionate to the
new stakes. Real transactions, tested restores, an audit trail, a documented
domain model. None of that was over-engineering; it turns out to have been
exactly right for where this is going.

The work that remains is almost entirely about people, sequencing and
expectations.

---

## The advice that just inverted

Earlier the guidance was to work with a single IT contact and avoid pulling in
the wider organisation, on the reasoning that broader involvement could add
months. For a departmental tool trying to prove itself, that was sound.

With the president sponsoring it, that advice is now actively dangerous, and
it is worth understanding why rather than just reversing course.

A tool that quietly avoided IT governance is a manageable irregularity when
nobody important is watching. The same tool, with executive backing, holding
the company's launch records across three plants, becomes something much worse
the moment anything goes wrong: *the president's system that IT never
approved*. That is the worst possible position to occupy. It converts every
future problem — an outage, a data question, a security review — into a
political event rather than a technical one, and it puts your IT contact in
the position of having been circumvented on something highly visible.

The inversion is this. You previously wanted to stay small enough to avoid
process. You now want the process, because you can afford it and you need the
legitimacy it confers.

Executive sponsorship is precisely the thing that makes governance fast. A
request that would have sat in a queue for a quarter gets attention when it
has a sponsor. Use that. Go through the front door, ask what the proper route
is, and let it be slower by two weeks in exchange for being unambiguously
sanctioned.

Concretely: still make Chambers your primary contact and your ally, but ask
him explicitly what the right process is for something with this sponsorship
and this scope, rather than asking him to keep it quiet. That question — asked
in those terms — is also a gift to him. It lets him bring his own department
along rather than carrying an exception on your behalf.

---

## The bar goes up, in four specific places

**Availability.** A departmental tool that is down for a morning is an
inconvenience. A system of record for three plants that is down during a
review, with the president's name attached, is a visible failure. It does not
need to be highly available in any formal sense — this is not a production
line — but somebody other than you needs to be able to restart it, and there
needs to be an obvious answer to "what do we do if it is down." The honest
answer is probably "use yesterday's export and re-enter" — but that answer
should exist, be written down, and be understood before it is needed rather
than improvised on the day.

**Data loss tolerance.** It was already near zero once this became the source
of truth. Executive visibility does not change the technical requirement, but
it changes who finds out. Hourly snapshots and an off-machine copy stop being
prudent and start being the minimum defensible position.

**Support.** "Nathan, when he has time" is not a support model for something
the president sponsors. This does not mean you need a team. It means the
arrangement needs to be explicit: who to contact, what the response
expectation is, and what happens when you are on holiday. Writing that down —
even if the answer is modest — is what separates a system from a favour.

**Accountability in the audit trail.** This is the one that changes most.
Shared role passwords were an acceptable development shortcut when the
audience was two people who trusted each other. Once the president is looking
at on-time percentages, those numbers evaluate people, and the ability to say
*this person changed this date on this day* stops being a nice-to-have. Single
sign-on moves from the wish list to something worth asking for directly, and
executive sponsorship is exactly the leverage that gets it.

---

## The metrics just became political

This deserves its own section because it is the most likely thing to go wrong,
and it has nothing to do with software.

The dashboard computes on-time gate reviews, on-time launches, and problem
reports in the first year after production starts. Until now those numbers
were interesting. The moment a president looks at them, they evaluate
somebody.

Two consequences follow immediately.

**The definitions must be agreed before anyone is measured, not after.** The
tool deliberately shows on-time two ways: against the adjusted date, and
against the date originally committed. On the demonstration data those differ
by seventeen points. That gap is genuinely informative — it is the share of
the on-time record that depends on dates having been moved — but it is also
exactly the kind of number that starts an argument if it appears unannounced
in front of an executive. Decide with Ryan and Lothian which is the headline,
what the other one is for, and be able to explain both in one sentence each.

**Somebody will be measured badly by a number that is wrong.** Not
maliciously — through a data entry error, a project that was legitimately
rescheduled, a gate that was closed but not recorded. When that happens, the
first instinct will be to blame the tool, and the tool's credibility is at its
most fragile in the first quarter.

The defence is the audit log and the parallel run. Being able to show exactly
who changed what and when turns a dispute into a lookup. Having run alongside
the spreadsheet for a cycle means you can point at agreement rather than
argue about it.

Run in parallel for at least one full monthly cycle at every plant before
anyone's numbers are reported upward. This was previously advisable. It is now
the single most important item on the list.

---

## Sequencing, and the thing to be careful about

There is an interpersonal risk here worth naming plainly.

Ryan has been the collaborator on this from the beginning. He shaped the gate
model, corrected the design, and gave you the process knowledge that makes it
correct. Lothian was the intended reviewer. If this arrives at the president
without them having been brought along first, it can very easily read as
having been gone around — regardless of intent, and regardless of the fact
that the president is your own manager.

That is a relationship you cannot afford to damage, both because Ryan is the
person who makes the tool correct and because his goodwill is what gets it
adopted at plant level. Executive mandate can compel use; it cannot compel
enthusiasm, and a tracker that people resent gets filled in badly.

The sequence that protects everyone: show Ryan first, and show him
specifically as the person whose input built it. Then Lothian, who runs the
two plants already using the tracker. Then the president, ideally with the
prior conversations mentioned. Framing it as *Ryan and I have got this to a
point where it is worth showing you* costs nothing and changes how it lands
for everyone.

If the president has already asked to see it and the sequencing is not fully
in your control, then at minimum tell Ryan before the meeting rather than
after. A short message is enough. Being surprised is what causes the damage,
not the meeting itself.

---

## Three buildings, not one

The scope change has a few practical consequences worth thinking through.

**Which three, exactly.** The tool currently carries four sites, one of which
is in Massachusetts. The Michigan set needs confirming and configuring, and
the plant list should match reality on day one — an executive noticing a wrong
plant name in the first five minutes costs more credibility than the error
deserves.

**Three plants means more editors.** Concurrency has been tested and handles
correctly, but the practical question is who edits what. If each plant has its
own person entering gate dates, and one person oversees all three, the
permission model needs to reflect that. Today there are two roles, and neither
is scoped by plant. That is probably fine to start and worth being conscious
of.

**Three plants means the data volume roughly triples**, which is still
negligible. Nothing to worry about technically. But it does mean the import is
larger, and the first import is where errors are most likely.

**Consider a staged rollout even under a single mandate.** One plant for a
cycle, then all three, is much easier to recover from than three at once. It
also gives you a genuine success to point at before the wider audience forms
its opinion. If the president wants all three immediately, that is their call
— but offering the staged version yourself demonstrates judgement, and it is
usually accepted.

---

## What to ask for now that you can

Executive sponsorship is a resource with a short half-life. It is at its most
useful in the first few weeks, before the project becomes routine. Spend it
deliberately.

Ask for the hosting and the storage, obviously — but ask for the whole package
while the sponsorship is fresh rather than returning three times.

Ask for single sign-on. It is the thing that most improves the tool's
standing, it is difficult to justify for a departmental utility, and it is
entirely reasonable for a system the president sponsors.

Ask for a second person who can support it. Not a team — one named individual
in IT who knows how it is deployed and could restart or restore it. This is
the single best answer to the bus-factor problem, and it will never be easier
to request than right now. It also, incidentally, makes IT a stakeholder
rather than a landlord, which is worth a great deal over time.

Ask what it would take to be considered a properly supported internal
application, and then either do those things or make a conscious decision not
to. Knowing the standard is valuable even if you do not meet all of it
immediately.

---

## What has not changed

Worth ending here, because the list is short and reassuring.

The technology is sound and was built to a standard that suits this. The
domain model is verified against the real process rather than assumed. The
storage handles concurrent editing correctly. The backups have been restored
from, not merely taken. The whole thing is documented well enough to hand to
somebody else.

None of that needs revisiting because the sponsor changed. The work that
remains is running a parallel cycle, agreeing what the numbers mean, getting
the hosting and identity arrangements right, and bringing the people who built
this with you along before it goes upward.

That is a good position to be in. Most tools that reach an executive have none
of the first list and all of the second still ahead of them.
