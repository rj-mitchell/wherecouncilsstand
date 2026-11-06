# Design: the minute book

Where They Stand takes its look from Hansard's printed Official Report, and Where Countries Stand from the UN's
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

## Colour and type

| Token | Use | Value |
|---|---|---|
| Binding | Links, focus rings, primary buttons, **full council** | A deep minute-book blue, `oklch(40% 0.07 255)` (light), `oklch(78% 0.08 250)` (dark) |
| Cabinet | **Cabinet** and policy committees | Ochre, `oklch(48% 0.09 65)` (light), `oklch(80% 0.1 75)` (dark) |
| Paper and ink | Text and background | Near-black on a faintly warm white, like typed minutes; dark mode is the binding's blue-black |

- **The meeting determines the colour,** as Where They Stand uses green for the Commons and red for the Lords:
  sources are edged in blue for full council and ochre for cabinet.
- **Party colours** are used only where a chart needs to tell parties apart (members by party on a council's page),
  with the colours readers associate with each party, as on Where They Stand. Local parties and independents share
  one grey. Party colours never mark a passage or a briefing.
- **Votes use neutral marks:** filled for *for*, outlined for *against*, hatched for *abstained*. Never green for
  yes and red for no, which would imply that one way is right.
- **Coverage uses neutral marks too:** on the councils page, "Coverage: full / partial / not yet", with a filled,
  half-filled or outlined square beside the word. Coverage is how much of a council's record the site can read, a
  fact about the site, so it is never shown in red, amber and green, which would read as rating the council.
- **Literata** (SIL Open Font Licence), a book face, for the record and the briefing. **Public Sans** (SIL OFL) for
  controls only: navigation, buttons, chips, metadata and counts. Both are bundled with the site.

## The mark

An open minute book: two pages with ruled lines, and a short margin rule on the left page for the minute number
(`web/public/icon.svg`). It looks nothing like a crest.

## Shared with Where They Stand and Where Countries Stand

- Square corners, ruled lists, and colour only where it carries meaning.
- OKLCH colour tokens holding both light and dark values, through `light-dark()`. Dark mode follows the system
  setting.
- One fluid type scale, logical properties, visible focus rings, hover styles only for a mouse, and animation only
  when reduced motion isn't requested.
- No horizontal scrolling on phones. Pages are checked at 390 px wide.
