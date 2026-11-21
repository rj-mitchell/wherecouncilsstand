/** A briefing as the reader sees it, as the Where They Stand family shows a checked briefing (family/BRIEFINGS.md in
 * the charity's repository, with the kit's /family/briefing.css): the check strip, the text with the record's own
 * words set apart, a chip after each cited passage naming the council, the meeting and the date, every passage with no
 * source marked in words, the record's slip for a source, and "How this briefing was checked" at the end. The text is
 * set from a small, safe subset of Markdown (headings in bold on their own line, bullets, bold); no HTML is injected. */
import { Fragment, type MouseEvent, type ReactNode } from "react";
import type { Answer, Segment, SourceCard } from "../api";
import {
  checkCounts, chipLabel, chipsShown, excerpt, firsts, flagged, highlights, itemLabel, otherMisquotes, quotations,
  type QuoteAt, type Quoted,
} from "../checked";
import { longDate } from "../format";

/** What a reader is told after each mark (said by a screen reader straight after it). */
export const SAID = {
  checked: (n: number) => ` (quotation, found word for word in the minutes of source ${n})`,
  missing: (n: number | undefined) =>
    ` (quotation not found word for word in the minutes cited for it${n ? `, source ${n}` : ""})`,
  nosource: " (no source)",
  invalid: " (its citation did not match the minutes and was removed)",
};

/** While the checks' results run up in the wait: quotations after ``upTo`` are not shown as found yet, and those of
 * passage ``flash`` take their highlight now. */
export type Checking = { upTo: number; flash: number | null };

type Piece = { seg: number; start: number; end: number; chips?: undefined } | { chips: number[]; seg: number };

/** The briefing as lines of pieces: a span of a segment's text, or where a cited passage's chips go (after its last
 * words, on the line they are on). */
function lines(segments: Segment[]): Piece[][] {
  const out: Piece[][] = [[]];
  const shows = chipsShown(segments);
  segments.forEach((seg, i) => {
    let off = 0;
    let last: Piece[] | null = null;
    (seg.text || "").split("\n").forEach((part, k) => {
      if (k > 0) out.push([]);
      if (part) {
        out[out.length - 1].push({ seg: i, start: off, end: off + part.length });
        last = out[out.length - 1];
      }
      off += part.length + 1;
    });
    if (shows[i]) ((last as Piece[] | null) || out[out.length - 1]).push({ chips: seg.sources, seg: i });
  });
  return out;
}

/** A chip: the source's number for printing and the reference list, then who, where and when. It is named by its
 * own visible words ("Source 3 Barnsley Metropolitan Borough Council, full council, 26 February 2025"), never by an
 * aria-label that would differ from them (WCAG 2.5.3). */
export function Chip({ n, source, seg }: { n: number; source?: SourceCard; seg?: number }) {
  const label = chipLabel(source);
  return (
    <button type="button" className="wts-chip" data-source={n} data-seg={seg}>
      <span className="wts-chip__in">
        <span className="wts-chip__n">
          <span className="wts-vh">Source </span>
          {n}
        </span>
        {label && <span>{label}</span>}
      </span>
    </button>
  );
}

type Ctx = { missingIds: Set<string>; firstNoSource: number; checking: Checking | null; key: number };

/** A quotation: the record's own words where the verifier found them in the passage's source, or marked where it
 * did not. One found inside text with no source is left as text: nothing says whose words they are. */
function quoteNode(q: QuoteAt, seg: Segment, i: number, inner: ReactNode[], ctx: Ctx): ReactNode {
  const n = q.sources[0];
  const key = `q${ctx.key++}`;
  if (q.missing) {
    const id = `misquote-${i}-${q.start}`;
    const fresh = !ctx.missingIds.has(id);
    ctx.missingIds.add(id);
    return (
      <span key={key} className="wts-quote wts-quote--missing" id={fresh ? id : undefined} data-seg={i}>
        {inner}
        {q.endsHere && <span className="wts-quote__tick" aria-hidden="true">Not found word for word</span>}
        {q.endsHere && <span className="wts-vh">{SAID.missing(n)}</span>}
      </span>
    );
  }
  if (!n || flagged(seg)) return <Fragment key={key}>{inner}</Fragment>;
  const c = ctx.checking;
  if (c && i > c.upTo) {
    // not checked yet, in the wait: the record's face, without its highlight or its tick
    return <span key={key} className="wts-quote" data-seg={i} data-source={n}>{inner}</span>;
  }
  return (
    <span key={key} className={`wts-quote wts-quote--checked${c && c.flash === i ? " is-flash" : ""}`} data-seg={i}
      data-source={n}>
      {inner}
      {q.endsHere && <span className="wts-quote__tick" aria-hidden="true">✓ word for word</span>}
      {q.endsHere && <span className="wts-vh">{SAID.checked(n)}</span>}
    </span>
  );
}

/** One piece of a segment's text, with its quotations and bold, as nodes. */
function pieceNodes(seg: Segment, i: number, start: number, end: number, quotes: QuoteAt[], ctx: Ctx): ReactNode[] {
  const text = seg.text.slice(start, end);
  const drop = new Set<number>();
  const bold: [number, number][] = [];
  for (const m of text.matchAll(/\*\*([^*]+)\*\*/g)) {
    bold.push([m.index! + 2, m.index! + 2 + m[1].length]);
    for (const x of [m.index!, m.index! + 1, m.index! + m[0].length - 2, m.index! + m[0].length - 1]) drop.add(x);
  }
  const local = (a: number, b: number): [number, number] => [Math.max(a, start) - start, Math.min(b, end) - start];
  const qs = quotes.filter((q) => q.start < end && start < q.end).map((q) => ({ ...q, range: local(q.start, q.end) }));
  const cuts = new Set([0, text.length]);
  for (const [a, b] of [...bold, ...qs.map((q) => q.range)]) {
    cuts.add(Math.max(0, a));
    cuts.add(Math.min(text.length, b));
  }
  const at = [...cuts].sort((x, y) => x - y);
  const runs: { t: string; quote: number; bold: boolean }[] = [];
  for (let k = 0; k + 1 < at.length; k++) {
    const a = at[k], b = at[k + 1];
    let t = "";
    for (let x = a; x < b; x++) if (!drop.has(x)) t += text[x];
    if (!t) continue;
    const q = qs.findIndex((r) => r.range[0] <= a && b <= r.range[1]);
    runs.push({ t, quote: q, bold: bold.some(([s, e]) => s <= a && b <= e) });
  }
  const out: ReactNode[] = [];
  for (let k = 0; k < runs.length;) {
    const q = runs[k].quote;
    let j = k;
    while (j < runs.length && runs[j].quote === q) j++;
    const inner = runs.slice(k, j).map((r) => (r.bold ? <strong key={`b${ctx.key++}`}>{r.t}</strong> : r.t));
    if (q < 0) out.push(...inner);
    else out.push(quoteNode(qs[q], seg, i, inner, ctx));
    k = j;
  }
  return out;
}

type Block = { kind: "h"; text: string } | { kind: "p"; nodes: ReactNode[] } | { kind: "ul"; items: ReactNode[][] };

/** The briefing's text as blocks: every cited passage followed by its chips, every passage with no source marked, the
 * first with "No source" in words. */
function blocks(segments: Segment[], sourcesByN: Record<number, SourceCard>, checking: Checking | null): Block[] {
  const quotes = quotations(segments).map((qs, i) => [...qs, ...otherMisquotes(segments[i], qs)]);
  const ctx: Ctx = { missingIds: new Set(), firstNoSource: segments.findIndex(flagged), checking, key: 0 };
  const all = lines(segments);
  const lastPiece = new Map<number, string>();
  all.forEach((line, li) => line.forEach((p, pi) => {
    if (p.chips === undefined) lastPiece.set(p.seg, `${li}:${pi}`);
  }));
  const seen = new Set<number>();
  const inlineOf = (line: Piece[], li: number): ReactNode[] => {
    const out: ReactNode[] = [];
    line.forEach((p, pi) => {
      if (p.chips !== undefined) {
        out.push("⁠", ...p.chips.map((n) => <Chip key={`c${ctx.key++}`} n={n} source={sourcesByN[n]} seg={p.seg} />));
        return;
      }
      const seg = segments[p.seg];
      let start = p.start;
      if (pi === 0) {
        // a list item's or heading's marker is not text
        const lead = seg.text.slice(p.start, p.end).match(/^\s*(?:[-*•]|#+)\s+/);
        if (lead) start += lead[0].length;
      }
      if (!flagged(seg)) {
        out.push(...pieceNodes(seg, p.seg, start, p.end, quotes[p.seg], ctx));
        return;
      }
      // the mark runs under the words, not the spaces either side of them
      const piece = seg.text.slice(start, p.end);
      const a = start + (piece.match(/^\s*/) || [""])[0].length;
      const b = Math.max(a, p.end - (piece.match(/\s*$/) || [""])[0].length);
      const first = !seen.has(p.seg);
      seen.add(p.seg);
      const last = lastPiece.get(p.seg) === `${li}:${pi}`;
      out.push(seg.text.slice(start, a));
      if (b > a) {
        out.push(
          <span key={`n${ctx.key++}`} className="wts-nosource" id={first ? `nosource-${p.seg}` : undefined} data-seg={p.seg}>
            {pieceNodes(seg, p.seg, a, b, quotes[p.seg], ctx)}
            {last && p.seg === ctx.firstNoSource && <span className="wts-nosource__tag" aria-hidden="true">No source</span>}
            {last && <span className="wts-vh">{seg.status === "invalid" ? SAID.invalid : SAID.nosource}</span>}
          </span>,
        );
      }
      out.push(seg.text.slice(b, p.end));
    });
    return out;
  };
  const out: Block[] = [];
  let list: ReactNode[][] | null = null;
  all.forEach((line, li) => {
    const plain = line.map((p) => (p.chips !== undefined ? "" : segments[p.seg].text.slice(p.start, p.end))).join("").trim();
    const cites = line.some((p) => p.chips !== undefined);
    if (!plain && !cites) {
      list = null;
      return;
    }
    if (!cites && (/^#{1,4}\s/.test(plain) || /^\*\*[^*]+\*\*:?$/.test(plain))) {
      out.push({ kind: "h", text: plain.replace(/^#+\s*/, "").replace(/\*\*/g, "").replace(/:$/, "").trim() });
      list = null;
      return;
    }
    if (/^[-*•]\s/.test(plain)) {
      if (!list) {
        list = [];
        out.push({ kind: "ul", items: list });
      }
      list.push(inlineOf(line, li));
      return;
    }
    list = null;
    out.push({ kind: "p", nodes: inlineOf(line, li) });
  });
  return out;
}

/** The briefing's text: the checked answer's segments, or the text as it is written (``text``, with a cursor while
 * it streams). The "In brief" section is set on a panel. */
export function BriefingText({ segments, text, sources = [], checking = null, cursor = false }: {
  segments?: Segment[];
  text?: string;
  sources?: SourceCard[];
  checking?: Checking | null;
  cursor?: boolean;
}) {
  const segs: Segment[] = segments || [{ text: text || "", sources: [], status: "connective" }];
  const byN = Object.fromEntries(sources.map((s) => [s.n, s]));
  const all = blocks(segs, byN, checking);
  const sections: { title: string | null; blocks: Block[] }[] = [{ title: null, blocks: [] }];
  for (const b of all) {
    if (b.kind === "h") sections.push({ title: b.text, blocks: [] });
    else sections[sections.length - 1].blocks.push(b);
  }
  const caret = <span className="wts-cursor" aria-hidden="true" />;
  const lastBlock = all.filter((b) => b.kind !== "h").at(-1);
  return (
    <div className="answer">
      {sections.map((s, i) => {
        const body = (
          <>
            {s.title && <h2>{s.title}</h2>}
            {s.blocks.map((b, k) => {
              const end = cursor && b === lastBlock;
              if (b.kind === "ul")
                return (
                  <ul key={k}>
                    {b.items.map((it, j) => (
                      <li key={j}>
                        {it}
                        {end && j === b.items.length - 1 && caret}
                      </li>
                    ))}
                  </ul>
                );
              return (
                <p key={k}>
                  {b.kind === "p" && b.nodes}
                  {end && caret}
                </p>
              );
            })}
            {cursor && !lastBlock && i === sections.length - 1 && <p>{caret}</p>}
          </>
        );
        return /^in brief$/i.test(s.title || "") ? (
          <section key={i} className="resolved" aria-label="In brief">
            {body}
          </section>
        ) : (
          <Fragment key={i}>{body}</Fragment>
        );
      })}
    </div>
  );
}

// ---------- the check strip, and the check details at the end ----------

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** The strip's "Show the first" links: to the passage, scrolled into view and briefly shown. */
function showFirst(e: MouseEvent<HTMLAnchorElement>) {
  const target = document.querySelector<HTMLElement>(e.currentTarget.getAttribute("href") || "");
  if (!target) return;
  e.preventDefault();
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  target.setAttribute("tabindex", "-1");
  target.scrollIntoView({ block: "center", behavior: still ? "auto" : "smooth" });
  target.focus({ preventScroll: true });
  target.classList.add("is-shown");
  setTimeout(() => target.classList.remove("is-shown"), 1600);
}

function StripItem({ shown, total, words, problem, first, pending = false }: {
  shown: number;
  total: number | null;
  words: string;
  problem: boolean;
  first: string | null;
  pending?: boolean;
}) {
  return (
    <li className="wts-check__item">
      <span className="wts-check__count">
        <span className="wts-check__glyph" aria-hidden="true">{pending ? "…" : problem ? "!" : "✓"}</span>
        {!pending && <span className="wts-check__num">{shown}</span>}
        {total !== null && <span>of {total}</span>}
        {problem && !pending && <span className="wts-check__badge">To check</span>}
      </span>
      <span>
        {pending ? `${words}: counted last` : words}
        {problem && !pending && first && (
          <>
            {". "}
            <a className="wts-check__first" href={`#${first}`} onClick={showFirst}>Show the first</a>
          </>
        )}
      </span>
    </li>
  );
}

/** The check strip: the three counts in words, under the title that names the record. ``running``: the numbers to
 * show while the checks' results run up in the wait (the count with no source "counted last"); the list is then
 * hidden from screen readers, which hear the counts once, at the end. */
export function CheckStrip({ answer, running = null }: { answer: Answer; running?: { citations: number; quotes: number } | null }) {
  const c = checkCounts(answer), f = firsts(answer);
  return (
    <section className="wts-check" aria-labelledby="check-title" id="check">
      <div className="wts-check__head">
        <h2 className="wts-check__title" id="check-title">Checked against the council minutes</h2>
        <a className="wts-check__more" href="#check-details">How it was checked</a>
      </div>
      <ul className="wts-check__list" aria-hidden={running ? "true" : undefined}>
        <StripItem shown={running ? running.citations : c.citations_matched} total={c.citations_total}
          words={plural(c.citations_total, "citation matched to the record", "citations matched to the record")}
          problem={!running && c.citations_matched < c.citations_total} first={f.invalid} />
        <StripItem shown={running ? running.quotes : c.quotes_found} total={c.quotes_total}
          words={plural(c.quotes_total, "quotation found word for word", "quotations found word for word")}
          problem={!running && c.quotes_found < c.quotes_total} first={f.missing} />
        <StripItem shown={c.no_source} total={null} pending={!!running}
          words={plural(c.no_source, "sentence without a source", "sentences without a source")}
          problem={c.no_source > 0} first={f.nosource} />
      </ul>
    </section>
  );
}

/** "How this briefing was checked", at the end, linked from the strip: the verifier's own counts, and what each mark
 * means. */
export function CheckDetails({ answer, found }: { answer: Answer; found: number }) {
  const total = Number(answer.citations_total || 0), invalid = Number(answer.citations_invalid || 0);
  const quotes = Number(answer.quotes_total || 0), missing = Number(answer.quotes_unverified || 0);
  const unsupported = Number(answer.unsupported_segments || 0);
  const beside = (answer.segments || []).filter((s) => s.beside).length;
  const points = [
    found ? `The AI was given only the ${found} ${plural(found, "passage", "passages")} of minutes found for the question, listed under Sources, and may use nothing else.` : null,
    `Each of the ${total} ${plural(total, "citation", "citations")} was checked against the minutes it cites: ` +
      (invalid ? `${invalid} did not match, so ${plural(invalid, "it was", "they were")} removed, and the words ${plural(invalid, "it was", "they were")} attached to are marked “No source”. Check the minutes before relying on them.` : "all matched."),
    quotes ? `Each of the ${quotes} ${plural(quotes, "quotation", "quotations")} was looked for word for word in the minutes cited for it: ` +
      (missing ? `${missing} could not be found and ${plural(missing, "is", "are")} marked “Not found word for word” with a wavy underline. Check the minutes before relying on ${plural(missing, "it", "them")}.` : "all were found, and each is marked “✓ word for word”.") : null,
    unsupported ? `${unsupported} ${plural(unsupported, "sentence", "sentences")} that no cited source supports ${plural(unsupported, "is", "are")} marked with a dotted underline, and the first with “No source”. Short joining phrases are not counted.`
      : "No sentence was found without a source. Short joining phrases are not counted.",
    beside ? `${beside === 1 ? "A quotation" : `${beside} quotations`} found word for word in the minutes cited straight after ${beside === 1 ? "it is" : "them are"} shown as those minutes’ ${plural(beside, "quotation", "quotations")}; the words around ${beside === 1 ? "it keep" : "them keep"} their marks.` : null,
    "Minutes are summaries of each meeting written by council officers, so a quotation is the minutes’ words, not a councillor’s own.",
    "Some errors can still get through: check the minutes before relying on a point.",
  ];
  return (
    <section className="check-details" id="check-details" aria-labelledby="check-details-head">
      <h2 id="check-details-head">How this briefing was checked</h2>
      <ul>
        {points.filter(Boolean).map((p) => <li key={p}>{p}</li>)}
      </ul>
      <p>
        <a href="/methodology#ai-briefings">How every briefing is checked, on the methodology page</a>
      </p>
    </section>
  );
}

// ---------- the record: the slip for one source ----------

function passageNodes(text: string, spans: [number, number, boolean][], short: boolean): ReactNode[] {
  const { from, to } = short ? excerpt(text, spans, 160, 420) : excerpt(text, spans);
  const out: ReactNode[] = [];
  if (from > 0) out.push("… ");
  let at = from;
  spans.forEach(([a, b, now], k) => {
    if (a < from || b > to) return;
    out.push(text.slice(at, a), <mark key={k} className={now ? "wts-now" : undefined}>{text.slice(a, b)}</mark>);
    at = b;
  });
  out.push(text.slice(at, to));
  if (to < text.length) out.push(" …");
  return out;
}

/** Who the passage names, with their party on the date ("Councillor Hannah Kitching (Liberal Democrats; not the party
 * in control)"): the name in bold. */
function named(people: string[]): ReactNode[] {
  return people.flatMap((p, i) => {
    const cut = p.indexOf(" (");
    const node = cut > 0 ? <Fragment key={i}><strong>{p.slice(0, cut)}</strong>{p.slice(cut)}</Fragment> : <strong key={i}>{p}</strong>;
    return i ? ["; ", node] : [node];
  });
}

/** The record's slip for one source, as a page of minutes: the council, the meeting and the date; who the passage
 * names; the item's number and heading; the passage with every quoted run highlighted and the chosen one outlined; and
 * the link to the council's own minutes. ``short``: a shorter passage, for the sheet on a phone, so the highlighted
 * words are in view as it opens. */
export function Slip({ source: s, quoted, nowSeg, passageId, short = false }: {
  source: SourceCard;
  quoted?: Quoted[];
  nowSeg: number | null;
  passageId: string;
  short?: boolean;
}) {
  const text = s.text || "";
  const spans = highlights(text, quoted, nowSeg);
  return (
    <div className="wts-slip">
      <div className="wts-slip__top">
        <b>{s.council_name}</b>
        <span>{[s.committee, longDate(s.date)].filter(Boolean).join(", ")}</span>
      </div>
      {s.named && s.named.length > 0 && <div className="wts-slip__who">{named(s.named)}</div>}
      <div className="wts-slip__heading">{itemLabel(s)}</div>
      <p className="wts-passage" tabIndex={0} id={passageId} aria-label={`The passage from source ${s.n}`}>
        {passageNodes(text, spans, short)}
      </p>
      <div className="wts-slip__foot">
        {spans.length ? <span className="wts-slip__found">✓ Highlighted words found word for word</span> : <span />}
        <a href={s.url} rel="noreferrer">The minutes on {s.council_name}’s website</a>
      </div>
    </div>
  );
}
