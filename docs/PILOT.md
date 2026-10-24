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

85% of meetings have minutes text in the record. By year:

| Year | Meetings | With minutes text | Minutes only as a document | No minutes yet |
|---|---|---|---|---|
| 2018 | 213 | 88% | 0% | 12% |
| 2019 | 356 | 92% | 0% | 8% |
| 2020 | 397 | 78% | 2% | 20% |
| 2021 | 418 | 86% | 3% | 11% |
| 2022 | 407 | 86% | 3% | 11% |
| 2023 | 399 | 90% | 3% | 7% |
| 2024 | 396 | 82% | 9% | 10% |
| 2025 | 431 | 84% | 7% | 9% |
| 2026 | 332 | 77% | 12% | 11% |

- **2020** dips because of remote meetings during Covid.
- **2026** dips because recent minutes aren't approved yet.
- **The share published only as a document is growing.** Northumberland has put its minutes only in a PDF since
  2024. **Reading PDF minutes is needed** to keep coverage even (Where Countries Stand's `pdftext.py` is a starting
  point).
- **"No minutes yet"** also covers cancelled meetings and meetings whose minutes are attached under a title that
  doesn't say "minutes".

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

A fourth, fresh sample should be checked before launch, and the target set: for example, no member on the wrong side
in a sample of 50.

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
- Minutes name members of the public: speakers, petitioners, people in planning items. The minutes text is stored
  for search, but briefings and pages must show only councillors' words and actions (docs/DECISIONS.md, 9). **Names
  of others need to be removed before any extract is shown.** That's the next privacy task.
- Declarations can include sensitive details about councillors' families. Show the councillor, the item and the kind
  of interest. Show the excerpt only behind a link to the council's own record.

## What a full launch would take

- **About 215 councils** whose web service answers (201 English and 14 Welsh), at roughly 170 meetings each: about
  36,000 meetings.
- **A one-off load of about six hours**, with 20 councils at a time, one request at a time to each.
  Then a daily update fetches only new and recent meetings.
- **About 4 GB of cached responses and 200 MB of Parquet.** Minutes text of roughly 125 million tokens to index;
  meaning search would use a local model, as Where They Stand does, at no API cost.
- **AI costs depend on briefings asked for, not on how many councils are covered.** A briefing reads the same number
  of sources whatever the size of the archive, so the cost per briefing will be close to Where They Stand's.

## Next steps

1. Read minutes that are published only as PDF documents.
2. Remove the names of people who aren't councillors from anything shown.
3. Load the remaining councils, and record each council's licence statement.
4. Check a fresh sample of 50 votes by hand against a set target.
5. Adapt Where Countries Stand's index and briefing engine to council minutes, with "the minutes record that…"
   wording (docs/DECISIONS.md, 7).
6. Retry the 25 councils that blocked automated requests and the 45 that were unreachable, from another network.
   Ask the ones still blocking to allow the crawler.
