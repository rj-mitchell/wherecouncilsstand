/** A topic's page (decision 35). The server writes the whole checked briefing into the page (the strip, the text with
 * its marks and chips, how it was checked, and the sources: src/councils/api/topic_pages.py), so it reads the same with
 * or without this script. Where it runs, it adds what the home page's briefings have (family/BRIEFINGS.md, "The record
 * beside the briefing"): on wide screens the record beside the briefing, open from the start on the first source,
 * following the chips and the scroll and joined to the chosen chip by a line; on narrower screens a sheet that a chip
 * opens. Its sources come from the data the server wrote into the page, so nothing is fetched. */
import { StrictMode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import type { Answer, SourceCard } from "./api";
import { citedSources, quotedFrom } from "./checked";
import { RecordPanel, Sheet } from "./components/Record";
import { drawConnector, WIDE } from "./connector";
import { markNav } from "./format";

type Data = { answer: Answer; sources: SourceCard[] };

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const canHover = () => matchMedia("(hover: hover)").matches;
const chipOf = (e: Event) => (e.target as HTMLElement).closest?.<HTMLElement>(".wts-chip") || null;

function useMedia(query: string): boolean {
  const [on, setOn] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query);
    const change = () => setOn(m.matches);
    m.addEventListener("change", change);
    return () => m.removeEventListener("change", change);
  }, [query]);
  return on;
}

export function TopicRecord({ data, grid, text, svg }: {
  data: Data;
  grid: HTMLElement;
  text: HTMLElement;
  svg: SVGSVGElement;
}) {
  const wide = useMedia(WIDE);
  const byN = useMemo(() => Object.fromEntries(data.sources.map((s) => [s.n, s])), [data]);
  const quoted = useMemo(() => quotedFrom(data.answer), [data]);
  const cited = useMemo(() => citedSources(data.answer).filter((n) => byN[n]), [data, byN]);
  const chips = useCallback(() => [...text.querySelectorAll<HTMLElement>(".wts-chip")], [text]);
  const first = chips()[0];
  const [active, setActive] = useState<{ n: number; seg: number | null; chip: HTMLElement | null } | null>(
    first ? { n: Number(first.dataset.source), seg: Number(first.dataset.seg), chip: null } : cited.length ? { n: cited[0], seg: null, chip: null } : null);
  const [sheet, setSheet] = useState<{ n: number; seg: number | null } | null>(null);
  const pinnedUntil = useRef(0);
  const sheetChip = useRef<HTMLElement | null>(null);
  const panel = wide && cited.length > 0;

  // the grid takes the record's column only while there is a record beside it
  useLayoutEffect(() => {
    grid.classList.toggle("has-record", panel);
  }, [grid, panel]);

  const line = useCallback((chip: HTMLElement | null) => drawConnector(svg, grid, text, chip), [svg, grid, text]);

  // the chosen chip marked, and joined to its passage
  useLayoutEffect(() => {
    for (const c of chips()) {
      const on = !!active && panel && Number(c.dataset.source) === active.n && (!active.chip || c === active.chip);
      c.setAttribute("aria-current", String(on));
    }
    line(panel ? active?.chip || null : null);
  }, [active, panel, chips, line]);

  // the chips, as on the home page: chosen by pressing, focus or hover on a wide screen; on a narrower one a press
  // opens the sheet
  useEffect(() => {
    const choose = (chip: HTMLElement, pin: number) => {
      pinnedUntil.current = Date.now() + pin;
      setActive({ n: Number(chip.dataset.source), seg: Number(chip.dataset.seg), chip });
    };
    const click = (e: Event) => {
      const chip = chipOf(e);
      if (!chip) return;
      if (matchMedia(WIDE).matches) choose(chip, 4000);
      else {
        sheetChip.current = chip;
        setSheet({ n: Number(chip.dataset.source), seg: Number(chip.dataset.seg) });
      }
    };
    const focus = (e: Event) => {
      const chip = chipOf(e);
      if (chip && matchMedia(WIDE).matches) choose(chip, 4000);
    };
    const hover = (e: Event) => {
      const chip = chipOf(e);
      if (chip && matchMedia(WIDE).matches && canHover() && chip.getAttribute("aria-current") !== "true") choose(chip, 2500);
    };
    text.addEventListener("click", click);
    text.addEventListener("focusin", focus);
    text.addEventListener("mouseover", hover);
    return () => {
      text.removeEventListener("click", click);
      text.removeEventListener("focusin", focus);
      text.removeEventListener("mouseover", hover);
    };
  }, [text]);

  // as the reader scrolls a wide screen, the chip nearest the upper third of the window leads, unless they have just
  // chosen one
  useEffect(() => {
    if (!panel) return;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const all = chips();
        const current = all.find((c) => c.getAttribute("aria-current") === "true") || null;
        if (Date.now() < pinnedUntil.current) {
          line(current);
          return;
        }
        const mark = innerHeight * 0.38;
        let best: HTMLElement | null = null, bd = Infinity;
        for (const c of all) {
          const r = c.getBoundingClientRect();
          const d = Math.abs(r.top - mark);
          if (r.bottom > 0 && r.top < innerHeight && d < bd) {
            bd = d;
            best = c;
          }
        }
        if (best && best !== current) setActive({ n: Number(best.dataset.source), seg: Number(best.dataset.seg), chip: best });
        else line(current);
      });
    };
    const onResize = () => line(chips().find((c) => c.getAttribute("aria-current") === "true") || null);
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onResize);
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onResize);
    };
  }, [panel, chips, line]);

  // a sheet is for narrower screens: widening the window closes it
  useEffect(() => {
    if (wide) setSheet(null);
  }, [wide]);

  function step(d: number) {
    if (!cited.length) return;
    const i = cited.indexOf(active?.n ?? cited[0]);
    const n = cited[(i + d + cited.length) % cited.length];
    const chip = text.querySelector<HTMLElement>(`.wts-chip[data-source="${n}"]`);
    pinnedUntil.current = Date.now() + 4000;
    setActive({ n, seg: chip ? Number(chip.dataset.seg) : null, chip });
    chip?.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" });
  }
  const closeSheet = useCallback(() => {
    setSheet(null);
    sheetChip.current?.focus();
  }, []);

  return (
    <>
      {panel && active && (
        <RecordPanel n={active.n} nowSeg={active.seg} cited={cited} byN={byN} quoted={quoted} onStep={step} />
      )}
      {sheet && byN[sheet.n] && (
        <Sheet n={sheet.n} nowSeg={sheet.seg} source={byN[sheet.n]} quoted={quoted[sheet.n]} onClose={closeSheet} />
      )}
    </>
  );
}

/** Start on the page the server wrote: the record's column and the line's drawing surface go into the briefing's
 * grid, and the component draws into them. A page with no briefing (not written yet, or hidden) is left as it is,
 * and so is one already started. */
export function start() {
  const grid = document.getElementById("topic-grid");
  const text = document.getElementById("topic-text");
  const raw = document.getElementById("topic-data")?.textContent;
  if (!grid || !text || !raw || grid.querySelector(":scope > .record-col")) return;
  let data: Data;
  try {
    data = JSON.parse(raw) as Data;
  } catch {
    return;
  }
  const aside = document.createElement("aside");
  aside.className = "record-col";
  aside.setAttribute("aria-label", "The record beside the briefing");
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "wts-connector");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  grid.append(aside, svg);
  createRoot(aside).render(
    <StrictMode>
      <TopicRecord data={data} grid={grid} text={text} svg={svg} />
    </StrictMode>,
  );
}

markNav();
start();
