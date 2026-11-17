# Strategic authorities: research note

The facts behind the site's coverage of England's strategic authorities, as found on 6 November 2026: what exists,
where each authority publishes its meetings, and what their records look like. A user organisation asked for this
coverage "as they scramble to understand them in the run-up to greater devolution". The decisions taken from it are
[decisions 17 to 21](../DECISIONS.md#17-strategic-authorities), and how the site reads the authorities is in
[`DATA.md`](../DATA.md), "Strategic authorities". This note is not kept up to date: the registry
(`data_static/strategic_authorities.csv`) is.

Every fact carries a date. "Not confirmed" means it couldn't be found in a primary source. Requests to the authorities'
own sites were made on 6 November 2026 from a development machine (not the site's server), with the user agent
`WhereCouncilsStand-research (+https://wherecouncilsstand.com)`, after reading each site's robots.txt.

## In short

- 20 strategic authorities exist (6 November 2026): 13 combined authorities, 6 combined county authorities and
  the Greater London Authority. 14 have a mayor. Two more (Greater Essex; Norfolk and Suffolk) are agreed but not yet
  established, and about a dozen more areas are in talks.
- 16 publish their meetings on Modern.gov: 12 on their own sites, Lancashire's, Sussex and Brighton's and Cheshire
  and Warrington's on a council's site, and the GLA's. Four publish them as documents on their own websites (Tees
  Valley, Hull and East Yorkshire, Cumbria, and Hampshire and the Solent).
- The record is thinner than a council's. Boards are small (often 5–15 voting members), mostly vote by consensus,
  and few minutes name how members voted. The one named vote the law requires is on the mayor's budget. Attendance
  in Modern.gov carries each member's party and home council.

## 1. The authorities, and coming changes

### The law

- The **English Devolution White Paper** (16 December 2024) proposed "strategic authorities" in three tiers.
- The **English Devolution and Community Empowerment Act 2026** (c. 23) received Royal Assent on **29 April 2026**
  ([legislation.gov.uk](https://www.legislation.gov.uk/ukpga/2026/23/contents)). Section 1 (in force at Royal Assent)
  defines a [strategic authority](https://www.legislation.gov.uk/ukpga/2026/23/section/1) as:

| Category | What it is |
|---|---|
| Single foundation strategic authority | A unitary or county council designated by regulations, with its consent ([s. 3](https://www.legislation.gov.uk/ukpga/2026/23/section/3), fully in force 29 June 2026). None designated yet (not found on legislation.gov.uk, 6 November 2026) |
| Combined foundation strategic authority | A non-mayoral combined authority or combined county authority |
| Mayoral strategic authority | A mayoral combined authority, a mayoral combined county authority, or the GLA |
| Established mayoral strategic authority (EMSA) | A mayoral one designated by regulations ([s. 8](https://www.legislation.gov.uk/ukpga/2026/23/section/8)), and the GLA |

- EMSAs. Greater Manchester, West Midlands, Liverpool City Region, North East, South Yorkshire, West Yorkshire and
  the GLA were named as established from Royal Assent ([GOV.UK area
  factsheets](https://www.gov.uk/government/publications/english-devolution-area-factsheets/english-devolution-area-factsheets),
  10 July 2025). On **31 July 2026** the Cabinet Office announced four more: Cambridgeshire and Peterborough, East
  Midlands, West of England, and York and North Yorkshire ([Ward
  Hadaway](https://www.wardhadaway.com/insights/updates/four-mayoral-strategic-authorities-secure-established-status/)).
  The designation regulations couldn't be found, so whether they are in force is not confirmed.
- Mayors are again elected by the supplementary vote ([s. 63](https://www.legislation.gov.uk/ukpga/2026/23/section/63)),
  and an MP can't be a mayor ([s. 17](https://www.legislation.gov.uk/ukpga/2026/23/section/17)).

### The 20 authorities (6 November 2026)

GSS codes for combined and combined county authorities are ONS's `E47` codes, from ONS's [local authority district to
combined authority lookup (May
2025)](https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD25_CAUTH25_EN_LU/FeatureServer/0) and
MHCLG's [local-authority register](https://files.planning.data.gov.uk/dataset/local-authority.csv) (type `COMB`).
Neither had codes for the four authorities created in 2026 when checked on 6 November 2026. Mayors are from
[Wikipedia's list](https://en.wikipedia.org/wiki/Metro_mayor) (as of June 2026) and the Greater Manchester
by-election result below; their parties are as elected.

| Authority | Kind | Created | GSS | Mayor (party) | Next mayoral election |
|---|---|---|---|---|---|
| Greater Manchester | Mayoral CA, EMSA | 1 April 2011 | E47000001 | Bev Craig (Labour and Co-operative), elected 30 July 2026 | May 2028 |
| South Yorkshire | Mayoral CA, EMSA | 1 April 2014 | E47000002 | Oliver Coppard (Labour and Co-operative) | May 2028 |
| West Yorkshire | Mayoral CA, EMSA | 1 April 2014 | E47000003 | Tracy Brabin (Labour and Co-operative) | May 2028 |
| Liverpool City Region | Mayoral CA, EMSA | 1 April 2014 | E47000004 | Steve Rotheram (Labour) | May 2028 |
| Tees Valley | Mayoral CA | 1 April 2016 | E47000006 | Ben Houchen (Conservative) | May 2028 |
| West Midlands | Mayoral CA, EMSA | 17 June 2016 | E47000007 | Richard Parker (Labour and Co-operative) | May 2028 |
| Cambridgeshire and Peterborough | Mayoral CA, EMSA from 31 July 2026 (announced) | 3 March 2017 | E47000008 | Paul Bristow (Conservative) | May 2029 |
| West of England | Mayoral CA, EMSA from 31 July 2026 (announced) | 9 February 2017 | E47000009 | Helen Godwin (Labour) | May 2029 |
| York and North Yorkshire | Mayoral CA, EMSA from 31 July 2026 (announced) | December 2023 or February 2024 (sources differ) | E47000012 | David Skaith (Labour and Co-operative) | May 2028 |
| East Midlands | Mayoral CCA, EMSA from 31 July 2026 (announced) | 28 February 2024 | E47000013 | Claire Ward (Labour and Co-operative) | May 2028 |
| North East | Mayoral CA, EMSA | 7 May 2024 ([SI 2024/402](https://www.legislation.gov.uk/uksi/2024/402/contents)) | E47000014 | Kim McGuinness (Labour and Co-operative) | May 2028 |
| Devon and Torbay | Non-mayoral CCA (foundation) | February 2025 ([SI 2025/115](https://www.legislation.gov.uk/uksi/2025/115/contents)) | E47000015 | None | None |
| Hull and East Yorkshire | Mayoral CA | February 2025 ([SI 2025/113](https://www.legislation.gov.uk/uksi/2025/113/contents)) | E47000016 | Luke Campbell (Reform UK) | May 2029 |
| Greater Lincolnshire | Mayoral CCA | February 2025 ([SI 2025/117](https://www.legislation.gov.uk/uksi/2025/117/contents)) | E47000017 | Andrea Jenkyns (Reform UK) | May 2029 |
| Lancashire | Non-mayoral CCA (foundation) | February 2025 ([SI 2025/118](https://www.legislation.gov.uk/uksi/2025/118/contents)) | E47000018 | None | None |
| Cumbria | Mayoral CA, no mayor yet | 24 February 2026 ([SI 2026/158](https://www.legislation.gov.uk/uksi/2026/158/contents)) | Not yet published | None until May 2027 | May 2027 (first) |
| Cheshire and Warrington | Mayoral CA, no mayor yet | 24 February 2026 ([SI 2026/159](https://www.legislation.gov.uk/uksi/2026/159/contents)) | Not yet published | None until May 2027 | May 2027 (first) |
| Sussex and Brighton | Mayoral CCA, no mayor yet; calls itself the "Sussex & Brighton Strategic Authority" | 26 March 2026 ([SI 2026/362](https://www.legislation.gov.uk/uksi/2026/362/contents)) | Not yet published | None until May 2028 | May 2028 (first) |
| Hampshire and the Solent | Mayoral CCA, no mayor yet | 4 June 2026 ([SI 2026/595](https://www.legislation.gov.uk/uksi/2026/595/contents)) | Not yet published | None until May 2028 | May 2028 (first) |
| Greater London Authority | Mayoral strategic authority, EMSA | 3 July 2000 | None of its own; the registry uses London's region code, E12000007 | Sadiq Khan (Labour) | May 2028 |

Notes:

- Greater Manchester. Andy Burnham was elected MP for Makerfield on 18 June 2026, which vacated the mayoralty.
  Bev Craig, until then leader of Manchester City Council, won the by-election on 30 July 2026
  ([Stockport Council, results](https://www.stockport.gov.uk/news/greater-manchester-mayoral-election-results-2026)).
- "Created" dates for the 2025 authorities are from Wikipedia ([Strategic
  authority](https://en.wikipedia.org/wiki/Strategic_authority)); the instruments are linked.
- Tees Valley couldn't apply for EMSA status while under a Best Value Notice (GOV.UK factsheets, 10 July 2025).
- The North East is legally the North East Mayoral Combined Authority; it calls itself the North East Combined
  Authority. Its predecessors, the North East and North of Tyne combined authorities (E47000010, E47000011), were
  dissolved on 6–7 May 2024 (MHCLG register).

### Constituent councils

Constituent councils appoint the authority's voting members. GSS codes match `data_static/councils.csv`. ONS's lookup
lists every district in an area, but in a two-tier area the constituent council is the county (Devon County Council,
not Teignbridge), except in Cambridgeshire and Peterborough, where the districts are constituent too.

| Authority | Constituent councils (GSS) |
|---|---|
| Greater Manchester | Bolton E08000001, Bury E08000002, Manchester E08000003, Oldham E08000004, Rochdale E08000005, Salford E08000006, Stockport E08000007, Tameside E08000008, Trafford E08000009, Wigan E08000010 |
| Liverpool City Region | Halton E06000006, Knowsley E08000011, Liverpool E08000012, St Helens E08000013, Sefton E08000014, Wirral E08000015 |
| West Yorkshire | Bradford E08000032, Calderdale E08000033, Kirklees E08000034, Leeds E08000035, Wakefield E08000036 |
| South Yorkshire | Barnsley E08000038, Doncaster E08000017, Rotherham E08000018, Sheffield E08000039 |
| West Midlands | Birmingham E08000025, Coventry E08000026, Dudley E08000027, Sandwell E08000028, Solihull E08000029, Walsall E08000030, Wolverhampton E08000031 |
| North East | Durham E06000047, Gateshead E08000037, Newcastle E08000021, North Tyneside E08000022, Northumberland E06000057, South Tyneside E08000023, Sunderland E08000024 |
| Tees Valley | Darlington E06000005, Hartlepool E06000001, Middlesbrough E06000002, Redcar and Cleveland E06000003, Stockton-on-Tees E06000004 |
| West of England | Bath and North East Somerset E06000022, Bristol E06000023, South Gloucestershire E06000025 |
| Cambridgeshire and Peterborough | Cambridgeshire County E10000003, Cambridge E07000008, East Cambridgeshire E07000009, Fenland E07000010, Huntingdonshire E07000011, Peterborough E06000031, South Cambridgeshire E07000012 |
| York and North Yorkshire | North Yorkshire E06000065, York E06000014 |
| East Midlands | Derby E06000015, Derbyshire County E10000007, Nottingham E06000018, Nottinghamshire County E10000024 |
| Greater Lincolnshire | Lincolnshire County E10000019, North East Lincolnshire E06000012, North Lincolnshire E06000013 |
| Hull and East Yorkshire | Hull E06000010, East Riding of Yorkshire E06000011 |
| Devon and Torbay | Devon County E10000008, Torbay E06000027 |
| Lancashire | Lancashire County E10000017, Blackburn with Darwen E06000008, Blackpool E06000009 |
| Cumbria | Cumberland E06000063, Westmorland and Furness E06000064 |
| Cheshire and Warrington | Cheshire East E06000049, Cheshire West and Chester E06000050, Warrington E06000007 |
| Sussex and Brighton | Brighton and Hove E06000043, East Sussex County E10000011, West Sussex County E10000032 |
| Hampshire and the Solent | Hampshire County E10000014, Isle of Wight E06000046, Portsmouth E06000044, Southampton E06000045 |
| Greater London Authority | No constituent councils: the Mayor and the 25-member London Assembly are elected directly. The 32 boroughs and the City of London are in the same area |

Some authorities also have **non-constituent members** (neighbouring councils, a business board's chair, a police
and crime commissioner), who vote only if the authority resolves so. West Midlands has many; West Yorkshire seats
York and its business board's chair (seen in the attendance of 22 January 2026, below).

### Coming changes

Agreed, not yet established. Both were in the Devolution Priority Programme (February 2025). On 4 December 2025 the
government said it was minded to move their first mayoral elections from May 2026 to **May 2028** ([written statement
HCWS1128](https://questions-statements.parliament.uk/written-statements/detail/2025-12-04/hcws1128)), as for Sussex
and Brighton, and Hampshire and the Solent. Cumbria's and Cheshire and Warrington's moved to May 2027 at their
councils' request.

| Proposed authority | Constituent councils (GSS) | Status, 6 November 2026 |
|---|---|---|
| Greater Essex CCA | Essex County E10000012, Southend-on-Sea E06000033, Thurrock E06000034 | Councils consented to the regulations in 2025. No regulations, made or draft, on legislation.gov.uk (searched 6 November 2026). Wikipedia still calls it planned (edited 25 September 2026). First mayoral election 4 May 2028 |
| Norfolk and Suffolk CCA | Norfolk County E10000020, Suffolk County E10000029 | Councils consented in October 2025. No regulations found (6 November 2026). Its website refused automated requests (Cloudflare check). First mayoral election May 2028 |

In talks. In February 2026 the government asked areas without devolution to propose footprints by 20 March ([LGC, 12
February
2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/new-wave-of-foundation-strategic-authorities-announced-12-02-2026/)).
On 28 October 2026, at the Budget, it said ten devolution deals were in their "final stages" ([LGC, 28 October
2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/ten-devolution-deals-in-final-stages-28-10-2026/)).
None of these is confirmed; dates are the councils' own aims:

| Area | Likely form | Notes (source: LGC, 28 October 2026, unless stated) |
|---|---|---|
| Thames Valley (Oxfordshire, Berkshire unitaries, Swindon) | Mayoral | Proposal spring 2027, shadow authority later in 2027, mayor 2028 (Swindon and Cherwell councils' news) |
| Surrey (East and West Surrey unitaries) | Foundation first | Foundation authority "from next year"; mayoral timetable requested |
| Hertfordshire | Mayoral, single county | |
| Leicester, Leicestershire and Rutland | Mayoral | Leicester City not yet committed |
| Kent and Medway | Mayoral | Depends on local government reorganisation |
| Wessex (BCP, Dorset, Somerset, Wiltshire) | Not stated | "Set to be established" |
| Staffordshire and Stoke-on-Trent | Not stated | |
| Bedford, Central Bedfordshire, Luton, Milton Keynes (or a wider South Midlands) | Not stated | |
| Shropshire and Telford and Wrekin | Not stated | |
| Herefordshire and Worcestershire ("Three Counties") | Not stated | Exploratory |
| Cornwall | Single foundation | Cornwall Council chose to seek this in July 2026 (Wikipedia, [Combined authority](https://en.wikipedia.org/wiki/Combined_authority)) |
| Buckinghamshire | Single foundation | |

Councils joining existing authorities: North Somerset (West of England), Gloucestershire (West of England),
Warwickshire (West Midlands) and Plymouth (Devon and Torbay), all in progress, none confirmed (LGC, February and
October 2026). The government's aim is for every part of England to have a strategic authority by 2028.

### Scotland, Wales and Northern Ireland

| Nation | Nearest equivalent | Comparable? |
|---|---|---|
| Wales | Four **corporate joint committees** (North Wales, Mid Wales, South West Wales, South East Wales/Cardiff Capital Region), set up under the Local Government and Elections (Wales) Act 2021, for strategic planning, regional transport and economic well-being. Members are the council leaders. North Wales's meetings are on Gwynedd's Modern.gov ([19 June 2026](https://democracy.gwynedd.llyw.cymru/ieListDocuments.aspx?MId=5803)); South West Wales's papers are on Neath Port Talbot's | Partly: indirectly elected, no mayor, narrower powers. Readable the same way as a hosted English authority |
| Scotland | No regional tier. City region deal joint committees, regional economic partnerships and seven regional transport partnerships (for example SPT) | No: no mayor and no devolved budget of this kind |
| Northern Ireland | None | No |

## 2. Meetings sites

Checked on 6 November 2026: robots.txt first, then one `GetCommittees` request to the Modern.gov web service, as
`sources/modgov.py` makes it. "Answered" means the web service returned a committee list. Requests from the
development machine can be refused where the site's server is allowed (as with councils, [`DATA.md`](../DATA.md)).

| Authority | Meetings published at | System | robots.txt | Web service | Main meeting (committee title) |
|---|---|---|---|---|---|
| Greater Manchester | [democracy.greatermanchester-ca.gov.uk](https://democracy.greatermanchester-ca.gov.uk) | Modern.gov | Allows | Answered (106 committees) | Greater Manchester Combined Authority |
| West Midlands | [governance.wmca.org.uk](https://governance.wmca.org.uk) | Modern.gov | Allows | Answered (108) | WMCA Board; also "Mayoral Decision" |
| Liverpool City Region | [liverpoolcityregion-ca.moderngov.co.uk](https://liverpoolcityregion-ca.moderngov.co.uk) | Modern.gov | Allows | Answered (218) | Liverpool City Region Combined Authority |
| West Yorkshire | [westyorkshire.moderngov.co.uk](https://westyorkshire.moderngov.co.uk) | Modern.gov | Allows | Answered (22) | Combined Authority Board |
| South Yorkshire | [governance.southyorkshire-ca.gov.uk](https://governance.southyorkshire-ca.gov.uk) | Modern.gov | Allows | Answered (70) | Mayoral Combined Authority Board |
| North East | [northeast-ca.moderngov.co.uk](https://northeast-ca.moderngov.co.uk) | Modern.gov | Allows | Answered (3) | Cabinet |
| West of England | [westofengland-ca.moderngov.co.uk](https://westofengland-ca.moderngov.co.uk) | Modern.gov | Allows | Answered (15) | West of England Combined Authority Committee |
| Cambridgeshire and Peterborough | [cambridgeshirepeterborough-ca.moderngov.co.uk](https://cambridgeshirepeterborough-ca.moderngov.co.uk) | Modern.gov | Allows | Answered (20) | Combined Authority Board; also "Mayor's Question Time" |
| York and North Yorkshire | [yorknorthyorks-ca.moderngov.co.uk](https://yorknorthyorks-ca.moderngov.co.uk) | Modern.gov | Allows | Answered (16) | Cabinet (its meetings were renamed "Cabinet" in 2026; 2024 meetings are on North Yorkshire Council's site and as PDFs on the authority's website) |
| East Midlands | [democracy.eastmidlands-cca.gov.uk](https://democracy.eastmidlands-cca.gov.uk) | Modern.gov | Allows | Answered (15) | East Midlands Combined County Authority Board |
| Greater Lincolnshire | [greaterlincolnshire.moderngov.co.uk](https://greaterlincolnshire.moderngov.co.uk) | Modern.gov | Allows | Answered (11) | Greater Lincolnshire Combined County Authority |
| Devon and Torbay | [democracy.devonandtorbay-cca.gov.uk](https://democracy.devonandtorbay-cca.gov.uk) | Modern.gov | Allows | Answered (8) | Devon and Torbay Combined County Authority Board (some early meetings were also published on Teignbridge's site) |
| Lancashire | [council.lancashire.gov.uk](https://council.lancashire.gov.uk/mgGeneric.aspx?MD=mglancashirecombinedcountyauthority&bcr=1), Lancashire County Council's site | Modern.gov, shared | Allows | Answered (655, the county's) | Lancashire Combined County Authority (also "Shadow Lancashire Combined County Authority") |
| Cheshire and Warrington | [Cheshire West and Chester's site, committee 1166](https://cmttpublic.cheshirewestandchester.gov.uk/ieListMeetings.aspx?CommitteeId=1166), linked from [cheshireandwarrington-ca.gov.uk](https://cheshireandwarrington-ca.gov.uk/) | Modern.gov, shared | Refused (403) | Refused this network (403, Azure gateway); the registry records it answering the site's server | Not confirmed (committee 1166) |
| Sussex and Brighton | [democracy.eastsussex.gov.uk](https://democracy.eastsussex.gov.uk/ieListDocuments.aspx?MId=7117), East Sussex County Council's site | Modern.gov, shared | **Forbids all** (`Disallow: /`) | Not requested | Sussex and Brighton Strategic Authority Board (first met 15 April 2026) |
| Greater London Authority | [meetings.london.gov.uk](https://meetings.london.gov.uk) (London Assembly); Mayor's decisions on [london.gov.uk](https://www.london.gov.uk/who-we-are/governance-and-spending/promoting-good-governance/decision-making/decisions) | Modern.gov; own site (Drupal) | Modern.gov site **forbids all** but Google and Bing; london.gov.uk allows decision pages | Not requested | London Assembly plenary; Mayor's Question Time; Mayoral Decisions |
| Tees Valley | [teesvalley-ca.gov.uk, meetings](https://teesvalley-ca.gov.uk/about/leadership/cabinet-boards-committees/meetings/) | Own site (WordPress), PDFs | Allows | No Modern.gov | Cabinet |
| Hull and East Yorkshire | [hullandeastyorkshire.gov.uk, Executive Board](https://www.hullandeastyorkshire.gov.uk/executive-board) | Own site (directory of PDFs; looks like Jadu) | None (allows) | No Modern.gov | Executive Board |
| Cumbria | [cumbria-ca.gov.uk, meetings](https://www.cumbria-ca.gov.uk/committees/meetings-agendas-and-minutes) | Own site (LocalGov Drupal), a page per meeting | Allows | No Modern.gov | Cumbria Combined Authority Board (first listed meeting 18 March 2026) |
| Hampshire and the Solent | Not found. [hantsandsolent-ca.gov.uk](https://hantsandsolent-ca.gov.uk/) refused automated requests (403). (Later the same day the site answered, and its meetings were found under [Democracy](https://hantsandsolent-ca.gov.uk/banner-test/democracy/): a page each for the board and the overview and scrutiny committee, with agendas and minutes as PDFs; read by `sources/docsite.py`.) First board meeting 13 July 2026 at Southampton Civic Centre ([Portsmouth News](https://www.portsmouth.co.uk/news/politics/hampshire-and-the-solent-combined-county-authority-takes-first-steps-8781495)) | Not confirmed | Refused | Not found | Not confirmed |

Hampshire and the Solent's site answered later the same day. Under decision 21, the robots.txt of the Sussex and
Brighton and GLA sites isn't treated as a barrier. Tees Valley, Hull and East Yorkshire, Cumbria, and Hampshire and
the Solent each publish PDFs on their own pages, with no attendance or party data beyond what the minutes print, and
are read by `sources/docsite.py`.

## 3. The record

### The bodies that decide

| Body | What it does | Comparable to |
|---|---|---|
| **The authority's board** (titled "Combined Authority", "Board", "Cabinet", "Executive Board") | The mayor (if any) and one member from each constituent council, usually its leader, plus non-constituent members. Agrees budgets, strategies, investment and transport decisions | A cabinet, though its members are leaders of different councils, often of different parties |
| **The mayor's decisions** | Functions the law gives the mayor alone: in most mayoral areas transport, the mayoral precept, spatial strategy ([Sch. 2](https://www.legislation.gov.uk/ukpga/2026/23/schedule/2)), and police and fire where the mayor holds those (Greater Manchester, West Yorkshire, South Yorkshire from 2024, York and North Yorkshire). Published as decision notices: West Midlands has a Modern.gov committee titled "Mayoral Decision" (contents not checked); the GLA's are "Mayoral Decisions" on london.gov.uk; others on their websites (not checked one by one) | A cabinet member's individual decision, which decision 3 leaves out |
| **Overview and scrutiny committee** | Required for every combined authority; the Act brings mayoral combined county authorities into the same regime (Schedules [4](https://www.legislation.gov.uk/ukpga/2026/23/schedule/4) and [5](https://www.legislation.gov.uk/ukpga/2026/23/schedule/5)). Members are backbench councillors of the constituent councils, politically balanced across the area | Council scrutiny, which the site doesn't cover |
| **Audit and governance; transport, skills and business boards** | Committees and advisory boards | Not in scope for councils either |
| **London: the Assembly** | 25 directly elected members. Scrutinises the Mayor, questions him at Mayor's Question Time, and can amend his budget or reject his strategies by a two-thirds majority | Partly full council (an elected body that votes), partly scrutiny |

### Voting on decisions

- The default rule (Act [s. 6](https://www.legislation.gov.uk/ukpga/2026/23/section/6), in force 29 April 2026):
  a simple majority of voting members present and voting; in a mayoral authority **the majority must include the
  mayor** (or a deputy acting for the mayor). Each voting member has one vote; there is **no casting vote**, and a
  tie means the motion falls. An authority's own order can say otherwise.
- The mayor's budget. Constituent members can veto it, or amend it, only by a **two-thirds majority** of those
  present and voting (excluding the mayor). Straight after that vote, **the minutes must record the names** of those
  who voted for, against or abstained (Greater Manchester's budget report, [7 February
  2025](https://www.greatermanchester-ca.gov.uk/media/5t2fy4y2/mayoral-general-budget-and-precept.pdf), paragraphs
  1.11–1.12). This is the one named vote the law requires. The instrument behind it is probably the Combined
  Authorities (Finance) Order 2017 (not confirmed).
- Spatial development strategy: majority including the mayor, who has a casting vote (Sch. 2, para 3).
- Recorded votes on request. Some constitutions let any member have their vote recorded (South Yorkshire, [2021
  constitution](https://www.southyorkshire-ca.gov.uk/getattachment/5460570b-415b-49ee-a649-21dbf56c3702/Constitution-September-2021-v1-rev-2.pdf?lang=en-GB);
  Cambridgeshire and Peterborough records its budget vote, 2018).

### Two meetings in the web service

Two requests each (a meeting list and one meeting), 6 November 2026:

- West Yorkshire, Combined Authority Board, 22 January 2026. Minutes text in the web service for every item
  (35,000 characters). Attendance lists each member's role, attendance ("Present, as expected", "Apologies"), party
  code (`LAB`, `GRN`, `LBD`, `CON`) and home council ("Bradford Council"). The board includes opposition councillors
  appointed for political balance, York's two members and the business board's chair (no party). Votes are recorded
  as counts or "unanimously": "For: 8 Against: 0 Abstentions: 2". No names.
- Greater Manchester, 13 February 2026 (the budget meeting). No minutes text in the web service (`minutepublished`
  false nine months later); the minutes are a document on the next meeting's agenda ("4A Draft minutes GMCA 30 January
  2026"), which `documents.py` already finds. Attendance has party and home council, but every member is still
  "Expected": attendance wasn't updated. The members were the mayor and ten leaders: nine Labour, one Liberal Democrat.
  The budget meeting is where the named vote on the mayor's budget would be recorded.

So the parser for named votes would find little: perhaps one vote a year per mayoral authority, and none where the
budget passes without a veto vote. Counts ("8 for, 2 abstentions") could be read and shown, without names.

### Party on the date

- Members are councillors of other councils. The party shown in the authority's own attendance is the authority's
  record, which can lag a defection. The home council's attendance, which the site already loads for 66 of 82
  constituent councils, is the better source. Matching needs the member's name and home council (the `representing`
  field), since Modern.gov's member ids differ between sites.
- Mayors have the party they stood for. A mayor isn't a councillor of any constituent council.
- Non-councillor members (business board chairs, independent persons, police and crime panel members) have no
  party. Decision 9 limits pages to councillors' words and actions; decision 20 settled that they are counted but
  not named.

## Sources

Legislation and government: [English Devolution and Community Empowerment Act
2026](https://www.legislation.gov.uk/ukpga/2026/23/contents); the instruments linked in the table; [written statement
HCWS1128, 4 December 2025](https://questions-statements.parliament.uk/written-statements/detail/2025-12-04/hcws1128);
[GOV.UK, English devolution area
factsheets](https://www.gov.uk/government/publications/english-devolution-area-factsheets/english-devolution-area-factsheets)
(10 July 2025); [GOV.UK, EMSA designation criteria and evidence
guidance](https://www.gov.uk/government/publications/established-mayoral-strategic-authority-designation-criteria-and-evidence-guidance)
(6 May 2026). Codes: [ONS lookup, LAD to combined authority, May
2025](https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD25_CAUTH25_EN_LU/FeatureServer/0); [MHCLG
local-authority register](https://files.planning.data.gov.uk/dataset/local-authority.csv). Secondary: [Ward Hadaway
on the four new
EMSAs](https://www.wardhadaway.com/insights/updates/four-mayoral-strategic-authorities-secure-established-status/);
[LGC, 12 February
2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/new-wave-of-foundation-strategic-authorities-announced-12-02-2026/)
and [28 October
2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/devo-discussions-the-possible-new-strategic-authorities-28-10-2026/);
Wikipedia ([Strategic authority](https://en.wikipedia.org/wiki/Strategic_authority), [Metro
mayor](https://en.wikipedia.org/wiki/Metro_mayor), [Devolution Priority
Programme](https://en.wikipedia.org/wiki/Devolution_Priority_Programme)), used only where marked. Meetings sites:
each authority's own site and web service, as linked in section 2.
