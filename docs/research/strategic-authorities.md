# Strategic authorities: what exists, where their records are, and how the site could cover them

Research note, 6 November 2026. Asked for by a user organisation that wants coverage of England's strategic
authorities "as they scramble to understand them in the run-up to greater devolution". Nothing here changes the site:
it sets out the facts, the options and the decisions the owner would need to make. Today the site leaves combined
authorities out ([`DATA.md`](../DATA.md): "Combined authorities are left out"), although the Greater London
Authority is already listed (below, "One thing already wrong").

Every fact carries a date. "Not confirmed" means I couldn't find it in a primary source. Requests to the authorities'
own sites were made on 6 November 2026 from a cloud network (not the site's server), with the user agent
`WhereCouncilsStand-research (+https://wherecouncilsstand.com)`, after reading each site's robots.txt.

## In short

- **20 strategic authorities exist** (6 November 2026): 13 combined authorities, 6 combined county authorities and
  the Greater London Authority. 14 have a mayor. Two more (Greater Essex; Norfolk and Suffolk) are agreed but not yet
  established, and about a dozen more areas are in talks.
- **13 can be read by the site's existing Modern.gov reader today**: 12 on their own Modern.gov sites, and
  Lancashire's on Lancashire County Council's. A 14th (Cheshire and Warrington, on Cheshire West and Chester's site)
  probably can from the site's server, but refused this network. Two more are on Modern.gov sites whose robots.txt
  forbids all crawling (the GLA, and Sussex and Brighton on East Sussex's site). Three publish on their own web pages
  (Tees Valley, Hull and East Yorkshire, Cumbria), and one (Hampshire and the Solent) I couldn't find.
- **The record is thinner than a council's.** Boards are small (often 5–15 voting members), mostly vote by consensus,
  and few minutes name how members voted. The one named vote the law requires is on the mayor's budget. Attendance
  in Modern.gov carries each member's party and home council.
- **Recommended pilot:** the main decision-making meeting of the 13 readable authorities, chosen by that rule alone,
  from May 2018 or their creation. Shown on their own pages and kept out of briefings' "party in control" grouping
  until the owner decides how to treat a mayor.

## 1. What exists now, and what is coming

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

- **EMSAs.** Greater Manchester, West Midlands, Liverpool City Region, North East, South Yorkshire, West Yorkshire
  and the GLA were named as established from Royal Assent ([GOV.UK area factsheets](https://www.gov.uk/government/publications/english-devolution-area-factsheets/english-devolution-area-factsheets),
  10 July 2025). On **31 July 2026** the Cabinet Office announced four more: Cambridgeshire and Peterborough, East
  Midlands, West of England, and York and North Yorkshire ([Ward Hadaway](https://www.wardhadaway.com/insights/updates/four-mayoral-strategic-authorities-secure-established-status/)).
  I couldn't find the designation regulations, so whether they are in force is not confirmed.
- **Mayors** are again elected by the supplementary vote ([s. 63](https://www.legislation.gov.uk/ukpga/2026/23/section/63)),
  and an MP can't be a mayor ([s. 17](https://www.legislation.gov.uk/ukpga/2026/23/section/17)).

### The 20 authorities (6 November 2026)

GSS codes for combined and combined county authorities are ONS's `E47` codes, from ONS's
[local authority district to combined authority lookup (May 2025)](https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD25_CAUTH25_EN_LU/FeatureServer/0)
and MHCLG's [local-authority register](https://files.planning.data.gov.uk/dataset/local-authority.csv) (type `COMB`).
Neither had codes for the four authorities created in 2026 when checked on 6 November 2026. Mayors are from
[Wikipedia's list](https://en.wikipedia.org/wiki/Metro_mayor) (as of June 2026) and the Greater Manchester by-election
result below; their parties are as elected.

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

- **Greater Manchester.** Andy Burnham was elected MP for Makerfield on 18 June 2026, which vacated the mayoralty.
  Bev Craig, until then leader of Manchester City Council, won the by-election on 30 July 2026
  ([Stockport Council, results](https://www.stockport.gov.uk/news/greater-manchester-mayoral-election-results-2026)).
- **"Created" dates** for the 2025 authorities are from Wikipedia ([Strategic authority](https://en.wikipedia.org/wiki/Strategic_authority));
  the instruments are linked.
- **Tees Valley** couldn't apply for EMSA status while under a Best Value Notice (GOV.UK factsheets, 10 July 2025).
- **The North East** is legally the North East Mayoral Combined Authority; it calls itself the North East Combined
  Authority. Its predecessors, the North East and North of Tyne combined authorities (E47000010, E47000011), were
  dissolved on 6–7 May 2024 (MHCLG register).

### Constituent councils, and whether the site already reads them

Constituent councils appoint the authority's voting members. GSS codes match `data_static/councils.csv`. "Loaded"
is from the live site's `/api/councils` on 6 November 2026. ONS's lookup lists every district in an area, but in a
two-tier area the constituent council is the county (Devon County Council, not Teignbridge), except in Cambridgeshire
and Peterborough, where the districts are constituent too.

| Authority | Constituent councils (GSS) | Loaded on the site |
|---|---|---|
| Greater Manchester | Bolton E08000001, Bury E08000002, Manchester E08000003, Oldham E08000004, Rochdale E08000005, Salford E08000006, Stockport E08000007, Tameside E08000008, Trafford E08000009, Wigan E08000010 | 10 of 10 |
| Liverpool City Region | Halton E06000006, Knowsley E08000011, Liverpool E08000012, St Helens E08000013, Sefton E08000014, Wirral E08000015 | 5 of 6 (not Sefton) |
| West Yorkshire | Bradford E08000032, Calderdale E08000033, Kirklees E08000034, Leeds E08000035, Wakefield E08000036 | 5 of 5 |
| South Yorkshire | Barnsley E08000038, Doncaster E08000017, Rotherham E08000018, Sheffield E08000039 | 4 of 4 |
| West Midlands | Birmingham E08000025, Coventry E08000026, Dudley E08000027, Sandwell E08000028, Solihull E08000029, Walsall E08000030, Wolverhampton E08000031 | 3 of 7 (Birmingham, Dudley and Walsall are on CMIS sites that forbid crawling; Solihull unreachable) |
| North East | Durham E06000047, Gateshead E08000037, Newcastle E08000021, North Tyneside E08000022, Northumberland E06000057, South Tyneside E08000023, Sunderland E08000024 | 6 of 7 (not South Tyneside) |
| Tees Valley | Darlington E06000005, Hartlepool E06000001, Middlesbrough E06000002, Redcar and Cleveland E06000003, Stockton-on-Tees E06000004 | 4 of 5 (not Hartlepool) |
| West of England | Bath and North East Somerset E06000022, Bristol E06000023, South Gloucestershire E06000025 | 3 of 3 |
| Cambridgeshire and Peterborough | Cambridgeshire County E10000003, Cambridge E07000008, East Cambridgeshire E07000009, Fenland E07000010, Huntingdonshire E07000011, Peterborough E06000031, South Cambridgeshire E07000012 | 4 of 7 |
| York and North Yorkshire | North Yorkshire E06000065, York E06000014 | 2 of 2 |
| East Midlands | Derby E06000015, Derbyshire County E10000007, Nottingham E06000018, Nottinghamshire County E10000024 | 3 of 4 (not Derby) |
| Greater Lincolnshire | Lincolnshire County E10000019, North East Lincolnshire E06000012, North Lincolnshire E06000013 | 2 of 3 |
| Hull and East Yorkshire | Hull E06000010, East Riding of Yorkshire E06000011 | 0 of 2 |
| Devon and Torbay | Devon County E10000008, Torbay E06000027 | 2 of 2 |
| Lancashire | Lancashire County E10000017, Blackburn with Darwen E06000008, Blackpool E06000009 | 3 of 3 |
| Cumbria | Cumberland E06000063, Westmorland and Furness E06000064 | 2 of 2 |
| Cheshire and Warrington | Cheshire East E06000049, Cheshire West and Chester E06000050, Warrington E06000007 | 2 of 3 (not Warrington) |
| Sussex and Brighton | Brighton and Hove E06000043, East Sussex County E10000011, West Sussex County E10000032 | 3 of 3 |
| Hampshire and the Solent | Hampshire County E10000014, Isle of Wight E06000046, Portsmouth E06000044, Southampton E06000045 | 3 of 4 (not Southampton) |
| Greater London Authority | No constituent councils: the Mayor and the 25-member London Assembly are elected directly. The 32 boroughs and the City of London are in the same area | Not counted |

Across the 19 combined and combined county authorities, 66 of 82 constituent councils are loaded (80%).

Some authorities also have **non-constituent members** (neighbouring councils, a business board's chair, a police
and crime commissioner), who vote only if the authority resolves so. West Midlands has many; West Yorkshire seats
York and its business board's chair (seen in the attendance of 22 January 2026, below).

### What is coming

**Agreed, not yet established.** Both were in the Devolution Priority Programme (February 2025). On 4 December 2025
the government said it was minded to move their first mayoral elections from May 2026 to **May 2028**
([written statement HCWS1128](https://questions-statements.parliament.uk/written-statements/detail/2025-12-04/hcws1128)),
as for Sussex and Brighton, and Hampshire and the Solent. Cumbria's and Cheshire and Warrington's moved to May 2027
at their councils' request.

| Proposed authority | Constituent councils (GSS) | Status, 6 November 2026 |
|---|---|---|
| Greater Essex CCA | Essex County E10000012, Southend-on-Sea E06000033, Thurrock E06000034 | Councils consented to the regulations in 2025. No regulations, made or draft, on legislation.gov.uk (searched 6 November 2026). Wikipedia still calls it planned (edited 25 September 2026). First mayoral election 4 May 2028 |
| Norfolk and Suffolk CCA | Norfolk County E10000020, Suffolk County E10000029 | Councils consented in October 2025. No regulations found (6 November 2026). Its website refused automated requests (Cloudflare check). First mayoral election May 2028 |

**In talks.** In February 2026 the government asked areas without devolution to propose footprints by 20 March
([LGC, 12 February 2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/new-wave-of-foundation-strategic-authorities-announced-12-02-2026/)).
On 28 October 2026, at the Budget, it said ten devolution deals were in their "final stages"
([LGC, 28 October 2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/ten-devolution-deals-in-final-stages-28-10-2026/)).
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

## 2. Where each authority's meetings are published

Checked on 6 November 2026: robots.txt first, then one `GetCommittees` request to the Modern.gov web service, as
`sources/modgov.py` makes it. "Answered" means the web service returned a committee list. Requests from this network
can be refused where the site's server is allowed (as with councils, [`DATA.md`](../DATA.md)).

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
| Hampshire and the Solent | Not found. [hantsandsolent-ca.gov.uk](https://hantsandsolent-ca.gov.uk/) refused automated requests (403). First board meeting 13 July 2026 at Southampton Civic Centre ([Portsmouth News](https://www.portsmouth.co.uk/news/politics/hampshire-and-the-solent-combined-county-authority-takes-first-steps-8781495)) | Not confirmed | Refused | Not found | Not confirmed |

What this means:

- **13 readable now** with `sources/modgov.py` (12 own sites, plus Lancashire's on the county's). **14** if Cheshire
  and Warrington answers the server as Cheshire West and Chester does.
- **2 behind a robots.txt that forbids crawling**: the GLA's Modern.gov site and East Sussex's. Under decision 2's
  approach (sites that refuse the crawler are asked, not worked around) these would need the GLA's and East Sussex's
  agreement. **But the site already loads East Sussex County Council**: `sources/modgov.py` doesn't read robots.txt,
  only the CMIS and CoINS readers do. Decision 2 states the rule only for CMIS. The owner should say whether it applies
  to Modern.gov sites too (below, decisions).
- **3 need a reader of their own** (Tees Valley, Hull and East Yorkshire, Cumbria): each publishes PDFs on its own
  pages, so each would be a small scraper plus `documents.py`, with no attendance or party data beyond what the
  minutes print.
- **Third-party coverage.** Open Council Network ([opencouncil.network](https://opencouncil.network/councils/cambridgeshire-and-peterborough-combined-authority))
  already lists some combined authorities' meetings and members. Not assessed.

### One thing already wrong

The registry already holds the **Greater London Authority** (`E12000007`, row 106 of `councils.csv`), because MHCLG's
register lists it as type `SRA` (strategic regional authority), and `build_councils.py` maps `SRA` to
`isles_of_scilly`. The live site's `/api/councils/E12000007` shows it as type "Council of the Isles of Scilly", not
loaded (6 November 2026). The Isles of Scilly themselves are a unitary (`UA`) in the register. So the site's 383
"councils" are 382 councils and the GLA, and the GLA's page is mislabelled. Its key is London's region code, which is
also its `region`. Whatever the owner decides, the label should be fixed.

## 3. What the record looks like, and what matters

### The bodies that decide

| Body | What it does | Comparable to |
|---|---|---|
| **The authority's board** (titled "Combined Authority", "Board", "Cabinet", "Executive Board") | The mayor (if any) and one member from each constituent council, usually its leader, plus non-constituent members. Agrees budgets, strategies, investment and transport decisions | A cabinet, though its members are leaders of different councils, often of different parties |
| **The mayor's decisions** | Functions the law gives the mayor alone: in most mayoral areas transport, the mayoral precept, spatial strategy ([Sch. 2](https://www.legislation.gov.uk/ukpga/2026/23/schedule/2)), and police and fire where the mayor holds those (Greater Manchester, West Yorkshire, South Yorkshire from 2024, York and North Yorkshire). Published as decision notices: West Midlands has a Modern.gov committee titled "Mayoral Decision" (contents not checked); the GLA's are "Mayoral Decisions" on london.gov.uk; others on their websites (not checked one by one) | A cabinet member's individual decision, which decision 3 leaves out |
| **Overview and scrutiny committee** | Required for every combined authority; the Act brings mayoral combined county authorities into the same regime (Schedules [4](https://www.legislation.gov.uk/ukpga/2026/23/schedule/4) and [5](https://www.legislation.gov.uk/ukpga/2026/23/schedule/5)). Members are backbench councillors of the constituent councils, politically balanced across the area | Council scrutiny, which the site doesn't cover |
| **Audit and governance; transport, skills and business boards** | Committees and advisory boards | Not in scope for councils either |
| **London: the Assembly** | 25 directly elected members. Scrutinises the Mayor, questions him at Mayor's Question Time, and can amend his budget or reject his strategies by a two-thirds majority | Partly full council (an elected body that votes), partly scrutiny |

### How decisions are voted

- **The default rule** (Act [s. 6](https://www.legislation.gov.uk/ukpga/2026/23/section/6), in force 29 April 2026):
  a simple majority of voting members present and voting; in a mayoral authority **the majority must include the
  mayor** (or a deputy acting for the mayor). Each voting member has one vote; there is **no casting vote**, and a
  tie means the motion falls. An authority's own order can say otherwise.
- **The mayor's budget.** Constituent members can veto it, or amend it, only by a **two-thirds majority** of those
  present and voting (excluding the mayor). Straight after that vote, **the minutes must record the names** of those
  who voted for, against or abstained (Greater Manchester's budget report, [7 February 2025](https://www.greatermanchester-ca.gov.uk/media/5t2fy4y2/mayoral-general-budget-and-precept.pdf),
  paragraphs 1.11–1.12). This is the one named vote the law requires. The instrument behind it is probably the
  Combined Authorities (Finance) Order 2017 (not confirmed).
- **Spatial development strategy:** majority including the mayor, who has a casting vote (Sch. 2, para 3).
- **Recorded votes on request.** Some constitutions let any member have their vote recorded (South Yorkshire,
  [2021 constitution](https://www.southyorkshire-ca.gov.uk/getattachment/5460570b-415b-49ee-a649-21dbf56c3702/Constitution-September-2021-v1-rev-2.pdf?lang=en-GB);
  Cambridgeshire and Peterborough records its budget vote, 2018).

### What two meetings look like in the web service

Two requests each (a meeting list and one meeting), 6 November 2026:

- **West Yorkshire, Combined Authority Board, 22 January 2026.** Minutes text in the web service for every item
  (35,000 characters). Attendance lists each member's role, attendance ("Present, as expected", "Apologies"), party
  code (`LAB`, `GRN`, `LBD`, `CON`) and home council ("Bradford Council"). The board includes opposition councillors
  appointed for political balance, York's two members and the business board's chair (no party). Votes are recorded
  as counts or "unanimously": "For: 8 Against: 0 Abstentions: 2". No names.
- **Greater Manchester, 13 February 2026 (the budget meeting).** No minutes text in the web service (`minutepublished`
  false nine months later); the minutes are a document on the next meeting's agenda ("4A Draft minutes GMCA 30 January
  2026"), which `documents.py` already finds. Attendance has party and home council, but every member is still
  "Expected": attendance wasn't updated. The members were the mayor and ten leaders: nine Labour, one Liberal Democrat.
  The budget meeting is where the named vote on the mayor's budget would be recorded.

So the parser for named votes would find little: perhaps one vote a year per mayoral authority, and none where the
budget passes without a veto vote. Counts ("8 for, 2 abstentions") could be read and shown, without names.

### Party on the date

- **Members are councillors of other councils.** The party shown in the authority's own attendance is the authority's
  record, which can lag a defection. The home council's attendance, which the site already loads for 66 of 82
  constituent councils, is the better source. Matching needs the member's name and home council (the `representing`
  field), since Modern.gov's member ids differ between sites.
- **Mayors** have the party they stood for. A mayor isn't a councillor of any constituent council.
- **Non-councillor members** (business board chairs, independent persons, police and crime panel members) have no
  party. Decision 9 limits pages to councillors' words and actions; these members are public office-holders, so the
  owner should say whether they are named.

## 4. Options for the site

### What "control" means for an authority

Decision 12 groups briefing evidence by the party in overall control, read from full council attendance. That
doesn't transfer:

- A **mayoral** authority can't decide anything without the mayor in the majority, so the mayor's party is the
  closest thing to control. But the board's leaders may be of other parties (Greater Lincolnshire: a Reform UK mayor;
  its constituent councils' leaders were not all Reform UK, not checked).
- A **non-mayoral** authority decides by simple majority of members, one per constituent council (Devon and Torbay:
  two; Lancashire: three). "Control" by more than half of three members is not meaningful.
- The **GLA**: the Mayor decides; the Assembly can block with two-thirds. Labour holds 11 of 25 Assembly seats
  (May 2024 election; not checked against the GLA's own pages), so the Assembly is in no overall control.

The plainest choice: record **"Mayor: party"** (on the date) for mayoral authorities, and **"Board: parties of the
members"** as recorded, and don't compute "overall control" for authorities. Briefings would group authorities on
their own ("strategic authorities"), by the mayor's party when asked, never mixed into the councils' control groups.

### Pages and links

- **An authority page** like a council page: kind and category on the date, mayor and party over time, constituent
  councils with links to their pages, board members on the date, meetings, any named votes.
- **Each council page** gains a line: "Part of the West Yorkshire Combined Authority (since 1 April 2014)", linking
  to it, and, where its leader sits on the board, the dates.
- **Membership changes over time** (Cumbria from 2026; North Somerset joining the West of England; local government
  reorganisation abolishing Essex, Norfolk, Suffolk, Hampshire and Sussex's councils in 2026–28), so the link must be
  dated: a small `data_static/strategic_authorities.csv` with authority, council GSS, from and to.

### Filters

| Filter | Councils today | Authorities |
|---|---|---|
| Nation | England, Wales, Scotland, Northern Ireland | England only |
| Region | One region each | Mostly one, but **Greater Lincolnshire spans two** (Lincolnshire in the East Midlands; North and North East Lincolnshire in Yorkshire and the Humber). Region would have to allow several, or be left blank |
| Kind | County, district, unitary… | A new kind, "strategic authority", with its category (foundation, mayoral, established mayoral) on the date |
| Control | Party in overall control | Mayor's party, or none (above) |

### The options

| Option | What is added | Readers | Rough effort | For | Against |
|---|---|---|---|---|---|
| **(a) Boards** | Each authority as a new kind of record, with its main meeting (board or cabinet), including budget meetings. Optionally the mayor's decisions | Modern.gov for 13 (14); three small readers for the own-site authorities later | 3–5 days for the 13: registry rows and keys, `committees.csv` entries (none of the main meetings' titles match `committees.py`, except the North East's and York and North Yorkshire's "Cabinet"), a shared-site rule for Lancashire and Cheshire and Warrington (as for Babergh and Mid Suffolk), linking members to home councils, the page. Mayor's decisions: 1 day for West Midlands (Modern.gov), 1–3 days each elsewhere | Answers the request directly; the main decisions are there; the readers exist | Few named votes; small boards mean briefings will often have one or two items per authority; party of non-councillor members |
| **(b) Plus scrutiny** | Overview and scrutiny committees | Same | About 1 day more | Shows challenge to the mayor; cross-party members | Decision 3 leaves council scrutiny out, so authorities would get more than councils; scrutiny rarely decides anything |
| **(c) Plus the GLA** | The London Assembly's plenary and Mayor's Question Time, the Mayor's decisions | Modern.gov (if the GLA agrees to the crawler); a new reader for london.gov.uk's decision pages | 2–4 days, after the GLA's agreement | London is the biggest and best-known strategic authority; the Assembly takes named votes (not confirmed how often) | Its Modern.gov site forbids crawling; it is unlike the others (a directly elected assembly, no constituent councils) |

### Risks

- **Fast change.** Eight authorities were created in the past 21 months; two more are agreed; about a dozen are in
  talks; four mayoralties begin in 2027–28. The registry would need checking each quarter, by hand, against
  legislation.gov.uk.
- **Names change.** "Combined county authority" vs "strategic authority" (Sussex and Brighton uses the latter);
  "North East Combined Authority" vs its legal name; York and North Yorkshire renamed its meetings "Cabinet" in 2026.
  Keys must not depend on names. ONS codes come late (none yet for 2026's four).
- **Records move.** York and North Yorkshire's early meetings are on North Yorkshire Council's site; Devon and
  Torbay's first on Teignbridge's; Cheshire and Warrington's shadow board on two councils' sites. The rule "the
  authority's own record from its creation" will have gaps that need saying on each page.
- **Constituent councils disappear.** Reorganisation will abolish county and district councils in several areas
  between 2026 and 2028; their pages and the authority's links need end dates.
- **Balance.** 10 of the 14 mayors are Labour or Labour and Co-operative, two Conservative, two Reform UK. Any
  selection should be by a stated rule, not by party, as the councils' pilot was.
- **Expectation.** Users "scrambling to understand them" may expect explanation of powers and funding. The site
  reports what the minutes record; a short, sourced "what this authority is" panel would help but is new writing to
  maintain.

## 5. Recommendation

### A pilot

- **Which authorities:** by one rule, as the councils' pilot was: **every strategic authority whose meetings are on a
  Modern.gov web service that answers and whose robots.txt allows it**. That is 13 today: Greater Manchester, West
  Midlands, Liverpool City Region, West Yorkshire, South Yorkshire, North East, West of England, Cambridgeshire and
  Peterborough, York and North Yorkshire, East Midlands, Greater Lincolnshire, Devon and Torbay, and Lancashire
  (Cheshire and Warrington too if it answers the server). The rule happens to include Labour, Conservative and Reform
  UK mayors and two non-mayoral authorities.
- **Which meetings:** the main decision-making meeting only (option a), all meetings including budget ones, from May
  2018 or the authority's creation, whichever is later. Not scrutiny, committees or advisory boards. Mayor's decisions
  for West Midlands only, as a test of whether they're worth adding.
- **What to measure:** meetings and minutes found by year; how many named votes and counted votes; how many members
  match a home-council councillor; time and requests.
- **How to show them:** on their own pages and the council pages' links, but **not in briefings** until the owner has
  decided how they are grouped. Then as their own group.
- **Then:** ask the GLA and East Sussex about their robots.txt; write readers for Tees Valley, Hull and East
  Yorkshire and Cumbria if the pilot is worth keeping.

### What the owner must decide

1. **Whether to cover strategic authorities** (decision 2 covers principal councils only), and what to call them on
   the site ("strategic authorities", the legal term since 29 April 2026).
2. **Which meetings** (decision 3 for councils): the board or cabinet; the mayor's decisions (individual decisions are
   left out for councils); scrutiny.
3. **The GLA:** in or out; and if in, whether to ask the GLA to allow the crawler. Either way, its "Council of the
   Isles of Scilly" label should be fixed.
4. **Control:** whether an authority is grouped by its mayor's party, by its board's parties, or not at all; and
   whether authorities appear in briefings by default or only when asked.
5. **Robots.txt on Modern.gov sites:** whether decision 2's rule (sites whose robots.txt forbids crawling are left out
   and asked) applies to Modern.gov sites as well as CMIS. It affects East Sussex today, and Sussex and Brighton and the
   GLA if covered.
6. **Non-councillor members:** whether business board chairs and other appointed members are named in votes and
   attendance (decision 9).
7. **Keys and dates:** ONS `E47` codes where they exist; a stated, provisional key for the newest authorities; coverage
   from May 2018 or creation.

### Decisions to record in `docs/DECISIONS.md` if approved

Suggested wording, numbered after the current 16:

| # | Topic | Decision |
|---|---|---|
| 17 | Strategic authorities | England's **strategic authorities** (combined authorities, combined county authorities and, if agreed, the Greater London Authority) are covered as a separate kind of record, alongside councils, where their meetings are published through a reader the site has and the site allows crawling. Each is keyed by its ONS code, or a stated provisional key until ONS publishes one. Its page links to its constituent councils, with dates. |
| 18 | Strategic authorities' meetings | The authority's **main decision-making meeting** (its board, "Combined Authority" or cabinet), including budget meetings, from **May 2018 or the authority's creation**, whichever is later. [Mayor's decisions: in / out.] [Overview and scrutiny: in / out.] |
| 19 | Mayors and control | An authority isn't given a "party in control". Its page shows the **mayor's party on the date**, where there is a mayor, and the parties of its board members as recorded. Briefings group authorities on their own, by the mayor's party when asked, never with councils' control groups. |
| 20 | Members' party | A board member's party on the date is taken from their **home council's** record where the site has it, otherwise from the authority's; appointed members who aren't councillors are [named / not named]. |
| 21 | Robots.txt | [A Modern.gov site whose robots.txt forbids crawling is treated as a CMIS one: left out, and the council or authority is asked.] |

## Sources

Legislation and government: [English Devolution and Community Empowerment Act 2026](https://www.legislation.gov.uk/ukpga/2026/23/contents);
the instruments linked in the table; [written statement HCWS1128, 4 December 2025](https://questions-statements.parliament.uk/written-statements/detail/2025-12-04/hcws1128);
[GOV.UK, English devolution area factsheets](https://www.gov.uk/government/publications/english-devolution-area-factsheets/english-devolution-area-factsheets)
(10 July 2025); [GOV.UK, EMSA designation criteria and evidence guidance](https://www.gov.uk/government/publications/established-mayoral-strategic-authority-designation-criteria-and-evidence-guidance)
(6 May 2026). Codes: [ONS lookup, LAD to combined authority, May 2025](https://services1.arcgis.com/ESMARspQHYMw9BZ9/arcgis/rest/services/LAD25_CAUTH25_EN_LU/FeatureServer/0);
[MHCLG local-authority register](https://files.planning.data.gov.uk/dataset/local-authority.csv). Secondary:
[Ward Hadaway on the four new EMSAs](https://www.wardhadaway.com/insights/updates/four-mayoral-strategic-authorities-secure-established-status/);
[LGC, 12 February 2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/new-wave-of-foundation-strategic-authorities-announced-12-02-2026/)
and [28 October 2026](https://www.lgcplus.com/politics/devolution-and-economic-growth/devo-discussions-the-possible-new-strategic-authorities-28-10-2026/);
Wikipedia ([Strategic authority](https://en.wikipedia.org/wiki/Strategic_authority), [Metro mayor](https://en.wikipedia.org/wiki/Metro_mayor),
[Devolution Priority Programme](https://en.wikipedia.org/wiki/Devolution_Priority_Programme)), used only where marked.
Meetings sites: each authority's own site and web service, as linked in section 2.
