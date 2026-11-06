# Decisions

Product decisions made by the owner. They override anything else in this repo. Add new decisions here once they're
made.

| # | Topic | Decision |
|---|---|---|
| 1 | Name and owner | **Where Councils Stand**, a Where They Stand project from day one, with its own domain. Listed under "In development" in the Charity Commission application. |
| 2 | Coverage | Principal councils across the **UK**: England, Wales, and (the owner's decision, 5 November 2026) **Scotland and Northern Ireland**, whose minutes are published through Civica's **Modern.gov**, Civica's **CMIS** or Northgate's **CoINS** (CMIS and CoINS readers added at the owner's request, 5 November 2026). Councils on other systems are left out for now; the reason is published. CMIS sites whose robots.txt forbids crawling (every Civica-hosted one) are left out, and sites that refuse the crawler are asked, not worked around. |
| 3 | Meetings | **Full council and cabinet** (or executive), including annual, budget and extraordinary council meetings and a mayor and cabinet. Not cabinet sub-committees, advisory panels or decisions by individual cabinet members. For councils run under a committee system, which have no cabinet: the committees their constitution gives the main policy and budget decisions, usually a policy and resources committee (`committees.py`, and `data_static/committees.csv` where a council's are named otherwise). A council that changed systems keeps whichever committees it had at the time. |
| 4 | How far back | **May 2018** for every council, so coverage is even. Each council's page shows its own coverage dates. Extending back to **25 February 2014**, when English councils had to start recording named budget votes, is the next step. |
| 5 | First users | Independent journalists and engaged members of the public. |
| 6 | Code | A new repo. Adapted from Where Countries Stand's and Where MPs Stand's code (same licence). |
| 7 | Neutral wording | The charity's impartiality policy applies. Minutes are officers' summaries, not verbatim records: briefings say "the minutes record that…" and never present a summary as a councillor's own words. |
| 8 | Party on the date | Each councillor is shown with the party recorded at that meeting, mapped to one code per party. Named local groups of independents or residents are local parties, not "Independent". |
| 9 | People named in council records | Briefings and pages are limited to councillors' own words and actions. Members of the public (speakers, petitioners, planning applicants and objectors) and council staff are not identified. Licensing hearings are not included. There is a published route for taking things down. |
| 10 | Reuse | Facts (votes, attendance, declarations, decisions) are extracted and published. Minutes are indexed in full but shown only as cited extracts linking to the council's own record. Each council's licence statement is recorded as it is added. |
| 11 | Being a good citizen | One request at a time to each council, at least a second apart, with an identifying user agent. Responses are cached so each meeting is fetched once. |
| 12 | Grouping evidence | Briefings group councils by facts recorded on the date, the same way for every party: by default the party in overall control (a party with more than half the members at full council), or no overall control; by region, kind of council or council when asked. Evidence is drawn from each group in turn, at most two items per council. |
| 13 | Default period | Briefings default to the last four years (the current council term), with an obvious control to widen it back to May 2018. |
| 14 | Models | As the sibling sites: Claude Sonnet 5.5 writes briefings, Claude Haiku 5.5 reads the question into filters, with server-side fallbacks on. |
| 15 | Vote accuracy in the alpha | About 1 named vote in 100 with a councillor on the wrong side (`docs/PILOT.md`, three samples of 100) is **accepted for the alpha** (6 November 2026, family plan decision 12). The methodology page says so plainly, with the figures. A test set of checked votes is built before the beta. |
| 16 | The mark | A **town hall** (clock tower, pediment, four columns and a gilt step) on a rounded Buckram-brown tile with a fine gilt edge in `#D9BC72`, in the manner of Where MPs Stand's mark. Chosen by the owner on 6 November 2026 from seven drawings (an open minute book, a closed minute book, the council chamber, a gavel, a named vote, the town hall, and sealed minutes). It must stay distinct from Where Landlords Stand's mark. `docs/DESIGN.md`, "The mark". |
