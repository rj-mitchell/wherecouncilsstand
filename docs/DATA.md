# Data

## Councils: `data_static/councils.csv`

Built by `scripts/build_councils.py` from:

- **England:** MHCLG's [local-authority register](https://www.planning.data.gov.uk/dataset/local-authority) on
  planning.data.gov.uk (Open Government Licence): current entries, with each council's type, GSS code and region.
  Combined authorities and the Greater London Authority are left out: strategic authorities are listed by hand (below,
  "Strategic authorities"). 317 councils.
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

Councils without Modern.gov use CMIS (those hosted at `*.cmis.uk.com` and others forbid all crawling in robots.txt, so
they are left out; councils' own CMIS sites that allow it are read, below), CoINS, Public Minutes, Jadu's meetings module, SharePoint, or their own pages. Each would need its
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
- **A committee whose meetings can't be listed** (East Hampshire's council meetings, once, November 2026) is tried
  again; if it fails twice, nothing is stored for the council, so the next load or update tries again, rather than
  storing it with a committee missing.
- **A meeting record without a readable date** (six councils, November 2026) takes the date the committee's list of
  meetings gave; one with no date at all is skipped and counted as failed, rather than stopping the council.
- **Certificates.** Some councils' servers leave out the intermediate certificate linking theirs to a trusted root
  (Newham, Plymouth, Boston, East Lindsey, South Holland, Torridge, November 2026). Browsers fetch it from the
  address in the site's certificate, and so does `sources/tls.py`, once, when a connection fails for that reason;
  the chain must still end at a trusted root and the name must still match.
- **Minutes can change** until approved at the next meeting, so meetings newer than 120 days are fetched again
  (`refetch_days`).

## Strategic authorities (decisions 17 to 20)

England's strategic authorities are listed by hand, beside the councils, in **`data_static/strategic_authorities.csv`**
(20 on 6 November 2026), from the research note [`research/strategic-authorities.md`](research/strategic-authorities.md):
each with its ONS `E47` code (or a provisional key, `SA-CUMBRIA` and so on, for the four created in 2026, until ONS
publishes one; the GLA keeps London's region code, `E12000007`), its statutory kind and category under the 2026 Act,
when it was created, the regions it spans (Greater Lincolnshire spans two; it is filed under the East Midlands, where
most of its people live), its meetings site and status, and, where the status alone doesn't say why it isn't covered,
the reason. `build_councils.py` leaves combined authorities and the GLA out of `councils.csv`; this file is checked by
hand each quarter against legislation.gov.uk.

- **`data_static/authority_councils.csv`**: each authority's constituent councils (and non-constituent councils where
  confirmed: York on West Yorkshire's board), with from and to dates where a council joined or left after the
  authority was created. In a two-tier area the county is the constituent council, except in Cambridgeshire and
  Peterborough, whose districts are constituent too.
- **`data_static/mayors.csv`**: each mayor, the party they were elected for, and from the day of their election to the
  day they left office (from Wikipedia's list of metro mayors, as of June 2026, and the research note; the dates
  before 2024 should be checked against the authorities' own records). Between two mayors (Greater Manchester, 18 June
  to 30 July 2026) there is none.
- **Committees** (decision 18): each authority's board, overview and scrutiny committees and any committee of
  the mayor's decisions are named in `committees.csv`, with the reason, and checked against their committee lists as
  their web services gave them on 6 November 2026 (`tests/fixtures/modgov/`), or, for the four read from their own
  websites, as those sites list them ("Meetings: authorities' own websites", below). None of the 13 lists the mayor's
  decisions as a live committee: West Midlands' "Mayoral Decision" is marked deleted, so nothing is read from it unless
  it returns. Lancashire's are on Lancashire County Council's site, so only the committees named are taken, and the
  county's own are unaffected.
- **Members** (decision 20, `authority.py`): Modern.gov's attendance for an authority names the body each member
  represents ("Bradford Council", "Tameside MBC"), which is matched to the council. Each member is the mayor, a
  constituent or non-constituent member, a substitute, a co-opted member, or an appointed member who isn't a
  councillor (named nowhere: name and member id dropped, and removed from the minutes). A councillor's party on the date
  is their home council's record where the site has it (first initial and surname, one match within a year), otherwise
  the authority's; `party_source` says which.
- **The GLA's members** (decision 20): every member listed at its meetings, other than the Mayor, is an elected London
  Assembly member (`assembly_member`), named, with the GLA's record of their party. Names drop the letters after them
  and a peer's designation ("Hina Bokhari OBE AM" -> "Hina Bokhari", "Baron Duvall of Woolwich, in the Royal Borough
  of Greenwich AM" -> "Lord Duvall", as the minutes write him), and the vote reader ignores "AM", so recorded votes
  ("For the amendment: Hina Bokhari OBE AM, ...") are read by name: a trial of November 2025 to February 2026 read
  20 meetings and 11 named votes, every name matched. Constituency codes aren't kept ("E&H" is two constituencies).
- **Control** (decision 19): the mayor's party on the date, as `MAYOR:LAB`, or `SA:NONE` (no single party) with no
  mayor, never a council's party in overall control.
- **What was seen** (two meetings, 6 November 2026): West Yorkshire's board minutes are in the web service, with votes
  as counts ("For: 8 Against: 0 Abstentions: 2") and no names; Greater Manchester's are published only as a document
  on the next agenda, and its attendance wasn't updated after the meeting (everyone "Expected"). Expect few named votes:
  the one the law requires is on a mayor's budget when it is challenged.

## Robots.txt (decision 21)

**Not obeyed, by the owner's decision of 6 November 2026**: robots.txt isn't treated as a blanket barrier to
councils' public records. `[robots] obey` in `config/settings.toml` is `false`, and every reader (Modern.gov, CMIS,
CoINS, the authorities' own websites) asks `sources/robots.py`, which then allows every page without reading the file's rules. Whatever the
setting, any `Crawl-delay` the site's robots.txt asks for is honoured where the file can be read, the crawler names
itself, requests to one council are one at a time at least `min_interval_seconds` apart, and a site that refuses
requests (401, 403, 429, a bot check) is asked, never worked around.

With the setting on, the rules are read as RFC 9309 says: a rule for this crawler by name ("User-agent:
WhereCouncilsStand") is honoured over the rule for everyone; paths are compared as written and also ignoring case
(these are IIS sites), and a page either comparison forbids is forbidden. Modern.gov sites that forbid the web service
then aren't asked (the load stops with "robots.txt forbids crawling", nothing written), and CMIS and CoINS sites whose
robots.txt can't be fetched are treated as forbidding. `scripts/build_councils.py` follows the same setting.

On 6 November 2026, 44 Modern.gov sites (44 councils and the Greater London Authority) were found to forbid reading,
nearly all with Civica's usual file ("Disallow all webbot searching BUT allow Google access to mgRss for calendar
sync"). They are read as before. The **26 councils on CMIS** marked `robots` under the earlier rule (every Civica-hosted site,
and Derby, Essex, Harborough, Hull, Walsall, Warrington and West Dunbartonshire's own) are `ok` again, at the owner's
request of 6 November 2026, and are loaded once on the server (docs/OPERATIONS.md). Hull's (`cmis.hullcc.gov.uk`) accepts connections but never completes the secure handshake, from the
server as from elsewhere (7 November 2026), so it is marked `unreachable` until it answers again. A council marked `robots` (`Council.withheld`)
isn't asked, and anything stored for it is kept but not shown, searched or updated; none that is loaded is marked.

## Meetings: CMIS sites

Civica's CMIS (and Nottinghamshire's variant of it, "DMS") is an ASP.NET (DotNetNuke) site with no web service, so
`sources/cmis.py` reads its public pages as a browser would. Every response is cached, gzipped, under
`data/raw/cmis/<council>/`. Councils on CMIS have `system` `cmis` in `councils.csv`; `modgov_url` holds the site's
base address.

**Robots and refusals.** Every page is checked with `sources/robots.py` before it is fetched, and any `Crawl-delay`
is honoured. With `[robots] obey` off (decision 21) every page is allowed. With it on, a site whose robots.txt forbids
its pages gets "robots.txt forbids crawling" and nothing is read: every Civica-hosted site (`*.cmis.uk.com`,
`*.cmis-ni.org`), whose robots.txt is `Disallow: /`, which is why 26 councils were left out until November 2026; and
Nottinghamshire's documents (`Disallow: /DMS/Document.ashx`), which are read now. A 401, 403,
429 or a bot check's page stops the council's load with an error; it isn't retried or worked around. (A redirect to
`login.aspx`, as Norwich's home page does, is a page that needs a login, not a refusal: it is skipped.)

| Page | Used for |
|---|---|
| `Committees.aspx`, and the site's other pages of committees its navigation links ("Former committees", "Historical committees", Sunderland's committees by council year, leaving out years before the start) | Committees, by id and title, linked as `…/ctl/ViewCMIS_CommitteeDetails/mid/<m>/id/<committee>/Default.aspx`. Their kind comes from `committees.py` as for Modern.gov |
| A committee's page | Its meetings, ten to a page of a grid, oldest first. The page around today is shown first; the others are reached by the grid's own postbacks (the form posted back, as the page's links do), walking back to the start date |
| A meeting's page, `…/ctl/ViewMeetingPublic/mid/<m>/Meeting/<id>/Committee/<committee>/Default.aspx` | Date, status, venue; the agenda, where the council enters one (Norwich and Nottinghamshire do, Sunderland and Warwick don't), with each item's number, title, text, documents and a link to any decision; minutes per item where entered (none of the sites seen do); its documents; grids of members attended, other members in attendance, apologies and absent, and declarations of interest, 25 to a page, the further pages reached by postback |
| `Document.ashx?…` | Minutes documents (PDF). The address is encrypted but stable, and the cache is keyed by it |
| A councillor's page, `…/ctl/ViewCMIS_Person/…/id/<person>/Default.aspx` | Party and ward history, each with from and to dates |

What was found:

- **Minutes are documents.** A meeting's own minutes are usually on its own page ("Minutes of the Full Council meeting
  held on 27 January 2026", Norwich; "Minutes Additonal Council 15 July 2026", Warwick), or at the next meeting's
  item approving them (Sunderland: "02 - Minutes of the last ordinary meeting of the Council held on 30 January
  2019"). Titles may be written as one word ("02-MinutesOfLastMeetingHeldOn3March2021") or without the year ("Public
  Minutes of 9 February Cabinet meeting"); both are read. The document is split into the agenda's items where the
  site has an agenda (`documents.split_into_items`), and otherwise kept whole as one "Minutes" item.
- **Some CMIS PDFs have cross-reference offsets a few bytes out**, from an update CMIS appends (Sunderland). pdfminer
  reads none of their text; the offsets are corrected (`cmis.repair_pdf`) and the document read again.
- **Some minutes are scanned images** (Warwick's 2018–19 minutes), with no text to read; they aren't read (there is
  no OCR).
- **Attendance** comes from the meeting's grids, with CMIS's own id for each councillor as `member_id`. Roles aren't
  in the grids: "the Mayor" or "the Chair" is taken from the minutes' "Present:" list ("The Mayor (Councillor L
  Scanlan) in the Chair", "Kendrick (Lord Mayor)"). Where a meeting's grids are empty, the attendance is read from that
  list, with an id made from the name as written ("sands-m") and no party.
- **Party on the date** comes from each councillor's party history, which CMIS keeps with dates for former
  councillors too. Where no entry covers the meeting's date, the party is left blank, never guessed. Labels are the
  party's name ("Labour", "Liberal Democrats"), mapped to codes as for Modern.gov.
- **Votes**: Sunderland prints its recorded votes one member to a line ("Atkinson", "Gibson, E."), which flattening
  the text would run together, so the reader turns such lists into commas (`votes.line_lists`) before storing the
  minutes; only for CMIS, since Modern.gov's text breaks single names over lines ("H" / "Blagbrough"). Sunderland's
  PDFs also run columns together ("And 1 abstention:- Councillor Bewick Guy, Heron, ..."), so a vote is kept only
  where the count printed before each list ("with 55 Members voting in favour:-", "Nine Members voted against") is
  the number of names read: about half its recorded votes (45 of about 100, 2018–2026). Norwich mostly records
  counts ("with 31 members voting in favour"), with its few named votes in brackets.
- **A committee page that lists only one council year** (Luton) until its own "meetings from" filter is set has the
  filter set to the start date, as a person would, and is then paged as usual. Only the "from" date is set, so
  meetings already arranged stay listed; a committee that began later keeps its own first date
  (Nottinghamshire's Cabinet, 2022), and its page is used as first shown.
- **A committee whose meetings can't be listed** (paging failed: Sunderland's council meetings, once, November
  2026) is tried again; if it fails twice, nothing is stored for the council, so the next load or update tries again,
  rather than storing it with a committee missing.
- **Slow pages**: each page is 100–200 KB of ASP.NET form, and a council of eight years takes about 1,000 requests
  (half an hour at a request a second).

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

## Meetings: authorities' own websites

Four strategic authorities publish their meetings as documents on their own websites, not through a meetings system:
Tees Valley, Hull and East Yorkshire, Cumbria, and Hampshire and the Solent (`system=docsite` in
`strategic_authorities.csv`; their meetings pages were found on 6 November 2026, Hampshire and the Solent's under its
site's "Democracy" pages, which answered that day although they had refused the research's requests earlier).
`sources/docsite.py` reads them, configured per authority in **`data_static/document_sites.csv`**: each committee in
scope, the pages that list its meetings, and their layout. Every response is cached, gzipped, under
`data/raw/docsite/<authority>/`, with the same user agent, spacing, Crawl-delay and refusals as the other readers.

| Layout | Sites | Read as |
|---|---|---|
| `sections` | Tees Valley (WordPress: the current year's page and its archive), Hampshire and the Solent (WordPress, one page a committee) | Meetings under dated headings ("31st July 2026", "28 September 2026 @ 2.30pm"), each followed by links to its documents |
| `listing` | Cumbria (LocalGov Drupal: a paged list), Hull and East Yorkshire (Jadu: a directory by council year) | A list of meetings, each linking to a page of its own with its documents; further pages ("?page=1") and council years ("2025/26") are followed |

What was found:

- **Minutes.** A meeting's minutes are the document titled as minutes that carries its date, in its link or its file
  name ("Cabinet-minutes-25-July-2025.pdf", "Minutes-280619.pdf", "20250926-heyca-executive-board-minutes", and
  Hampshire and the Solent's "260928_Board-Minutes-Final.pdf", year first). Approved or final minutes are preferred to
  drafts; a meeting without its own takes the draft attached to the committee's next meeting. A link to a file with
  another meeting's date isn't taken (Tees Valley's 15 October 2025 scrutiny meeting links the 19 November minutes).
  An annual meeting held the same day as an ordinary one (Tees Valley's AGM) is read with it. The minutes are kept
  whole as one "Minutes" item: there is no agenda to split them by, and their numbering ("TVCA 32/25") doesn't survive
  the PDFs' columns.
- **Not every meeting has minutes on the site.** Hull and East Yorkshire publishes most of its scrutiny committee's
  minutes, and three of its board's, only inside the next meeting's agenda pack, and Tees Valley its scrutiny
  committee's since 2026 and a few of its cabinet's; these meetings are kept without minutes or attendance. Tees
  Valley's site has nothing before April 2019 (the archive starts with the 2019/20 council year).
- **Attendance** is read from the list at the top of the minutes: "Present:" or "ATTENDEES", with sections for
  members, associate members, apologies, and those in attendance or officers (only councillors and mayors are kept
  from the last three: Tees Valley lists officers' apologies with the members', with nothing to tell them apart).
  The layouts differ: a name a line with the council in brackets ("Councillor Ian Blades (Middlesbrough Council)
  (Chair)"), a name a line with the roles in a column beside them, which comes out of the PDF after the names ("Leader,
  Hartlepool Borough Council") and is matched in order (a member written without a title whose role is a council's
  leader or "Mayor of Middlesbrough" is that councillor or mayor), the council after a comma, or a sentence ("Councillors
  Handley, Ross, Tock (substituting for Councillor Dad), and Tucker", "Cllr M Fryer (Chair), Cllr J Brook (Vice Chair)
  ..."). A councillor named without their council is matched to the authority's member councils' stored records by
  surname and first name or initial, within a year (`authority.find_member`), and takes that council and its record's
  full name; one not matched (a council the site doesn't hold, or two who fit) is a non-constituent member with no
  party. A body or office is never read as a person.
- **Members** are then classed as on Modern.gov (`authority.classify`, decision 20): the mayor, councillors (constituent
  or non-constituent members, substitutes), and appointed members who aren't councillors (business board chairs,
  members of the old local enterprise partnership, the police and crime commissioner), counted with their names
  removed from the attendance and the minutes. Party is the home council's record on the date, where the site holds
  it; these minutes give none of their own.
- **Coverage** (loaded on 6 November 2026, from a cloud network): Tees Valley 81 meetings from April 2019 (68 with
  minutes), Hull and East Yorkshire 23 from March 2025 (13), Cumbria 7 from March 2026 (all), Hampshire and the Solent
  3 from July 2026 (all). Mayor's decisions aren't published as meetings on any of the four sites.
- **Named votes.** None are read yet. Most decisions are by consensus. The minutes record two named votes, in
  layouts `parse/votes.py` doesn't read: Tees Valley's scrutiny committee on 14 October 2022 lists a roll call one
  member to a line ("Cllr Branson (Middlesbrough) - For"), and Hampshire and the Solent's board's budget vote on 13
  July 2026 is a table whose columns come apart in the PDF. Declarations of interest are read (71 at Tees Valley).

## Party in control

`reference/people.py` reads control from each full council meeting's attendance list, which lists the council's
members and their parties on the day. A party with more than half of those listed is in overall control; otherwise
there is no overall control. Because some older lists are incomplete, the longest list within three months is used.
Control is reported as recorded, as a filter and a grouping, never as a judgement. Each local party counts on its own
("R4GV"), so two local groups are never added together.

## Links to Where Landlords Stand: `data_static/landlords_links.csv`

Each council's page links to its pages on Where Landlords Stand, the charity's site on social landlords in England:
the council as a landlord, where it owns homes and has a profile there, and the area page listing the landlords with
homes in its area. Both sites key councils by ONS GSS code (and both use the post-2019 codes for Barnsley and
Sheffield). The file lists, for each council, the area page's name, slug and number of landlords, and the council's
own landlord page, if any (296 areas and 160 councils as landlords on 6 November 2026).

It is built by `scripts/landlords_links.py` from the Landlords repository's register (`data_static/landlords.csv`)
and that site's published figures (`data/homes-by-area.csv` and `data/landlords.csv`, from a local build or the live
site), naming area pages as that site does. Every page is checked against the build before it is written. Run it
after Where Landlords Stand's weekly update has published new figures, and commit the file: the link is a fixed
address, so this site never depends on the other being up. Where Landlords Stand links back to each council's page
here (`/councils/{gss}`).

## Licence

Council documents are the council's copyright. See decision 10 in [`DECISIONS.md`](DECISIONS.md) for how they are
used. Each council's licence statement is to be recorded in `data_static/councils.csv` as it is added.
