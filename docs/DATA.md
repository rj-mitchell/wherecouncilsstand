# Data

## Councils: `data_static/councils.csv`

Built by `scripts/build_councils.py` from:

- **England:** MHCLG's [local-authority register](https://www.planning.data.gov.uk/dataset/local-authority) on
  planning.data.gov.uk (Open Government Licence): current entries, with each council's type, GSS code and region.
  Combined authorities are left out. 318 councils.
  The register still gives Barnsley and Sheffield the GSS codes ONS replaced on 1 April 2019, when the boundary
  between them moved (E08000016, E08000019); `build_councils.py` uses the current ones (E08000038, E08000039), as ONS
  and the Regulator of Social Housing do (`SUPERSEDED`). A data folder loaded before this change is moved to the new
  codes by `scripts/recode_councils.py`.
- **Wales:** the 22 unitary authorities from mySociety's [MapIt](https://mapit.mysociety.org/).
- **Scotland and Northern Ireland** (in scope from 5 November 2026, decision 2): Scotland's 32 councils (MapIt's
  unitary authorities) and Northern Ireland's 11 district councils (MapIt's local government districts). Their
  websites and meetings systems were found by research, November 2026: Modern.gov at 9 (Aberdeen City,
  Aberdeenshire, Argyll and Bute, City of Edinburgh, Dumfries and Galloway, East Dunbartonshire, Scottish Borders,
  Belfast, and Derry City and Strabane), CMIS at 8, CoINS at 4 (Falkirk, Glasgow, Shetland, West Lothian), Public
  Minutes at 2 (Armagh City, Banbridge and Craigavon; Fermanagh and Omagh), and the council's own pages at 20.
- **Modern.gov sites:** [Local Democracy UK](https://www.local-democracy.uk/data)'s council list (CC BY 4.0), then a
  probe of the usual host names (`democracy.`, `moderngov.`, `modgov.`, `committees.` …) on each remaining council's
  own domain.

Each site was checked with one `GetCommittees` request on 24 October 2026, again from the live server (which is in
the UK) on 4 November, and the councils with no site found were researched on 5 November:

| | Answered | Blocked automated requests | Unreachable | No Modern.gov site found |
|---|---|---|---|---|
| England (318) | 251 | 13 | 16 | 38 |
| Wales (22) | 20 | 0 | 1 | 1 |
| Scotland (32) | 7 | 0 | 0 | 25 |
| Northern Ireland (11) | 1 | 0 | 1 | 9 |

"Blocked" and "unreachable" sites may work from another network or later: many refuse connections from cloud
networks, and some from outside the UK ("Connection denied by Geolocation"), but answer the server. A firewall's or
bot check's page, or a Cloudflare timeout, counts as blocked or unreachable, not as no site. Sites that refuse the
crawler are asked, not worked around (decision 2).

Councils without Modern.gov use CMIS (hosted at `*.cmis.uk.com` and others, whose robots.txt forbids all crawling, so
they are left out), CoINS, Public Minutes, Jadu's meetings module, SharePoint, or their own pages. Each would need its
own reader.

## Meetings: Modern.gov's web service

Every Modern.gov site has an ASP.NET web service at `/mgWebService.asmx`. It's undocumented. Its operations are
listed at that address, and its WSDL is at `?WSDL`. It needs no key. Dates are day/month/year.

| Operation | Used for |
|---|---|
| `GetCommittees` | All committees, with expired and deleted flags |
| `GetMeetings?lCommitteeId=&sFromDate=&sToDate=` | A committee's meetings in a date range |
| `GetMeeting?lMeetingId=` | The whole meeting: agenda items with **the minutes of each item as HTML** (`minutesnonemptyhtmlbody`), decision, call-in and restricted flags, declaration counts, linked documents, and **attendees with role, attendance and party on the date** (`politicalparty`), and ward |

Other operations exist (`GetCouncillorsByWard`, `GetElectionResults`, `GetWebCastMeetings` and more) but aren't used
yet.

What was found:

- **Party is recorded as at the meeting.** A councillor who changed party shows the old party at earlier meetings.
  Councils also relabel parties over time ("LAB", then "Labour"), so labels are mapped to codes
  (`parse/parties.py`).
- **Attendance lists can be incomplete for older meetings.** Some councillors who left the council are missing from
  older meetings' lists even though the minutes name them in votes. Names are matched to the meeting's attendance
  first, then to anyone recorded at the council's meetings within a year either side.
- **Some sites serve two councils** that share services (Babergh and Mid Suffolk; Broadland and South Norfolk; Adur
  and Worthing; Lewes and Eastbourne). Each committee's title starts with its council's name. High Peak and
  Staffordshire Moorlands share one site under two host names, with titles such as "Council (HPBC)" and an
  unprefixed "Cabinet" and "The Executive". Which is whose is set in `data_static/committees.csv`, from the wards of
  the members who attend. Councils sharing a site were found by comparing their committee lists.
- **Successor councils can host their predecessors' committees.** Westmorland and Furness's site still holds
  Cumbria County Council's and Barrow Borough Council's committees, with their names as a prefix.
- **Some councils split full council into several committees** in Modern.gov, for example Lewisham's
  "Full Council - Council questions".
- **Servers can be slow.** `GetMeeting` took 7–24 seconds on some councils' servers, which is why the pilot loads
  councils side by side.
- **A meeting's minutes are attached to the next meeting's agenda**, at the item that approves them. Where a council
  publishes minutes only as a document, that's where they're found (`sources/documents.py`). Documents come from
  `mgConvert2PDF.aspx?ID=…`, which many sites, especially Civica-hosted `*.moderngov.co.uk` ones, put behind a
  browser check that refuses automated requests, although the web service itself answers.
- **Minutes can change** until approved at the next meeting, so meetings newer than 120 days are fetched again
  (`refetch_days`).

## Meetings: CoINS

Four Scottish councils publish through Northgate's CoINS: Glasgow, Falkirk, Shetland and West Lothian
(`system=coins` in `councils.csv`). CoINS has no web service, so `sources/coins.py` reads its public pages, which
are the same on every site apart from the site's address (checked November 2026; none has a robots.txt, which
allows everything). Every response is cached under `data/raw/coins/<council>/`, with the same spacing, user agent,
retries and refetching of recent meetings as Modern.gov.

| Page | Used for |
|---|---|
| `allCommittees.asp?sort=1&page=0&rec=1000` | Every committee (`page=0` shows the whole list), linking to `committee.asp?bodyid=…` |
| `allBodyMeetings.asp?bodyid=…&bodytitle=…&MeetingYear=…&page=0&rec=1000` | A committee's meetings in a year, linking to `Agenda.asp?meetingid=…`. The `bodytitle` must be the committee's own title, or the list comes back empty |
| `Agenda.asp?meetingid=…` | The agenda items ("Number / Item"), each item's papers (`submissiondocuments.asp?submissionid=…`), restricted items (those after a heading such as "The following items contain exempt information"), and the meeting's packs: "Public Agenda", "Public Minutes" |
| `viewPack.asp?c=…`, `viewDoc.asp?c=…` | A page showing a PDF in a frame (`viewSelectedPack.asp`, `viewSelectedDocument.asp`), which is followed. Glasgow serves the pack page only to a request that names the agenda page it came from (the `Referer` a browser sends), so the reader sends it |
| `submissiondocuments.asp?submissionid=…` | A paper's documents, where a meeting's minutes are a paper on a later agenda |
| `allMembers.asp`, `political.asp`, `partyMembers.asp` | Current members, their wards, and their parties |

* **Committees.** Full council is named as the council ("Glasgow City Council", "West Lothian Council"), which
  `committees.py` recognises. The main committees are Glasgow's City Administration Committee, Falkirk's Executive
  (under three titles since 2018, in `committees.csv`), Shetland's Policy and Resources Committee and West
  Lothian's Council Executive.
* **Minutes.** Glasgow, Shetland and West Lothian attach a "Public Minutes" pack to each meeting. Falkirk doesn't:
  its minutes are a paper on a later agenda ("Minute of Meeting of Falkirk Council held on 28 February 2024", or an
  item "Minute" with that line under it), found by the meeting's date, as on Modern.gov. The committee's own next
  agendas are searched first, then the other committees' in scope, whose paper must name the committee: Falkirk's
  Executive approves its minutes at its next sitting, which since June 2024 may be the "Executive (including
  Education)". Falkirk's separate "Record of Votes" paper
  isn't read, because the minutes record the same votes. The text is split into the agenda items by their titles
  (without "- Report by …") where at least half are found, as `sources/documents.py` does; otherwise it is kept whole
  as one "Minutes" item. Glasgow's minutes head each item with a summary ("Minutes approved.") rather than the
  agenda's title, so its minutes are mostly kept whole.
* **Attendance from the sederunt.** Meeting pages don't list attendance, so it is read from the list at the top of
  the minutes. The layouts differ: "Present:" and a sentence of names (Glasgow's committees, West Lothian), one
  name a line in capitals (Glasgow's council), "Councillors:" (Falkirk), initials and surnames, with "Present via
  Remote Link:" (Shetland). "Present" sections give `Present`, "Apologies" gives `Apologies`, and "Also present" or
  "In attendance" gives `In attendance` but only for names matched to a current councillor. Officers' sections
  ("Attending:", "Officers:", "In Attendance (Officers):") end the list, and so does a block naming job titles
  whatever its header (one Glasgow meeting lists its officers under a second "Present:"). Offices printed in the
  list ("LORD DEAN OF GUILD", "DEACON CONVENER") aren't names. A committee can list people who aren't councillors,
  such as the religious representatives who sit for education business, so a name in a committee's sederunt that
  isn't on the members pages is kept only if full council's sederunts list it too (decision 9). Only the first
  sederunt is read: a meeting that resumes may take it again. Roles come from the list: "(Chair)", "(substitute for
  …)", "Provost", "Bailie".
* **Member ids.** A name is matched to the members pages by full name, or by initials and surname where only one
  current member fits, and takes CoINS's member id. Otherwise (former councillors) the id is the name as a slug
  ("allan-casey"), the same wherever the minutes write the name the same way.
* **Party limits.** CoINS gives only each current councillor's current party; there is no party on the date. So a
  party is recorded only for a current councillor, and only at meetings in the last year (and since the last
  ordinary election, 5 May 2022). Earlier, and for former councillors, the party is left blank: it is never guessed.
  The year limits the risk of showing a councillor who changed party with the new party at earlier meetings (it does
  happen: Glasgow's members pages list Your Party councillors, a party founded in 2025), at the cost of party data
  for most of the record. These councils are rated "partly working" on the councils page for that reason.
  Party in control is therefore read only for the last year. Labels are mapped as for Modern.gov; a site's
  abbreviation in brackets ("Scottish Green Party (SGP)") is dropped, and `parties.csv` maps Shetland's "- None"
  (no party), Falkirk's "Scottish Labour and Co-operative Party" and "Non-Aligned Independent".
* **Named votes** (November 2026). Scottish councils vote on a motion against an amendment, not for against
  against. Falkirk lists each side by name ("For the motion (15) – Depute Provost Balfour; and Councillors Binnie,
  … For the amendment (12) – Provost Bissett; and Councillors …"), which `parse/votes.py` reads as two votes, one
  with the motion's supporters "for" and one with the amendment's supporters "for", the outcome after them going to
  the second. Glasgow's minutes give only the numbers ("32 members voted for the amendment … 46 for the motion").
  West Lothian and Shetland print a roll call as columns headed "Motion", "Amendment", "Abstain": West Lothian's
  come out of the PDF's text row by row, mixing the columns, and Shetland's ("Amendment Ms Hawick Mrs Lyall
  Motion Mr Anderson …") have no heading `votes.py` reads, so neither is read yet.

## Party in control

`reference/people.py` reads control from each full council meeting's attendance list, which lists the council's
members and their parties on the day. A party with more than half of those listed is in overall control; otherwise
there is no overall control. Because some older lists are incomplete, the longest list within three months is used.
Control is reported as recorded, as a filter and a grouping, never as a judgement. Each local party counts on its own
("R4GV"), so two local groups are never added together.

## Licence

Council documents are the council's copyright. See decision 10 in [`DECISIONS.md`](DECISIONS.md) for how they are
used. Each council's licence statement is to be recorded in `data_static/councils.csv` as it is added.
