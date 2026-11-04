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

## Party in control

`reference/people.py` reads control from each full council meeting's attendance list, which lists the council's
members and their parties on the day. A party with more than half of those listed is in overall control; otherwise
there is no overall control. Because some older lists are incomplete, the longest list within three months is used.
Control is reported as recorded, as a filter and a grouping, never as a judgement. Each local party counts on its own
("R4GV"), so two local groups are never added together.

## Licence

Council documents are the council's copyright. See decision 10 in [`DECISIONS.md`](DECISIONS.md) for how they are
used. Each council's licence statement is to be recorded in `data_static/councils.csv` as it is added.
