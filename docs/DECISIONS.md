# Decisions

The owner's product decisions for Where Councils Stand, each with its reason. They take precedence over the other
documents in this repository. Code and docs refer to them by number ("decision 9"), so numbers are never reused; a
new decision is added at the end, and one that replaces another says so.

## 1. Name and owner

The site is called Where Councils Stand. It is a Where They Stand project with its own domain, and is listed under
"In development" in the charity's application to the Charity Commission.

## 2. Coverage

Principal councils across the UK (England, Wales, Scotland and Northern Ireland) whose minutes are published
through Civica's Modern.gov or CMIS, or Northgate's CoINS, and England's strategic authorities (decision 17).
Councils on other systems are left out until there is a reader for them, and the councils page gives the reason.
A site that refuses the crawler is asked for permission, never worked around (robots.txt: decision 21).

## 3. Meetings

Full council and cabinet (or executive), including annual, budget and extraordinary council meetings, and a mayor
and cabinet. Not cabinet sub-committees, advisory panels or decisions by individual cabinet members. A council run
under a committee system has no cabinet, so its record takes the committees its constitution gives the main policy
and budget decisions, usually a policy and resources committee (`committees.py`, and `data_static/committees.csv`
where a council names them otherwise). A council that changed systems keeps whichever committees it had at the
time.

## 4. How far back

May 2018 for every council, so that coverage is even. Each council's page shows its own coverage dates. Extending
back to 25 February 2014, when English councils had to start recording named budget votes, is the next step being
considered; [`PILOT.md`](PILOT.md), "Back to February 2014", says what it would add.

## 5. First users

Independent journalists and engaged members of the public.

## 6. Code

A new repository, adapted from Where Countries Stand's and Where MPs Stand's code under the same licence. Code
shared by the Where They Stand sites now comes from wts-core (decision 24).

## 7. Neutral wording

The charity's impartiality policy applies. Minutes are summaries written by council officers, so briefings say
"the minutes record that…" and never present a summary as a councillor's own words.

## 8. Party on the date

Each councillor is shown with the party recorded at that meeting, mapped to one code per party. Named local groups
of independents or residents are local parties, not "Independent".

## 9. People named in council records

Briefings and pages are limited to councillors' own words and actions. Members of the public (speakers,
petitioners, planning applicants and objectors) and council staff are not identified, and licensing hearings are
not included. There is a published route for taking things down.

## 10. Reuse

Facts (votes, attendance, declarations, decisions) are extracted and published. Minutes are indexed in full, but
shown only as cited extracts linking to the council's own record, because they remain each council's copyright.
Each council's licence statement is to be recorded in the registry (not yet done).

## 11. Being a good citizen

One request at a time to each council, at least a second apart, with a user agent that names the site. Responses
are cached, so each meeting is fetched once.

## 12. Grouping evidence

Briefings group councils by facts recorded on the date, the same way for every party: by default by the party in
overall control (a party with more than half the members at full council) or no overall control; by region, kind
of council or council when asked. Evidence is drawn from each group in turn, at most two items from any council.

## 13. Default period

Briefings cover the last four years (the current council term) by default, with an obvious control to widen the
period back to May 2018.

## 14. Models

As on the sister sites: Claude Sonnet 5.5 writes briefings and Claude Haiku 5.5 reads the question into filters,
with server-side fallbacks on.

## 15. Vote accuracy in the alpha

Decided 6 November 2026: about 1 named vote in 100 with a councillor on the wrong side (three samples of 100,
[`PILOT.md`](PILOT.md)) is accepted for the alpha. The methodology page says so plainly, with the figures. A test set
of checked votes is built before the beta.

## 16. The mark

A town hall (clock tower, pediment, four columns and a gilt step) on a rounded Buckram-brown tile with a fine gilt
edge, drawn in the manner of Where MPs Stand's mark. It was chosen on 6 November 2026 from seven drawings, and must
stay distinct from Where Landlords Stand's mark. [`DESIGN.md`](DESIGN.md), "The mark", describes it.

## 17. Strategic authorities

Decided 6 November 2026: England's strategic authorities (the English Devolution and Community Empowerment Act
2026's term for combined authorities, combined county authorities and the Greater London Authority) are covered,
called "strategic authorities" on the site, with each one's statutory kind on its page. All 20 that exist are
covered: 16 through Modern.gov (Lancashire's, Sussex and Brighton's and Cheshire and Warrington's on a council's
Modern.gov site), and Tees Valley, Hull and East Yorkshire, Cumbria, and Hampshire and the Solent through a reader
of their own websites (`sources/docsite.py`). An authority created later is listed, with the reason it isn't yet
read, and added when it can be.

Each is keyed by its ONS `E47` code. The Greater London Authority has none, so it uses London's region code,
`E12000007`, and the authorities created in 2026 use a stated provisional key until ONS publishes one. Each
authority's page and its constituent councils' pages link to each other, with dates
(`data_static/strategic_authorities.csv`, `authority_councils.csv` and `mayors.csv`).

## 18. Strategic authorities' meetings

The authority's main board or cabinet, including budget meetings; the mayor's decisions, where they are published
as decisions in its meetings system; and its overview and scrutiny committees. From May 2018 or the authority's
creation, whichever is later. They are chosen per authority in `data_static/committees.csv`, with the reason for
each (`committees.py` has the rules). Not audit, standards, appointments, advisory boards, joint committees with
other bodies or police and crime panels.

## 19. Control of a strategic authority, and briefings

Strategic authorities are in briefings. For one with a mayor, "control" is the mayor's party on the date, always
labelled as the mayor's ("mayor: Labour", "authorities with a Labour mayor") and never mixed with councils' party in
overall control, because a mayoral authority can decide nothing without its mayor. One without a mayor (or between
mayors) is "no single party": its members are appointed by its constituent councils, each with the same say, so no
party has control. Filters: nation England, the region it sits in (Greater Lincolnshire spans two and is placed in
the East Midlands, where most of its people live), and the kind "strategic authority". A briefing's balance treats
an authority as one body: at most two items from each.

## 20. Strategic authorities' members

Board and committee members are shown with their role (the mayor, constituent member, non-constituent member,
substitute, co-opted member) and their party on the date from their home council's record where the site has it,
otherwise from the authority's own record, saying which. Only councillors, London Assembly members and the mayor
are named: Assembly members are elected, so they are named as councillors are, with the GLA's record of their
party. Appointed members who aren't councillors (business board chairs, independent and co-opted members) are
counted but not named, and their names are removed from the minutes, as decision 9 does for everyone who isn't a
councillor.

## 21. Robots.txt

Decided 6 November 2026: robots.txt isn't treated as a barrier to councils' and authorities' public records,
because a blanket barrier to open data is unreasonable. `[robots] obey` in `config/settings.toml` is off, so no
reader obeys robots.txt's rules; the setting and the code that obeys them are kept and tested. Whatever the setting,
any `Crawl-delay` a site asks for is honoured, the crawler names itself, requests are one at a time at least a
second apart, and a site that refuses requests (a 403, a bot check) is asked, never worked around. A council marked
`robots` in the registry by hand is not read, and anything stored for it is kept but withheld. No letters are sent
about robots.txt.

## 22. Corrections and the right of reply

The charity's corrections and right-of-reply policy (impartiality policy, section 7) is built into the site, in
the family's words (the charity's glossary).

An "If you're named" page (`/named`, linked from the corrections and About pages) serves
councillors (mayors and London Assembly members included), councils and strategic authorities, and anyone acting
for them. It sets out three routes: "Something is wrong" and "You've been characterised unfairly" through the report
form (`/corrections?kind=error`, `?kind=unfair`), and "Add a statement in your own words" through its own form
(`?kind=statement`). Members of the public have the takedown route (`?kind=takedown`), which is dealt with first.

Corrections cover the site's labels, groupings and connections as well as briefings: a councillor's party on the
date, which side of a named vote they're shown on, a council's control and an authority's mayor's party, members by
party, an authority member's role and home-council party, the links between authorities and their councils and to
Where Landlords Stand, coverage labels, and how briefings group councils. The corrections page and the named page
say: "We reply within 5 working days, and decide within 20 working days."

A statement (policy 7.2) is up to 150 words, with the author's name and role, about one item (a council's page, a
named vote or a saved briefing), with an optional link to the record and an email address to confirm who sent it.
It waits until the owner has confirmed the sender, and is then published as written or declined with reasons; its
author can have it updated or withdrawn at any time ([`OPERATIONS.md`](OPERATIONS.md), "Statements under the right of
reply"). It is shown after its item and on the council's page, headed "Statement from [name], [date]" and followed
by "In their own words. Not checked or endorsed by Where Councils Stand.", in a panel set apart from the record.
Councillors have no pages of their own, so a councillor's statement goes beside a vote, a briefing or their
council's page, and is gathered on the council's page.

Statements are never part of the record: never given to the AI model, never in the search index, a page's
description or its structured data, and the code that builds the record and briefings doesn't read the site's own
database. The confirming address is kept while a statement is waiting or shown, and deleted three months after it
is withdrawn, declined or removed, as the privacy notice says.

## 23. Briefings compared with a general AI chatbot

Decided 13 November 2026: readers are told plainly why the site's briefings are more reliable than a general AI
chatbot's, in the family's words (the charity's glossary, "AI briefings"). On the home page, beside the question box,
one line is always shown, with a disclosure, "How the briefings are checked", that opens to five short points and a
link to the methodology. The About and methodology pages give all seven points at more length, from one file
(`web/partials/why.html`). No product or company is named, and nothing is said about what others get wrong.

Every claim must be true of this site's code and settings, and is checked again before it is changed: the model is
given only the record (rule 1 of the instructions in `rag/prompts.py`; `rag/answer.py` sends only the passages found
and the question); citations and quotations are checked (wts-core's checks, with this site's rules in
`rag/checks.py`); minutes are read every day (`deploy/councils-update.timer`); "No records found" (`rag/pipeline.py`,
`rag/prompts.py`); evidence from councils run by different parties (`rank/evidence.py`, decision 12); from May 2018
(`config/settings.toml`, decision 4); open, free and without tracking (the methodology, terms and privacy pages).
Nothing is counted when the disclosure is opened.

## 24. The shared package, the corrections log, and hiding a page

Decided 14 November 2026: the site runs on wts-core, the Where They Stand sites' shared package, installed as the
wheel of a tagged release with its `cli`, `offsite` and `ai` extras. wts-core provides the settings loader, the
state database and its backups, limits and spending, the answer cache and saved briefings, the flow of a question,
the checks on briefings, reports and statements, the model client, the embedders and the search index's store. What
stays in this repository is the councils' record and how it is read, the search and its balance across councils,
the instructions to the model, the words on every page and in every message, the limits and prices
(`config/settings.toml`), and this site's honorifics, evidence-note rule and list of loaded words (`rag/checks.py`).

Readers saw no change from the move except the two additions below, and the parity tests hold the site to what its
own code gave before (`tests/golden/`, `tests/test_parity.py`). The checks on briefings never weaken. The state
database's rows were carried over once, with a way back until 1 February 2027
([`OPERATIONS.md`](OPERATIONS.md), "The move onto wts-core, and going back").

The site gains two things the impartiality policy (section 7) asks for:

- A public corrections log, on the corrections page and at `/api/corrections`: each withdrawn briefing with the
  reason given, and each report closed with a note written for the log, newest first. It never shows a withdrawn
  briefing's question (it may name someone who isn't a councillor), anything a reporter wrote, or why a statement
  was removed.
- Hiding a page while a concern is decided (policy 7.3, which the "If you're named" page promises): a named vote, a
  council's or authority's page, or a saved briefing can be hidden, with a note in its place, and is left out of
  lists, the sitemap, search and the sources of briefings written meanwhile ([`OPERATIONS.md`](OPERATIONS.md),
  "Hiding a page").

For the owner, the site also gains a record of each briefing (how it ended, how long it took, what it cost, what
the checks found; nothing that identifies a reader; kept 13 months), `councils stats`, a weekly report with alert
thresholds that start unset, the nightly `councils tidy`, `councils restore`, `councils eval`, and `/api/check` for
the family's nightly check. The privacy notice says what each keeps. The site keeps no separate note of failed
questions, counts no reader's reports or statements, and sends no token counts to the reader.

## 25. wts-core 0.3.0

Decided 16 November 2026: the site moves from its old code straight to wts-core 0.3.0. Readers see no change
(`tests/golden/`, `tests/test_parity.py`), and no sentence of the privacy notice changes. What is kept narrows,
within what the notice already says: a spending row keeps which visitor it was for, and at what time, for its own
day only; the record of each briefing keeps only the hour; and the nightly tidy and backup delete what is due even
on a night when nobody asks anything. Going back to the old code without the undo script is noticed, and the new
code refuses to start until it is mended ([`OPERATIONS.md`](OPERATIONS.md), "Going back, and coming forward
again").

## 26. Every point to check is marked

Decided 13 November 2026: every result of the checks that a reader should see is shown. Text whose citations all
failed the check against the minutes is marked as unsupported text is, with "Not supported by a cited source", and
the notice under the briefing says a citation failed and was removed. A quotation not found word for word in the
minutes cited for it is marked with a wavy amber line and "Not found word for word in the minutes cited for it",
screen readers are told the same straight after it, and a notice under the briefing says how many there are. The
methodology page says so, and the accessibility check (`scripts/a11y.mjs`) fails if a point to check is not marked
or explained. The same fix is made on the sister sites. Readers see more passages and quotations marked, never
fewer.

## 27. A council's control is not a speaker's party

Decided 19 November 2026: the owner decided that briefings show both a council's control and the party of whoever
made, moved or proposed each point, so that a point is never attributed to the party in control when someone of
another party made it. An audit had found a remark by Doncaster's directly elected Labour mayor about a Section 114
notice under a heading of Reform UK control. Grouping and balance stay as decision 12 has them; the labelling changes.
Each source's title gives the council's control and each councillor the passage names with their own party on the
date, marked "not the party in control" where it is another party (at a strategic authority, "not the mayor's
party"); where the council has a directly elected mayor and the passage speaks of a mayor, the title gives the mayor
and their party too. The instructions (rule 12) forbid presenting a point as the controlling party's unless its
speaker belongs to that party, and grouping by control names each council's control and, where they differ, the
speaker's or the mayor's party ("Barchester (Reform UK control; directly elected mayor: Labour)"). The list of
sources gives the people in each passage with their party under the group's heading, and the methodology page says
so. The site holds no list of councils' elected mayors: one is read from the council's own attendance lists (an
elected, executive or city mayor's title, or "Mayor" and a name at a cabinet meeting), so a mayor whom a council's
lists don't title as such is not given, and "the Mayor" alone in minutes is not taken to be them, since a council
may also have a civic mayor. Briefings written under the earlier instructions are not served again (instructions
version 4).

## 28. What a named vote is called

Decided 19 November 2026, at the owner's request after an audit of how search engines read the site: each named
vote's page has a title, heading and description of its own. Many agenda items hold several named votes (a budget
and its amendments), and every one of them had the item's title, so search engines treated them as copies of one
page and showed only one. A vote's label says what it was on, in the minutes' own terms ("Amendment 7", "Amendments
3 and 5", "Amendment by Cllr Webb", "Substantive motion"), read as the page is served from the words just before the
vote in the item's minutes, or in its stored extract where the minutes can't be matched (`api/titles.py`). It is read
only where those words say so plainly; otherwise the vote is called by its place, "Vote 2 of 4 on this item", and
two votes on one item never share a label. A vote alone on its item has no label unless it says more than the
item's title (an amendment, a substantive motion). Who moved an amendment is named only if they are a councillor at
that council and nothing the rules of decision 9 remove is in the label. The title gives the label, the result and
count (left out where the result the minutes give contradicts the count), the item, the council and the date in
about 70 characters, an item in capitals in sentence case; a budget or council tax item's single vote is "How
councillors voted: …". Nothing in the record changes, and the site still gives no amounts of council tax.

## 29. Rebuilding the search index waits for the server's update lock

Decided 21 November 2026, in the review of that day (A2 in the charity's review plan): `councils index` and
`councils embed`, which both write the search index's state file, take the server's update lock, `/var/lock/wheretheystand-update.lock`, before it writes anything, as every site's nightly
update does. On 19 and 20 November an index run by hand and the nightly update ran together for ten hours, and both
wrote the search index's state file. Like the update, it waits for the lock rather than fail: it says it is waiting,
what holds the lock and how to see who, and carries on by itself when the lock is free, so that an index run the same
day as a suppression (decision 9) still happens without anyone coming back to start it. It does not wait when the
lock cannot be opened at all: in the server's containers the lock is the server's file, mounted read-only by
`deploy/docker-compose.yml`, and if it is missing the command does nothing and exits 1, saying how to put it right,
rather than run unguarded. On a developer's machine with no `/var/lock`, it runs without a lock.
