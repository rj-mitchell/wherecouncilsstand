/** The line joining a chosen chip's line of text to its passage in the record beside the briefing, across the gutter
 * (family/BRIEFINGS.md, "The record beside the briefing"): drawn into ``svg``, which covers ``grid``, from the end of
 * the chip's line of ``text`` to the highlighted words in the passage. Nothing is drawn on narrower screens, for a chip
 * out of view, or where the gutter is too narrow. Used by the home page's briefings (ask.tsx) and the topic pages
 * (topic.tsx). */
export const WIDE = "(min-width: 64rem)";

export function drawConnector(svg: SVGSVGElement | null, grid: HTMLElement | null, text: HTMLElement | null,
  chip: HTMLElement | null, passageId = "record-passage") {
  if (!svg) return;
  svg.replaceChildren();
  const passage = document.getElementById(passageId);
  if (!chip || !grid || !text || !passage || !matchMedia(WIDE).matches) return;
  const box = grid.getBoundingClientRect(), a = chip.getBoundingClientRect();
  if (a.bottom < 0 || a.top > innerHeight) return;
  const m = passage.querySelector("mark.wts-now") || passage.querySelector("mark") || passage;
  const b = m.getBoundingClientRect(), pb = passage.getBoundingClientRect(), t = text.getBoundingClientRect();
  // from the end of the chip's line of text, so the line runs in the gutter and never across the briefing
  const x1 = t.right + 6 - box.left, y1 = a.top + a.height / 2 - box.top;
  const x2 = pb.left - 6 - box.left;
  const y2 = Math.min(Math.max(b.top + 10, pb.top + 8), pb.bottom - 8) - box.top;
  if (x2 - x1 < 12) return;
  const mid = (x1 + x2) / 2, ns = "http://www.w3.org/2000/svg";
  svg.setAttribute("viewBox", `0 0 ${box.width} ${box.height}`);
  svg.setAttribute("width", String(box.width));
  svg.setAttribute("height", String(box.height));
  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", `M${x1} ${y1} C ${mid} ${y1}, ${mid} ${y2}, ${x2} ${y2}`);
  svg.append(path);
  for (const [cx, cy] of [[x1, y1], [x2, y2]]) {
    const dot = document.createElementNS(ns, "circle");
    dot.setAttribute("cx", String(cx));
    dot.setAttribute("cy", String(cy));
    dot.setAttribute("r", "3");
    svg.append(dot);
  }
}
