# Data

## Councils: `data_static/councils.csv`

Built by `scripts/build_councils.py` from:

- **England:** MHCLG's [local-authority register](https://www.planning.data.gov.uk/dataset/local-authority) on
  planning.data.gov.uk (Open Government Licence): current entries, with each council's type, GSS code and region.
  Combined authorities are left out. 318 councils.
- **Wales:** the 22 unitary authorities from mySociety's [MapIt](https://mapit.mysociety.org/).
- **Modern.gov sites:** [Local Democracy UK](https://www.local-democracy.uk/data)'s council list (CC BY 4.0), then a
  probe of the usual host names (`democracy.`, `moderngov.`, `modgov.`, `committees.` …) on each remaining council's
  own domain.

Each site was checked with one `GetCommittees` request on 24 October 2026:

| | Answered | Blocked automated requests | Unreachable from here | No Modern.gov site found |
|---|---|---|---|---|
| England (318) | 201 | 25 | 39 | 53 |
| Wales (22) | 14 | 0 | 6 | 2 |

"Blocked" and "unreachable" sites may work from another network or later. Several reset connections from the cloud
network this ran on, and had answered from it earlier the same day. Wales's two without Modern.gov are Conwy and the
Vale of Glamorgan.

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
- **Some sites serve two councils** that share services (Babergh and Mid Suffolk; Broadland and South Norfolk). Each
  committee's title starts with its council's name.
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

## Licence

Council documents are the council's copyright. See decision 10 in [`DECISIONS.md`](DECISIONS.md) for how they are
used. Each council's licence statement is to be recorded in `data_static/councils.csv` as it is added.
