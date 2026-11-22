# Design

The site's design: how it stays independent of councils, its layout, colours, type and mark. Where Councils Stand
uses the Where They Stand family's design (family kit 2.3), shared with its sister sites: a white page, light grey
panels, the site's cloth as a solid band across the top of every page, Source Serif 4 for headings and Source Sans 3
for everything else.

## Independence from councils

The site must look like a record of councils' decisions. Nothing on it should resemble a council's own site.

- No council's crest, coat of arms or logo, and nothing that resembles them: no shields, mantling or mural crowns.
  No council's colours.
- No council's name in the site's name or address. Councils' names appear only as what the record is about.
- Independence is stated on every page, in the footer's short form: "Independent. Not affiliated with any council,
  the Local Government Association, Civica or Northgate." The About page gives the full sentence and says that
  Civica make Modern.gov and CMIS, and Northgate make CoINS. Printed pages keep it.
- A screenshot must never pass for a council document. The header, name and mark are the site's own, and every
  quotation sits in a source that names the council and links to its minutes.

## Layout

- The header is a band of the site's cloth, Buckram brown, across the full width, with the mark, the site's name,
  the family's endorsement ("A Where They Stand project") and the navigation in white. The alpha banner sits under it
  on a light grey strip.
- Every part of a page lines up to one column, 72rem wide with the kit's gutter: the header's contents, the main
  content, the family shelf and the footer. Running text is held to about two-thirds of it (46rem); panels, tables,
  lists of votes and sources, and the filters use the whole column.
- Where a short block would sit alone, two blocks share the row (`.split`): a council's introduction beside its figures, members by party beside the party
  in control, meetings by year beside the latest meetings.
- Panels (`.panel`, notices, statements, the routes on the page for people who are named) are light grey with no
  border or coloured edge. A council's figures are a short list of terms and values.
- The home page has the question box first, held to the running text's width, with "Ask" and "Sources only (no AI)"
  side by side under it, then the line about the briefings and its disclosure. Under the questions to try comes the
  proof of the checking ("The home page", below), then "Latest named votes" (decision 32):
  the 20 newest named votes across every council, in as many columns as fit the whole column (one on a phone,
  two on a wide screen). Each has its vote's heading as a link in the heading face, then the council and the date
  in full, then the result and counts with their sides named. A thin rule above each separates them. The server
  writes it outside the app's root, so it is the same with and without scripts.
- A council's or authority's page lists "MPs whose seats overlap this council" (decision 31) under its members and
  control: Where MPs Stand's spine and name, a line saying where the seats come from, then each MP as a link with
  their party and seat, in as many columns as fit.
- The footer is the family shelf, then six links (About, Methodology, Corrections, Accessibility, Privacy, Source
  code) and one short paragraph with the independence line and the licence notice. Terms, Press, Status and the page
  for people who are named are linked from the About page. While measurement for Google Ad Grants is on (decision 36; off as
  it ships), a line of its own follows the paragraph: "Measurement choices", which opens the family's consent banner
  again (a control, not a page, so not one of the six links).

## The family binding

The kit (`web/public/family`, copied in by the charity's `family/kit/sync.mjs`; README, "The Where They Stand
family") gives the colour tokens, the fonts, the endorsement, the footer shelf, the favicon, the link card and the
theme colour. Its files are included as they are (`<!--#include family/shelf-->` in the partials) and never
edited here. On the brown band the endorsement's spine is drawn a shade darker than the cloth so that it stays
visible.

The kit's `measure.js` and `measure-csp.json` are the family's consent banner and Google tag loader, and the hosts
a content security policy adds for it (the charity's `family/MEASUREMENT.md`). Both are unused while measurement is
off, as it ships (decision 36): no page loads `measure.js` until `[ads] measurement` is on, and then the server adds
it to the head of every page it sends. The banner is drawn at the top of `<main>` in the kit's own styles
(`family.css`, `.wts-measure`), with "Accept" and "Reject" the same button. The pages carry the kit's conversion marks
(`data-wts-conversion`) whether it is on or off: the source chips and every link to a council's own minutes, "How
this briefing was checked" at the end of a written briefing, and the shelf's Donate link.

A link to a sister site names it and shows its spine, so the reader knows they are moving to another site (the
charity's roadmap, "Links between the records"). The spine is the kit's own drawing, taken from its footer shelf
(`family/shelf.html`), never drawn here: by the server for the pages it writes (`sisters.spine`) and by the app
from the same file (`components/Sister.tsx`). It goes beside the links to Where Landlords Stand on a council's
page, the MPs whose seats overlap it, and the offer of the same question on Where MPs Stand, which appears only
under a written briefing (not under "No records found", an error or the sources alone).

## Colour and type

| Token | Use | Value |
|---|---|---|
| Binding (`--binding`) | The header band and primary buttons | The kit's `--wts-cloth-councils`: `#6E4A2A`, and `#865A33` in dark mode |
| Accent (`--accent`, `--council`) | Links, focus rings, secondary buttons | The kit's `--wts-cloth-councils-text`: `#6E4A2A`, and `#D8AE84` in dark mode |
| Page, panel, ink, rules | Text and backgrounds | The kit's `--wts-paper-light`, `--wts-paper`, `--wts-ink`, `--wts-ink-muted` and `--wts-rule-faint`, light and charcoal dark |
| Warning (`--warn`) | Notices, text a source doesn't support | Amber, `oklch(55% 0.125 82)` (light), `oklch(84% 0.12 88)` (dark) |

- Brown is the site's identity colour and the only one it uses for itself.
- Party colours are used only where a chart needs to tell parties apart (members by party on a council's page),
  with the colours readers associate with each party. Local parties and independents share one grey.
- Votes use neutral marks: filled for "for", outlined for "against", hatched for "abstained".
- Coverage uses neutral marks too: a filled, half-filled or outlined square beside "Full", "Partial" or "Not yet".
  Coverage describes the site's reading of a council's record, so it is never shown in red, amber and green.
- Source Serif 4 for headings and the site's name, through `class="wts-headings"` on `<body>`, and Source Sans 3 for
  body text and controls, both from the kit and served from the site itself (SIL Open Font Licence).
- Headings and labels are in sentence case at normal letter spacing.

## The mark

A town hall on a tile of Buckram brown with rounded corners and a fine gilt edge (`#D9BC72`, the family's spine
gilt, so the edge still shows at 16 pixels), drawn in the same manner as Where MPs Stand's mark: a clock tower with a
spire behind a pediment, four columns on a stylobate, and a gilt step (`web/partials/mark.html`, drawn inline at
52 px, 44 px on a phone). It was chosen from seven drawings (decision 16). In dark mode the tile and the clock
face are the family's lifted cloth, at 3:1 against the page; the stone and gilt keep their colours. In forced colours
it is redrawn in the system's two colours.

The same drawing is in `web/public/` for others to use: `mark.svg` (light), `mark-dark.svg` (the lifted cloth), and
`mark-small.svg` and `mark-small-dark.svg` for 16 to 32 pixels, with three columns, a heavier edge and step, and no
clock hands. The favicon, the footer shelf and the link card use the family's spine. In the header the mark
sits on the band of the same brown, so its gilt edge frames it.

## Shared with the family

- Colour tokens hold light and dark values through `light-dark()` (from the kit). Dark mode follows the system
  setting.
- Logical properties, visible focus rings, hover styles only for a mouse, and transitions only when reduced motion
  isn't requested. Forced colours draw panels with a border.
- No horizontal scrolling on phones. Pages are checked at 390 px wide, and at 320 px.

## Tables and citations

- On a phone (below 30rem) the councils page's tables become blocks, one per council (`.stack-table`): the
  council's name and type, its row heading, on top, then each other column as a pair, its name (`data-label`) beside
  its value. The column headings stay for screen readers, and explicit table roles keep it a table for them once its
  display changes. Columns marked `wide-only` (meetings, from) are left out there.
- A table of a few short figures (`.table-wrap.narrow`, figures in tabular numerals), a council's meetings by
  year, shares its row with the latest meetings, so it stays narrow enough to read across on a wide screen.
- Dates in a timeline take the width of the longest, but never more than 16rem or 45% of the line, so on a narrow
  phone a long date range wraps rather than squeezing the names.
- Citations are chips ("Checked briefings", below), not bare numbers; printed, each is its number in brackets.

## Checked briefings

Decision 34, after the charity's review plan of 21 November 2026 (B1 to B6) and the family's `family/BRIEFINGS.md`.
The parts are the family kit's (`/family/briefing.css`, linked by the home page, which also shows saved briefings),
used as they are, in the site's cloth (`wts-cloth--councils` on the briefing); `web/src/styles.css` adds only the
layout around them. `web/src/checked.ts` holds the pure parts, `components/Briefing.tsx` draws the briefing,
`components/Record.tsx` the record beside it and the sheet, `components/Wait.tsx` the wait, and `ask.tsx` puts them
together.

### The briefing

- The question, as asked, then how the question was read and the filters used, then "Briefing written by AI", then
  the check strip: a band of the cloth titled "Checked against the council minutes", with citations matched,
  quotations found word for word and sentences without a source, each in words, a tick or "!" and "To check", and a
  link to the first point to check. On a phone the counts stack, number first.
- The text: a quotation found word for word in the minutes' serif on the record's highlight with "✓ word for word";
  one not found with a wavy underline and "Not found word for word"; text with no source with a dotted underline in
  the warning colour, "No source" in words on the first. After each cited passage a chip: its number on the cloth,
  then the council, the meeting (full council, cabinet, or the committee's name) and the date.
- On screens 64rem and wider the briefing is beside the record (24rem, sticky): a page of minutes for one source,
  open on the first, with the council, the meeting and date, who the passage names with their party on the date, the
  item's number and heading, the passage with every quoted run highlighted and the chosen one outlined, and a link to
  the council's own minutes; "Previous source" and "Next source" under it. A chip pressed, focused or pointed at
  shows its source, and as the reader scrolls the chip nearest the upper third of the window leads, unless they have
  just chosen one. A thin line in the cloth joins the chip's line of text to its passage across the gutter.
- On narrower screens a chip opens the same slip in a sheet from the bottom of the screen; focus moves to its heading,
  stays in it, and returns to the chip on Close, Escape or a tap outside.
- At the end, "How this briefing was checked" (the verifier's own counts, and what each mark means), the link to the
  briefing and the report link, the offer of the same question on Where MPs Stand, then the list of sources (the
  printed reference list).

### The wait

The stages run across the column, "Now" in words and a heavier border on the current one (two rows on a phone):
reading the question, searching the record, writing from these records only, checking every citation and quotation.
The stage under way has a pulsing dot beside "Now". Before the plan arrives, the family's five books on a shelf, each
taken down and put back in turn; then the question as read in large chips ("Councils in Wales",
"since May 2022", "all parties", "full council and cabinet") with the plan's own reading. The records found arrive as
cards, each a page of minutes (the council and the date, the meeting and the item, the first words of the passage),
into a pile beside the text on wide screens and along a shelf on phones, under a running count and then the search's
own summary ("24 records from 11 councils at 18 meetings: 15 from full council and 9 from cabinet"). Then "Writing
from these N records only. The AI may use these and nothing else.", the text as it is written with a cursor, and each
card marked "Cited" as its citation arrives. When the text is complete the server says the checks have begun (a
`progress` event with `step: "checking"`, `rag/pipeline.py`): from then until the final event the stage is
"Checking", the line about writing goes, and under the text the checking line says "Checking every citation and
quotation against the council minutes. The briefing is finished when this is done." over a bar that moves while the
checks run (the status region says it once). When the final event arrives the strip appears and its counts run up
through the real results, each quotation taking its highlight in turn, the count of sentences without a source
"counted last"; then the pile settles into the record. Cards are added as they arrive, with no canvas and no work per
frame. With reduced motion the stages are the same, without movement. Sources only shows the first two stages, then
the list of sources.

### The home page

Under the questions to try, the proof of the checking, in the page's HTML so that it needs no script: "Every
briefing, checked against the council minutes", the three steps in large type, then two cards of the same height
(kit 2.3.0): on the left a sentence with a record quotation and its chip, and under it where the example comes from;
on the right the page of minutes it came from with the same words highlighted, joined by a rule across the gutter at
the cards' middle. Its labels share a row from 48rem, so the cards start level although the passage's label is long. The
example is a genuine minute from the site's test record, Glasgow City Council's City Administration Committee of 25
January 2024, and the page says where it comes from. A link to the methodology ends it. It is hidden once a briefing
is shown.

### Share cards

A saved briefing's link preview is its own card (1200 by 630): the band of the cloth with the site's icon and name,
"Briefing written by AI, checked against the council minutes", the title "Briefing from council minutes, <date>"
(decision 33), the strip's three counts in words, and the day it was prepared.

## Topic briefings

Decision 35. `/topics` lists the ten topics in two columns on a computer and one on a phone, each with its title (a
link, in the serif), its question in the serif, a line on what it covers, and when its briefing was prepared and from
how many records (or that it has not been written yet). A topic's page opens with a link back to the list, the title,
the question as the lede in the serif, and a sentence saying what a topic briefing is, when this one was prepared and
what it was written from; then the briefing exactly as a saved one looks (the checked design above), without the
question box, the wait or the offer of Where MPs Stand; then the sources and the earlier weeks' briefings. The record
sits beside it on a computer and opens in a sheet on a phone, as on the home page. The home page lists the topics that
have a briefing as serif links with the day each was prepared, in as many columns as fit, between the proof of the
checking and the latest named votes. A topic's share card is the saved briefing's card, titled with the topic's
question. On a phone the five links of the menu keep to one line, a little closer together.
