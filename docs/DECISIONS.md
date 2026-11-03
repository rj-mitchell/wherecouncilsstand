# Decisions

Product decisions made by the owner. They override anything else in this repo. Add new decisions here once they're
made.

| # | Topic | Decision |
|---|---|---|
| 1 | Name and owner | **Where Councils Stand**, a project of the charity Where They Stand from day one, with its own domain. Listed under "Planned" in the Charity Commission application. |
| 2 | Coverage | Principal councils in **England and Wales** whose minutes are published through Civica's **Modern.gov**. Councils on other systems are left out for now; the reason is published. Scotland and Northern Ireland are out of scope. |
| 3 | Meetings | **Full council and cabinet** (or executive), including annual, budget and extraordinary council meetings and a mayor and cabinet. Not cabinet sub-committees, advisory panels or decisions by individual cabinet members. For councils run under a committee system, which have no cabinet: the committees their constitution gives the main policy and budget decisions, usually a policy and resources committee (`committees.py`, and `data_static/committees.csv` where a council's are named otherwise). A council that changed systems keeps whichever committees it had at the time. |
| 4 | How far back | **May 2018** for every council, so coverage is even. Each council's page shows its own coverage dates. Extending back to **25 February 2014**, when English councils had to start recording named budget votes, is the next step. |
| 5 | First users | Independent journalists and engaged members of the public. |
| 6 | Code | A new repo, adapted from Where Countries Stand, itself adapted from Where They Stand (same licence, same author). |
| 7 | Neutral wording | Where They Stand's impartiality rules apply. Minutes are officers' summaries, not verbatim records: briefings say "the minutes record that…" and never present a summary as a councillor's own words. |
| 8 | Party on the date | Each councillor is shown with the party recorded at that meeting, mapped to one code per party. Named local groups of independents or residents are local parties, not "Independent". |
| 9 | People named in council records | Briefings and pages are limited to councillors' own words and actions. Members of the public (speakers, petitioners, planning applicants and objectors) and council staff are not identified. Licensing hearings are not included. There is a published route for taking things down. |
| 10 | Reuse | Facts (votes, attendance, declarations, decisions) are extracted and published. Minutes are indexed in full but shown only as cited extracts linking to the council's own record. Each council's licence statement is recorded as it is added. |
| 11 | Being a good citizen | One request at a time to each council, at least a second apart, with an identifying user agent. Responses are cached so each meeting is fetched once. |
| 12 | Grouping evidence | Briefings group councils by facts recorded on the date, the same way for every party: by default the party in overall control (a party with more than half the members at full council), or no overall control; by region, kind of council or council when asked. Evidence is drawn from each group in turn, at most two items per council. |
| 13 | Default period | Briefings default to the last four years (the current council term), with an obvious control to widen it back to May 2018. |
| 14 | Models | As the sibling sites: Claude Sonnet 5.5 writes briefings, Claude Haiku 5.5 reads the question into filters, with server-side fallbacks on. |
