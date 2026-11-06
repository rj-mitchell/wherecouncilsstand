# Design: the minute book

Where MPs Stand takes its look from Hansard's printed Official Report, and Where Countries Stand from the UN's
Official Records. Where Councils Stand takes its look from a council's own record: the **minute book**. A council's
minutes are typed up, approved at the next meeting, signed by the chair and bound. Each minute is numbered in the
margin ("CO92", "45."), its heading in capitals, its decision introduced by **RESOLVED**.

## The rule: like the record, never like a council

- **No council's crest, coat of arms or logo**, and nothing that resembles them: no shields, mantling or mural
  crowns. No council's colours.
- **No council's name in the site's name or address.** Councils' names appear only as what the record is about.
- **Independence is stated on every page**: in the masthead ("Independent. Not affiliated with any council.") and in
  the footer, which also names the Local Government Association, Civica (who make Modern.gov and CMIS) and
  Northgate (who make CoINS).
- **A screenshot must never pass for a council document.** The minute book's conventions are borrowed. The masthead,
  name and mark are our own, and every quotation sits inside a source panel that names the council and links to its
  minutes.

## What is borrowed from the record

| In the minute book | In the site |
|---|---|
| Minute numbers in the left margin | Source numbers in the margin of each source; the item's own number ("CO92") beside its title |
| Headings in capitals | Section headings in small capitals between rules |
| **RESOLVED** – That … | The briefing's "In brief" is set like a resolution: a ruled box, its label in small capitals |
| *Present:* Councillors … | Councillors named in a source, and members by party on a council's page, set as the attendance list is: label in italic, names in a run |
| Recorded votes: *For:* … *Against:* … *Abstentions:* … | The same labels in italic, with neutral marks |
| The chair's signature line at the foot of each page | The footer's rule and the independence notice |

## The family binding

Where Councils Stand is a Where They Stand project, and carries the family's binding, the same on every site
(the charity's family kit, copied into `web/public/family` by its `family/kit/sync.mjs`; README, "In the family"):

- **the endorsement** under the site's name in the masthead: the site's spine in Buckram brown and "A Where They
  Stand project" in gilt capitals, linking to wheretheystand.uk;
- **the family shelf** at the foot of every page: the charity, every project's spine and a link to each sister site;
- **the favicon, theme colour and link card** in the site's cloth;
- **Source Serif 4 for headings** (decision 1 of the family plan), through `class="wts-headings"` on `<body>`. The
  site's name in the masthead is set in it too, so the name, the endorsement and the headings below read as one.

The kit's files are included as they are (`<!--#include family/shelf-->` in the partials) and never edited here.

## Colour and type

| Token | Use | Value |
|---|---|---|
| Binding (`--binding`, `--council`, `--accent`) | The mark, the phase tag, links, focus rings, primary buttons, **full council** | **Buckram brown**, the site's cloth in the family: `#6E4A2A`, `oklch(44.2% 0.0675 61.3)` (light). In dark mode the family's lifted brown `#865A33` for fills and its tan `#D8AE84` for text and links |
| Cabinet (`--cabinet`) | **Cabinet** and policy committees | Slate grey, `oklch(46% 0.035 240)` (light), `oklch(80% 0.035 240)` (dark): far from the brown in hue, and from every party's colour |
| Warning (`--warn`) | Notices, text a source doesn't support | Amber, `oklch(55% 0.125 82)` (light), `oklch(84% 0.12 88)` (dark): yellower than the brown, so a warning never reads as the site's own colour |
| Paper and ink | Text and background | Near-black on a faintly warm white, like typed minutes; dark mode is a near-neutral slate black, close to the family shelf's |

- **Brown is the identity colour**, and the only one the site uses for itself. It replaced a minute-book navy in
  November 2026 (family decision 2): navy sat close to Where Countries Stand's blue and to a party's colour.
- **The meeting determines the colour,** as Where MPs Stand uses green for the Commons and red for the Lords:
  sources are edged in brown for full council and slate for cabinet.
- **Party colours** are used only where a chart needs to tell parties apart (members by party on a council's page),
  with the colours readers associate with each party, as on Where MPs Stand. Local parties and independents share
  one grey. Party colours never mark a passage or a briefing, and none of them is the site's own.
- **Votes use neutral marks:** filled for *for*, outlined for *against*, hatched for *abstained*. Never green for
  yes and red for no, which would imply that one way is right.
- **Coverage uses neutral marks too:** on the councils page, "Coverage: full / partial / not yet", with a filled,
  half-filled or outlined square beside the word. Coverage is how much of a council's record the site can read, a
  fact about the site, so it is never shown in red, amber and green, which would read as rating the council.
- **Source Serif 4** (SIL Open Font Licence), the family's typeface, for headings and the site's name, from the
  family kit. **Literata** (SIL OFL), a book face, for the record and the briefing. **Public Sans** (SIL OFL) for
  controls only: navigation, buttons, chips, metadata and counts. All three are served from the site itself.

## The mark

An open minute book: two pages with ruled lines, and a short margin rule in gilt on the left page for the minute
number, bound in Buckram brown (`web/partials/mark.html`, drawn inline so it takes the page's colours). In dark mode
the brown is the family's lifted cloth, at 3:1 against the page, with a thin gilt edge. It looks nothing like a
crest. It is the site's page mark (family decision 4); the favicon, the footer shelf and the link card use the
family's spine instead.

## Shared with the family

- Square corners, ruled lists, and colour only where it carries meaning.
- OKLCH colour tokens holding both light and dark values, through `light-dark()`. Dark mode follows the system
  setting.
- One fluid type scale, logical properties, visible focus rings, hover styles only for a mouse, and animation only
  when reduced motion isn't requested.
- No horizontal scrolling on phones. Pages are checked at 390 px wide.
