# Documentation

An index of Where Councils Stand's documents, with what each is for and who it is for. Start with the
[README](../README.md) for what the site is and how to run it.

| Document | What it covers | For |
|---|---|---|
| [`DECISIONS.md`](DECISIONS.md) | The owner's product decisions and the reason for each. They take precedence over every other document | Everyone |
| [`DATA.md`](DATA.md) | Where the data comes from, how each kind of meetings site (Modern.gov, CMIS, CoINS, authorities' own websites) is read, and what was found | Developers |
| [`DESIGN.md`](DESIGN.md) | The site's design: independence from councils, layout, colour, type and the mark | Developers and designers |
| [`DEPLOY.md`](DEPLOY.md) | Installing the site on the charity's shared server, deploying new code, and setting up backups | The maintainer |
| [`OPERATIONS.md`](OPERATIONS.md) | Running the site: the nightly update, spending limits, reports and statements, hiding pages, statistics, deletion, the state database and going back to the code from before wts-core | The maintainer |
| [`EVALUATION.md`](EVALUATION.md) | The briefing test set, and how to score a change against it | Developers |
| [`PILOT.md`](PILOT.md) | The October 2026 pilot of 20 councils, the full load, and the hand checks of votes and removed names | Developers and partners judging accuracy |
| [`research/strategic-authorities.md`](research/strategic-authorities.md) | Research note of 6 November 2026 on England's strategic authorities, behind decisions 17 to 21 | Background |
| [`../CONTRIBUTING.md`](../CONTRIBUTING.md) | Tests, checks and style for contributors | Contributors |
| [`../outreach/README.md`](../outreach/README.md) | The letters asking councils for permission to read their meetings sites, and how they are sent | The maintainer |

Terms used across the documents:

- Strategic authority: a combined authority, a combined county authority or the Greater London Authority, the
  English Devolution and Community Empowerment Act 2026's term ([decision 17](DECISIONS.md#17-strategic-authorities)).
- wts-core: the Python package the Where They Stand sites share, which provides much of this site's machinery
  ([decision 24](DECISIONS.md#24-the-shared-package-the-corrections-log-and-hiding-a-page)).
- The family kit: the Where They Stand sites' shared design files, in `web/public/family`.
- The state database: `data/state.db`, the one store that can't be rebuilt from councils' sites (spending, saved
  briefings, reports, statements).
- The owner makes the product decisions; the maintainer runs the site on the server.
