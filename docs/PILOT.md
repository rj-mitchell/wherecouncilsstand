# Pilot: 20 councils, May 2018 to October 2026

Run 24 October 2026. It tests whether full council and cabinet minutes from Modern.gov can be loaded and read reliably
enough to build Where Councils Stand on, and what that costs.

## Which councils

The rule (`pilot.py`): from councils whose Modern.gov web service answered, 17 English councils drawn at random in
proportion to the number of English councils of each type, and 3 Welsh councils, with a fixed, published seed
(`20261024`). Party control plays no part.

| Type | Councils |
|---|---|
| District (9) | Chesterfield, Fareham, Folkestone and Hythe, Guildford, Hart, Redditch, Rother, South Oxfordshire, Stratford-on-Avon |
| Unitary (3) | Darlington, Northumberland, Westmorland and Furness |
| Metropolitan (2) | Manchester, Wirral |
| London borough (2) | Lewisham, Sutton |
| County (1) | Staffordshire |
| Welsh unitary (3) | Blaenau Gwent, Bridgend, Neath Port Talbot |

## What was loaded

- **3,349 meetings:** 1,389 full council, 1,848 cabinet, and 112 policy committee meetings. Sutton and Wirral are run
  by committees: Sutton since before 2018, Wirral since 2020, so Wirral has cabinet meetings before its change and
  policy and resources meetings after.
- **37,822 agenda items**, 32,882 of them with minutes text (46 million characters, about 12 million tokens), and
  88,922 attendance records of councillors (staff, guests and members of the public in the lists are not stored).
- **No failures:** every meeting listed was fetched.
- **Time:** councils' servers took 7–24 seconds per meeting. With each council fetched one request at a time, the
  20 ran side by side in 26 minutes. Reloading from the cache takes 30 seconds.
- **Size:** 339 MB of cached responses and 18 MB of Parquet.

### How far back

14 of the 20 councils' records go back to May 2018. Of the six that start later:

- **Westmorland and Furness** was created in April 2023. Its site still holds its predecessors' committees.
- **Hart** starts in May 2020, **Northumberland** in February 2021, **Blaenau Gwent** in October 2019 and
  **Rother** in May 2019: their Modern.gov history begins then.
- **Manchester**, from September 2018, is close enough.

That's slightly behind the earlier survey's 79% for 2018. Each council's page will need to show its own start date
(docs/DECISIONS.md, 4), and the gaps would need another source.

### Minutes text

87% of meetings have minutes. 85% come from the web service's minutes text, and 2% are read from the meeting's
minutes document. By year:

| Year | Meetings | With minutes | Of which read from a document | No minutes found |
|---|---|---|---|---|
| 2018 | 213 | 89% | 0% | 11% |
| 2019 | 356 | 93% | 1% | 7% |
| 2020 | 397 | 80% | 2% | 20% |
| 2021 | 418 | 87% | 1% | 13% |
| 2022 | 407 | 88% | 2% | 12% |
| 2023 | 399 | 92% | 2% | 8% |
| 2024 | 396 | 86% | 5% | 14% |
| 2025 | 431 | 87% | 3% | 13% |
| 2026 | 332 | 79% | 1% | 21% |

- **2020** dips because of remote meetings during Covid.
- **2026** dips because recent minutes aren't approved yet.

**Minutes published only as a document.** A meeting's minutes are attached to the agenda of the committee's next
meeting, at the item that approves them ("02 Minutes 011123" on the January agenda is November's minutes). An
earlier version of this note counted those attachments as the meeting's own minutes, which overstated how many
councils publish minutes only as a document; the table above corrects that.

`sources/documents.py` now finds each meeting's own minutes document by the date in its title, extracts the text and
splits it into the meeting's agenda items. In the pilot this added minutes for 65 meetings: 347 agenda items, plus
36 meetings kept as one whole document where the item titles couldn't be found.

**Most councils on Civica's hosted `moderngov.co.uk` sites refuse documents** to automated requests from the network
this ran on: a browser check answers instead, though the web service itself works. 7 of the 16 councils tested
served documents. The councils with the most meetings still without minutes are all among those that refuse:
Northumberland (96 meetings, since it moved to documents in 2024), Neath Port Talbot (65) and Lewisham (40). Reading
them needs a different network, or the councils' agreement to allow the crawler.

## Named votes

**473 named votes**, with 19,480 names: 11,833 for, 6,743 against and 904 abstaining. **97% of names were matched
to a member.**

- Almost all are from full council (463). Cabinets vote by name very rarely (10).
- 283 of the 473 also record the result (carried or lost) in a form that could be read. The rest give it in ways not
  yet recognised.
- 22 apparent votes were left out because most of their names matched no one: they were lists of appointments or
  other text that looked like a vote.

Councils write named votes in at least nine ways, and the parser now reads all of them:

| Layout | Example | Councils |
|---|---|---|
| Heading and list | "In favour of the Motion: Councillors A, B and C" | most |
| Heading, count and list | "For the Motion (24) – Councillors …" | Darlington, Rother, Wirral |
| Heading without a colon | "Members Voting FOR the Resolutions below Councillors …" | Redditch |
| Count then "namely" | "For the proposal 19 votes (namely, the Chairman, Councillors …)" | Stratford-on-Avon |
| Names before the side | "(Councillors K Barton, … voting in favour and … voting against)" | Fareham |
| Columns of surnames without commas | "FOR – Councillors: Bagley P Gilby P Barr T Gilby …" | Chesterfield |
| A table, one row per member, a mark in a column | "Name / For / Against / Abstain / Absent" | Westmorland and Furness, South Oxfordshire |
| A table, one column per side, the names listed in each cell | "FOR: / AGAINST: / ABSTAIN:" | Guildford |
| Initials joined to surnames | "M.Harvey, S.M.Penry" | Neath Port Talbot |

Sutton records that a named vote was taken, but the names aren't in the minutes text; they're in an attached
document. Elections of a person ("For Councillor Bigmore (19 votes): …") are left out: they aren't votes on a motion.

### How accurate

Three random samples of 15 votes were checked by hand against the minutes, each drawn with a different seed. The
first two found errors, which were fixed. The third was checked before the last fixes:

- **12 of 15 were right, or within one name of right, with every member on the right side.**
- **2 were elections of a person read as votes.** This is now fixed.
- **1 missed one abstainer**, because the list ran into a "(Voting figures …)" note. This is now fixed.

Errors found and fixed along the way:

- the last name of a list lost to the count after it: "Snedker (20)";
- a second column of names put under "abstentions" when the other headings said "None" (Chesterfield). This was
  the one error that put members on the wrong side; such layouts are now left unread rather than guessed;
- typos in headings ("ABTENTIONS", "Againt");
- the same person matched on both sides of a vote: both are now left unmatched;
- "The Mayor" when the attendance list says "The Mayor" rather than "Mayor".

Remaining weaknesses:

- where the minutes themselves run names together without commas ("Graham Liz Grey Grier" in one Wirral vote),
  only one of the names is kept;
- about 3% of names match no member, mostly because older attendance lists are incomplete, or because of
  misspellings in the minutes ("Heighbour" for Neighbour).

### Across all councils

Once about 200 councils were loaded, 50 votes were drawn at random from all of them (seed 2026) and checked by hand
against the minutes. The target was no member on the wrong side. The parser missed it:

| | Votes |
|---|---|
| Right | 23 |
| Within one or two names of right (a name missed, or a stray word such as "MBE" read as a name) | 18 |
| Misread: a list read from the wrong place, a side missed, or an election of a leader read as a vote | 6 |
| **Members on the wrong side** | **3** |

Outcomes were wrong in at least 4 of the 50, where the parser took the result of another question nearby.

The three wrong-side errors:

- **Wirral:** counts first, then one list ("For - 65 Against - 0 Abstentions - 0 Avis, Banks, …"). All 65 were put
  under abstentions.
- **Merton:** a "Not voting:" list read as part of the "against" list before it, putting 7 non-voters against.
- **Harrow:** an "Absent:" list read the same way.

Fixes, each with a test built from the real wording:

- "Not voting", "Absent", "Did not vote" and "Present not voting" now end the list before them.
- A zero count can't have names: names after "Abstentions - 0" go to the side whose count they match, or are left out.
- A list with far more names than its count is left out; it means both lists follow both headings, or the list runs on
  into the text.
- Party block votes ("Labour block vote of 15 votes") are left out: they aren't votes by name.
- Totals after each list ("Those voting FOR – 56") no longer split a vote in two.
- Headings may run up to their colon ("For the Cabinet recommendations to Council as set out in the minutes …:"),
  but not across a verb ("… are recorded as set out below:"), and year ranges ("for 2023-2027") aren't headings.
- A list now ends at a new sentence ("Councillor Gill. The proposed motion therefore FELL."), or at "Motion Carried".
- The result is read from the sentences straight after the names, up to one that moves on to another question. Only
  if there's nothing there is the last result before the vote used.
- One member recorded after the lists is read ("The Lord Mayor abstained from voting."; "Councillor Huntley voted
  against.").
- Roles named with a person count once ("the Deputy Mayor, Councillor Ed Foley"; "His Worshipful the Mayor
  Councillor Salim Chowdhury"). A deputy mayor is no longer matched to the mayor.
- "K Berberi" isn't matched to the only Berberi listed if that member is Mark. Surname-first names ("Barratt R") are
  matched. Honours split from names ("MBE", "J.P.") and counts in square brackets ("[7]") are dropped.

The same 50, parsed again, have no member on the wrong side. Wirral's vote is now left unread rather than guessed.
Oxford's 29 names are read. Lincolnshire's two votes are no longer split into four.

A second sample of 20 (seed 777) found one more wrong-side error. Southend wrote both lists after both headings
("For the Motion (31) Against the Motion (13) Councillors …"), and all 44 were read as against. This is the case that
the count rule above now leaves out. That sample also found Crawley's block votes and a missed "[7]" count.

**A final sample of 20 (seed 4242), drawn after every fix and checked without changing anything:**

- **17 right, 2 within one name, 1 with one side's list missed. No member on the wrong side.** The two near
  misses are the minutes' own slips: "J, Phipps", and a member listed twice. The missed list was "AGAINST the
  Amendment (22). Bayliss, …", with a full stop after the count; this has been fixed since.
- The result was read in 18 of the 20, and was right wherever the minutes give it.

Across the 198 councils loaded at the time, the changes read **6% more named votes** (6,591 to 6,958). They also cut
names matched to no member from 3.3% to 3.0%. Removing names from excerpts had two faults, now fixed. It cut
"McInroy" to "[name removed]Inroy". And it removed a councillor's name when a heading followed it ("Mr Whiting
Against (51)").

20 votes is a small sample. A wrong-side rate under 1 in 20 is all it shows. Before launch, a larger check (100 or
more votes) should confirm the target. Each vote should keep linking to the council's own minutes, so a reader can
check.

### A check of 100 votes, then 100 more

The 20-vote samples above could only show a wrong-side rate under 1 in 20. So once 70 councils of the full load were
in, 100 votes were drawn at random from them (seed 2026, `councils pilot-check --all --n 100`) and checked against
their passages, name by name. The target was still no member on the wrong side.

| First 100 (seed 2026) | Votes |
|---|---|
| Right | about 41 |
| A member missed, or a stray word read as a name | about 35 |
| Not a vote: sponsors of a motion, or a section number read as a count | 4 |
| Only a table's summary in the excerpt, so the names couldn't be checked | 12 |
| **Members on the wrong side** | **9 votes, about 25 members** |

The wrong-side errors had five causes, each now fixed with a test built from the real wording:

- **The side after the names.** "Councillor Gunner voted against the recommendations (1). Councillors Andy Cooper,
  Alison Cooper, and Greenway abstained from voting (3)." (Arun, four votes; Ipswich). The parser gave each side
  word the names after it, so the abstainers went against. Such a side now takes the names before it.
- **A heading that ran on.** "Against the motion None Abstentions Councillor Paul Gray Absent: Councillors Denton, …"
  (Havant) was read as one heading, putting six absent members against. A heading's words now stop at another
  side's words or a name.
- **"Abstentions" with no colon.** "… and Kate Walsh Abstentions Patrick McGinley" (Hyndburn).
- **A table inside a table.** Lincoln's table repeats its names in rows after a cell that holds whole lists, so
  members appeared on both sides. Those rows are skipped, and a table that puts one name in two columns is left out.
- **A count read as names.** "with 46 members voting for" (Bury) gave "for" to the motion's sponsors named before it.

Two safeguards cover what the patterns miss:

- **Counts must agree.** Where the minutes print a count for a side ("(24)", "Total 36", "With 37 in favour and 3
  voting against"), the names read must match it, or the vote is left out. In the check, most of the votes with a
  member on the wrong side printed a count that disagreed with the names read.
- **A vote needs a "for" side** (an empty one, "For: None", is fine). In the check, a missing "for" side always meant
  a list that hadn't been read.

Names run together without a comma ("W Drew A Garratt", "Dorn: Farmer") are now split where each part is a
different member. "The Chair of Council, Councillor Ian Pearson" and "the Mayor of Doncaster, Ros Jones" count as
one member each, and a full stop for a comma ("Holroyd. Howarth") no longer ends a list.

**A fresh 100 (seed 9090, 49 councils), drawn after those fixes:**

| Second 100 (seed 9090) | Votes |
|---|---|
| Right | 60 |
| A member or a side missed, or a stray word | about 20 |
| Only a table's summary in the excerpt | 15 |
| **Members on the wrong side** | **2 votes** |

Both were the side-after-names pattern in words the first fix didn't cover: "Cllrs: A, B, … were in favour. Cllrs:
C, D, … were against" (South Norfolk, 19 members), and "For the Amendment:- S Arif; Brown, Gartside, Harris, Hussain,
voting for; A Arif, … Y Wright voting against" (Bury, 42 members). Both are now read correctly.

The check also found councillors removed from excerpts as if they were members of the public. "Richard Long, TD" and
"Councillor Miss Phillipa Tatham BA (Hons)" gave the surnames "td" and "hons", so the councillor wasn't recognised.
191 of 10,829 attendance names were affected; letters, bracketed words and styles are now passed over.

**A third 100 (seed 31337, 50 councils, 93 of them votes not seen before), drawn after those fixes:**

| Third 100 (seed 31337) | Votes |
|---|---|
| Right | about 75 |
| A member missed, or a stray word | about 14 |
| Only a table's summary in the excerpt | 9 |
| **Members on the wrong side** | **2 votes** |

Durham spelt the heading "Abstenions", so its two abstainers were read as against; this spelling is now read.
Kirklees's passage began with the previous vote's abstentions, which were read as this vote's. That is now caught
by a structural rule rather than a pattern: **a vote that puts one member, or one name, on two sides is left out
entirely.** Every Kirklees vote misread this way had members on two sides. (Before, only that member was unlinked.)

So the rate of votes with a member on the wrong side went from 9 in 100 to 2 in 100, and stayed at 2 in the third
sample, each time from a wording not seen before. Each of those is now fixed or left out. The rules that don't
depend on wording (counts must agree, a "for" side is needed, no member on two sides) would have caught at least 2 of the
4 wrong-side votes in the last two samples (South Norfolk's printed totals, Kirklees's members on two sides). **The target of none is not yet met on an untouched sample**; at this rate
expect about 1 vote in 100 with an error the rules don't catch. Every vote links to the council's own minutes, and the
corrections route covers what slips through.

Across the 88 councils loaded at the time, all these changes read 9.7% fewer named votes (2,489 to 2,248), mostly
votes now left out by the three rules, and cut names matched to no member from 3,034 to 2,520.

**Counts before the lists (November 2026).** A count printed just before a heading ("carried with 55 Members voting
in favour:-", "And 13 Members voting against", "Nine Members voted against", "lost by: 13 votes in favour:") is now
that side's count, and the vote is left out unless it is the number of names read; spelled counts are read
("forty-two"). The next side's count at the end of a list ("Tunnacliffe To 24 votes against") is no longer taken as
part of the last name. Built for Sunderland (CMIS), whose lists were read with most names lost; across the 169
Modern.gov councils stored here it changed 17 items at 9 councils. Most are votes whose names don't add up to the
printed count, now left out (Cambridge, Windsor and Maidenhead, Swale, Bury, and elections of a person at Guildford,
Basingstoke and Three Rivers). Cambridge's lists are now read whole, and Eastbourne gains two votes that add up. In
the 2014–2019 sample, Wirral's 2016 budget votes, two of which had been merged with their sides swapped, are read as
four.

Other faults the checks found, which lose information but don't misplace anyone:

- The result is often missing where the minutes say only "RESOLVED", and twice it was taken from the amendment
  just before.
- Votes between candidates for a post ("Those in favour of Councillor X – 6 …") are read as a vote "for".
- About one vote in seven is a table whose excerpt shows only its summary, so a reader can't check the names on
  the page; the link to the minutes is the check.

## Declarations of interest

**1,116 declarations, 95% matched to a member.** The kind of interest is as the minutes give it: mostly "personal"
(532), then "non-pecuniary", "disclosable pecuniary", "prejudicial" and others; 164 don't say.

15 sampled at random were all attributed to the right councillor with the right kind of interest. One excerpt was cut
short at "Item No.".

Some declarations describe councillors' families in detail. One, for example, mentions a councillor's child receiving
social care. They're published by the council, but they need care when shown. See below.

## Party on the date

Councils use 86 different labels in these 20 councils alone. Many are their own codes: "L" for Labour in Lewisham,
"WLP" for Welsh Labour in Blaenau Gwent, "LC" for the Conservatives in Sutton, "CCH" for Community Campaign (Hart).

`scripts/party_labels.py` learns each council's codes from Open Council Data's annual lists of every councillor's
party. It maps a code only where at least two members are found and at least two-thirds agree, and records the
evidence in `data_static/parties.csv`. Three were decided by hand, with the reason recorded.

**99% of attendance records now have a recognised party.** 20 small labels are left, covering 766 records. Most are
one-member groups or mixed groups ("Independent partnership"), which need a person to decide.

## Privacy findings

- Modern.gov attendance lists include **members of the public and council staff** (roles such as "Public",
  "Officer", "Guest"), and co-opted and independent members. These are now dropped when a meeting is loaded, and
  never stored.
- Minutes name members of the public (speakers, petitioners, people in planning items) and council staff.
  `parse/redact.py` replaces their names with "[name removed]", keeping any role ("[name removed], Chief
  Executive"). It runs before text is indexed or shown, so neither the site nor the AI model sees them. The raw
  minutes stay in the store. A name is kept if its surname belongs to one of the council's councillors, because some
  councils write councillors as "Mrs Hollingsbee" or "Sir Steve Houghton". Names right after "Councillor" or
  before a councillor's role ("…, Leader of the Council") are never removed.

  In the pilot's minutes it removed 3,080 names, in 1,532 agenda items. In a random sample of 30 removals:
  - 25 were people who aren't councillors: public speakers and questioners, petitioners, officers, GPs and clergy,
    and people in honours lists;
  - 5 were places or job titles removed by mistake ("Hampshire Rose", a school's name). That over-removes, but
    exposes no one.

  It can miss a name that comes with no telling context (one sample: "the Leader invited Jonathan Davies from …",
  since fixed). A member of the public who shares a surname with a councillor is kept. A takedown route covers what
  slips through.

  **Checking for misses.** Two random samples of 100 agenda items each were read for names left in (scratch tools
  list every capitalised two- or three-word phrase that wasn't removed, for reading by hand):
  - Sample 1, 100 items from 57 councils: 4 people missed, in 2 patterns. Officers named before their role without a
    comma ("David Armiger the Chief Executive"), and questioners in a question's header ("Question 1 From: Marcus
    Simpson To: …", "Question from M J Ray"). Both are now caught.
  - Sample 2, a fresh 100 items from 60 councils, after those fixes: 8 names removed, all correctly. 2 people
    missed: a public speaker in a transcript named with their area ("Trevor Hammon (Ifield) It's really a
    question …"), and a bishop whose title took up the words, so only part of her name went ("the Right Reverend
    Sophie Jelley" became "[name removed] Jelley"). Both are now caught.

  So about 2 in 100 agenda items still held a name that should have gone, each in a pattern seen once. Expect more
  one-off patterns. The takedown route, and a repeat of this check after the full load, remain the safeguards.
- Declarations can include sensitive details about councillors' families. Show the councillor, the item and the kind
  of interest. Show the excerpt only behind a link to the council's own record.

## The full load

On 24 and 25 October 2026, every council whose web service answered was loaded the same way, from May 2018. The
per-council table and the year-by-year figures come from `councils report --all`.

- **213 of the 215 councils whose web service answered** (199 English, 14 Welsh). Stevenage's server returned errors
  ("502 Bad Gateway") on every try. Lewes was loaded last, once titles carrying the full council name were read.
- **30,848 meetings**: 13,578 of full council, 16,358 of cabinets, 912 of the policy committees of councils run by
  committees.
- **Minutes text for 78–90% of meetings each year**, about 4% read from a document. 2020 is lowest (78%), when
  meetings moved online. 2026 (81%) includes meetings whose minutes aren't published yet. 14 councils have minutes
  text for under half their meetings. Most of them publish minutes only as documents that their sites refuse to
  automated requests: Bolton, St Helens and Tameside (under 3%), and Peterborough, Lichfield and Northumberland
  (under a quarter).
- **7,342 named votes in 191 councils, with 279,450 names: 97.1% matched to a member.** 6,517 are at full council,
  762 at cabinet and 63 at policy committees. The result (carried or lost) is read for 4,960 (68%).
- **15,748 declarations of interest, 92.9% matched to a member.**
- **99% of attendance records have a recognised party**, across 631 different labels. About 25 labels, each a
  breakaway or local group sitting beside a label the council already uses for a party, are left for a person to
  decide (`scripts/party_labels.py` lists them).
- **About 121 million tokens of minutes text** in 309,852 agenda items, indexed as 526,700 passages, every one
  with a vector for meaning search. A hybrid (keyword and meaning) search over all of them takes a few seconds.
- **Storage:** 3.3 GB of cached responses, 180 MB of Parquet, 3.5 GB of search index.
- **Time:** two runs of about two hours each, then retries for the last few councils, 20 councils at a time and one
  request at a time to each. Slow servers set the pace: the last few councils took hours on their own. Embedding for meaning search ran on the machine's own
  processor at roughly 30 passages a second: about five hours for the whole archive, in resumable runs, newest first.
  Re-indexing keeps the vectors of passages whose text is unchanged, so later runs embed only what changed.

Problems found only at this scale, now fixed:

- **High Peak and Staffordshire Moorlands** share one Modern.gov site under two host names, so each council had both
  councils' executives. They are now separated (see docs/DATA.md).
- **Full council under other names:** "Cornwall Council", Blackburn with Darwen's "Council Forum", and Eastbourne's
  and Lewes's "… Borough Council Full Council".
- **Party labels:** at first 11% of attendance records had a label the rules didn't know. Many were common codes
  ("GP", "RUK", "L&C"). Learning from Open Council Data also read members who had changed party under their old
  party, so Reform UK labels were read as Conservative in three councils. Codes are now read from the year nearest
  each label's use.

**AI costs depend on briefings asked for, not on how many councils are covered.** A briefing reads the same number
of sources whatever the size of the archive, so the cost per briefing will be close to Where They Stand's.

## Back to February 2014?

Decision 4 names extending back to 25 February 2014, when English councils had to start recording named budget
votes, as the next step. To see what that would add, the 20 pilot councils were loaded for 25 February 2014 to
30 April 2018 only, into a separate store:

| | Councils |
|---|---|
| Minutes online for 2014-2018 | 13 of 20 (1,286 meetings) |
| ...with named votes | 9 (127 votes; Wirral 41, South Oxfordshire 18, Guildford 17, Stratford-on-Avon 14) |
| ...with none (Lewisham, Staffordshire, and the three Welsh councils, which the 2014 rule doesn't cover) | 4 |
| Nothing online before May 2018 (Rother, Hart, Darlington, Northumberland, Manchester, Blaenau Gwent; Westmorland and Furness didn't exist) | 7 |

So extending would add about four years for roughly two councils in three, and nothing for the rest. That makes
coverage uneven, which decision 4 chose May 2018 to avoid. Each council's page already shows its own coverage
dates, so it can be done; whether to do it is the owner's decision.

## Next steps

1. ~~Read minutes that are published only as PDF documents.~~ Done where councils serve documents; the rest need
   another network or the councils' agreement.
2. ~~Remove the names of people who aren't councillors from anything shown.~~ Done; a larger check of misses is
   still to do.
3. ~~Load the remaining councils~~ (213 of 215 loaded), and record each council's licence statement.
4. ~~Check a fresh sample of 50 votes by hand against a set target.~~ Done across all councils, then twice with
   100 votes three times: 9, then 2, then 2 votes with members on the wrong side, each fixed or now left out. The
   target of none isn't met on an untouched sample; the owner should decide whether about 1 in 100 is acceptable
   for launch, with the corrections route, or whether another round is needed.
5. ~~Adapt Where Countries Stand's index and briefing engine to council minutes, with "the minutes record that…"
   wording (docs/DECISIONS.md, 7).~~ Done, from the command line.
6. Retry the 25 councils that blocked automated requests and the 45 that were unreachable, from another network.
   Ask the ones still blocking to allow the crawler.
