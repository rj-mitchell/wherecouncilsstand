# Design

The site's design: how it stays independent of councils, its layout, colours, type and mark. Where Councils Stand
uses the Where They Stand family's design (family kit 2.0), shared with its sister sites: a white page, light grey
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
- Where a short block would sit alone, two blocks share the row (`.split`): the question box beside the panel about
  the briefings on the home page, a council's introduction beside its figures, members by party beside the party
  in control, meetings by year beside the latest meetings.
- Panels (`.panel`, notices, statements, the routes on the page for people who are named) are light grey with no
  border or coloured edge. A council's figures are a short list of terms and values.
- The footer is the family shelf, then six links (About, Methodology, Corrections, Accessibility, Privacy, Source
  code) and one short paragraph with the independence line and the licence notice. Terms, Press, Status and the page
  for people who are named are linked from the About page.

## The family binding

The kit (`web/public/family`, copied in by the charity's `family/kit/sync.mjs`; README, "The Where They Stand
family") gives the colour tokens, the fonts, the endorsement, the footer shelf, the favicon, the link card and the
theme colour. Its files are included as they are (`<!--#include family/shelf-->` in the partials) and never
edited here. On the brown band the endorsement's spine is drawn a shade darker than the cloth so that it stays
visible.

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
- Citation marks ("[1]") keep their small size, with an invisible area to tap or click around each: 24 px tall,
  28 px on a touch screen, reaching a little either side but never into a citation next to it. Each mark is kept on
  one line.
