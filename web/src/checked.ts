/** A checked briefing, as the Where They Stand family shows one (family/BRIEFINGS.md in the charity's repository, with
 * the kit's /family/briefing.css): pure functions from a briefing's answer and sources to what the page shows. The
 * quotations and their sources, as the verifier reads them; the check strip's counts (wts-core's check_counts); which
 * passages show their chips; the words in each chip; the words quoted from each source and where they are in its
 * passage; and the words of the wait. components/Briefing.tsx and components/Wait.tsx draw them. */
import type { Answer, Plan, Segment, SourceCard } from "./api";
import { KIND_LABEL, longDate, monthYear } from "./format";

// ---------- quotations, as the verifier finds them (wts-core checks.verify) ----------

/** Double quotes, straight or curly, of six characters or more; or single curly quotes not closing a word. */
const QUOTE = /["“]([^"“”\n]{6,}?)["”]|‘([^‘’\n]{6,}?)’(?![a-z])/g;
const ELLIPSIS = /\s*(?:\.\.\.|…|\[[^\]]{0,40}\])\s*/;
export const wordsIn = (s: string) => s.toLowerCase().replace(/[’']/g, "").split(/[^a-z0-9]+/).filter(Boolean);

/** A quotation's place in one segment: offsets into its text, the quotation's words, whether the verifier did not
 * find it word for word, whether it ends in this segment, and the sources it was checked against. */
export type QuoteAt = { start: number; end: number; quote: string; missing: boolean; endsHere: boolean; sources: number[] };

/** Text with no source: none was given ("unsupported"), or every citation it gave failed the check against the
 * minutes and was removed ("invalid"). Both are marked alike. */
export const flagged = (seg: Segment) => seg.status === "unsupported" || seg.status === "invalid";
const isBlank = (seg: Segment) => seg.status === "connective" && !(seg.text || "").trim();

/** Each segment's quotations. A quotation of a word or two is a term, not a quotation, as the verifier counts them.
 * Its sources are the verifier's: those of the passages it is part of, or of the cited passage straight after it
 * (within three characters), which is how a quotation in a lead-in is checked against the citation that follows. A
 * quotation is missing where the verifier recorded it as not found (the segment's misquotes). */
export function quotations(segments: Segment[]): QuoteAt[][] {
  const starts: number[] = [];
  let pos = 0;
  for (const s of segments) {
    starts.push(pos);
    pos += (s.text || "").length;
  }
  const full = segments.map((s) => s.text || "").join("");
  const out: QuoteAt[][] = segments.map(() => []);
  for (const m of full.matchAll(QUOTE)) {
    const quote = m[1] || m[2];
    if (wordsIn(quote).length < 3) continue;
    const a = m.index!, b = a + m[0].length;
    const sources: number[] = [];
    segments.forEach((s, i) => {
      const s0 = starts[i], s1 = s0 + (s.text || "").length;
      if ((s0 < b && a < s1) || (s0 >= b && s0 - b <= 3 && (s.sources || []).length)) {
        for (const n of s.sources || []) if (!sources.includes(n)) sources.push(n);
      }
    });
    segments.forEach((s, i) => {
      const s0 = starts[i], s1 = s0 + (s.text || "").length;
      if (!(s0 < b && a < s1)) return;
      const start = Math.max(a, s0) - s0, end = Math.min(b, s1) - s0;
      const missing = (s.misquotes || []).some((x) => x.start < end && start < x.end);
      out[i].push({ start, end, quote, missing, endsHere: b <= s1, sources });
    });
  }
  return out;
}

/** The marks of a quotation the verifier did not find that the pattern above does not see (a single word in
 * quotes, say): each misquote of a segment not already covered, so that every one the checks recorded is shown. */
export function otherMisquotes(seg: Segment, found: QuoteAt[]): QuoteAt[] {
  return (seg.misquotes || [])
    .filter((x) => !found.some((q) => q.start < x.end && x.start < q.end))
    .map((x) => ({ start: x.start, end: Math.min(x.end, seg.text.length), quote: x.text, missing: true,
      endsHere: x.end <= seg.text.length, sources: seg.sources || [] }));
}

// ---------- the check strip ----------

export type CheckCounts = {
  citations_matched: number;
  citations_total: number;
  quotes_found: number;
  quotes_total: number;
  no_source: number;
};

/** The strip's counts, as wts-core's check_counts gives them for the answer as shown (after quotes_beside, on the
 * server): the verifier's counts of citations and quotations, and the passages shown as having no source. */
export function checkCounts(answer: Answer): CheckCounts {
  const total = Number(answer.citations_total || 0), quotes = Number(answer.quotes_total || 0);
  return {
    citations_matched: total - Number(answer.citations_invalid || 0), citations_total: total,
    quotes_found: quotes - Number(answer.quotes_unverified || 0), quotes_total: quotes,
    no_source: (answer.segments || []).filter(flagged).length,
  };
}

/** Where the strip's "Show the first" links go: the first passage with no source, the first whose citation was
 * removed, and the first quotation not found. */
export function firsts(answer: Answer): { nosource: string | null; invalid: string | null; missing: string | null } {
  const segs = answer.segments || [];
  const nosource = segs.findIndex(flagged), invalid = segs.findIndex((s) => s.status === "invalid");
  let missing: string | null = null;
  quotations(segs).some((qs, i) => [...qs, ...otherMisquotes(segs[i], qs)].some((q) =>
    q.missing ? ((missing = `misquote-${i}-${q.start}`), true) : false));
  return { nosource: nosource < 0 ? null : `nosource-${nosource}`, invalid: invalid < 0 ? null : `nosource-${invalid}`, missing };
}

const plural = (n: number, one: string, many: string) => (n === 1 ? one : many);

/** The counts in one sentence, as screen readers hear them once the checks are shown. */
export function countsSentence(answer: Answer): string {
  const c = checkCounts(answer);
  return `Checked against the council minutes: ${c.citations_matched} of ${c.citations_total} ` +
    `${plural(c.citations_total, "citation", "citations")} matched to the record, ${c.quotes_found} of ${c.quotes_total} ` +
    `${plural(c.quotes_total, "quotation", "quotations")} found word for word, ` +
    `${c.no_source ? `${c.no_source} ${plural(c.no_source, "sentence", "sentences")}` : "no sentences"} without a source.`;
}

// ---------- chips and the record ----------

/** Which passages show their chips: two runs next to each other from the same sources show one chip, after the
 * second. */
export function chipsShown(segments: Segment[]): boolean[] {
  return segments.map((seg, i) => {
    if (seg.status !== "cited" || !(seg.sources || []).length) return false;
    let j = i + 1;
    while (j < segments.length && isBlank(segments[j])) j++;
    const next = segments[j];
    return !(next && next.status === "cited" && (next.sources || []).join() === seg.sources.join());
  });
}

/** The meeting, as a chip names it: full council, cabinet, or the committee's own name. */
export function meetingLabel(s: Pick<SourceCard, "kind" | "committee">): string {
  if (s.kind === "council") return "full council";
  if (s.kind === "cabinet") return "cabinet";
  return s.committee || KIND_LABEL[s.kind] || "";
}

/** The words in a chip: the council, the meeting, the date ("Barnsley Metropolitan Borough Council, full council,
 * 26 February 2025"). */
export function chipLabel(s: SourceCard | undefined): string {
  if (!s) return "";
  return [s.council_name, meetingLabel(s), longDate(s.date)].filter(Boolean).join(", ");
}

/** An item as the minutes number it: "Item 10: Notice of Motion - Weekly Bin Collections". */
export function itemLabel(s: Pick<SourceCard, "item_number" | "item_title">): string {
  const n = (s.item_number || "").trim().replace(/[.:]$/, "");
  return n ? `Item ${n}: ${s.item_title}` : s.item_title;
}

/** The sources the chips point to, in order of their numbers: what the record beside the briefing steps through. */
export function citedSources(answer: Answer): number[] {
  const ns = new Set<number>();
  for (const s of answer.segments || []) if (s.status === "cited") for (const n of s.sources || []) ns.add(n);
  return [...ns].sort((a, b) => a - b);
}

/** A run of words quoted from a source, in pieces split at an ellipsis, and the passage whose chip shows it. */
export type Quoted = { seg: number; parts: string[] };
const quoteParts = (q: string) => q.split(ELLIPSIS).map((p) => p.trim()).filter((p) => wordsIn(p).length >= 2);

/** The words quoted from each source, found word for word, for highlighting in its passage. */
export function quotedFrom(answer: Answer): Record<number, Quoted[]> {
  const segs = answer.segments || [];
  const shows = chipsShown(segs);
  const out: Record<number, Quoted[]> = {};
  quotations(segs).forEach((qs, i) => {
    if (flagged(segs[i])) return;
    for (const q of qs) {
      if (q.missing || !q.endsHere) continue;
      // the chip a quotation is shown with: on its own passage, or the next that shows one
      let at = i;
      while (at < segs.length && !shows[at]) at++;
      for (const n of q.sources) (out[n] = out[n] || []).push({ seg: at, parts: quoteParts(q.quote) });
    }
  });
  return out;
}

/** Lower-case words with a map back to the text, as the verifier compares a quotation with its source. */
function wordMap(text: string): { out: string; at: number[] } {
  let out = "", space = true;
  const at: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const c = text[i].toLowerCase();
    if (c === "'" || c === "’" || c === "‘") continue;
    if (/[a-z0-9]/.test(c)) {
      out += c;
      at.push(i);
      space = false;
    } else if (!space) {
      out += " ";
      at.push(i);
      space = true;
    }
  }
  return { out, at };
}

/** Where each quoted piece is in the source's text: [start, end, now], ``now`` for those of the passage chosen. */
export function highlights(text: string, quoted: Quoted[] | undefined, nowSeg: number | null): [number, number, boolean][] {
  const map = wordMap(text);
  const spans: [number, number, boolean][] = [];
  for (const q of quoted || []) {
    for (const part of q.parts) {
      const w = wordsIn(part).join(" ");
      if (!w) continue;
      let i = (" " + map.out + " ").indexOf(` ${w} `);
      if (i < 0) i = (" " + map.out).indexOf(` ${w}`); // the last word may run on in the record
      if (i < 0) continue;
      const a = map.at[i], b = map.at[i + w.length - 1] + 1;
      if (spans.some(([x, y]) => a < y && x < b)) continue;
      spans.push([a, b, q.seg === nowSeg]);
    }
  }
  return spans.sort((x, y) => x[0] - y[0]);
}

/** The part of a long passage around what is quoted from it, cut at sentence ends. */
export function excerpt(text: string, spans: [number, number, boolean][], before = 420, after = 560): { from: number; to: number } {
  if (!spans.length) {
    if (text.length <= 900) return { from: 0, to: text.length };
    const end = text.indexOf(". ", 700);
    return { from: 0, to: end > 0 && end < 1000 ? end + 1 : 900 };
  }
  let a = Math.max(0, spans[0][0] - before), b = Math.min(text.length, spans[spans.length - 1][1] + after);
  if (a > 0) {
    const stop = text.lastIndexOf(". ", a), para = text.lastIndexOf("\n", a);
    const cut = Math.max(stop >= 0 ? stop + 2 : -1, para >= 0 ? para + 1 : -1);
    if (cut >= 0 && a - cut < 240) a = cut;
  }
  if (b < text.length) {
    const stop = text.indexOf(". ", b), para = text.indexOf("\n", b);
    const cut = Math.min(stop >= 0 ? stop + 1 : Infinity, para >= 0 ? para : Infinity);
    if (cut !== Infinity && cut - b < 240) b = cut;
  }
  if (a > 0) a += (text.slice(a).match(/^\s*/) || [""])[0].length;
  return { from: a, to: b };
}

/** The first words of a passage, for its card in the pile. */
export function firstWords(text: string, most = 150): string {
  const first = (text || "").replace(/\s+/g, " ").trim();
  return first.length > most ? first.slice(0, most).replace(/\s+\S*$/, "") + "…" : first;
}

// ---------- the wait ----------

const NATION: Record<string, string> = {
  england: "England", wales: "Wales", scotland: "Scotland", northern_ireland: "Northern Ireland",
};
const PARTY: Record<string, string> = {
  LAB: "Labour", CON: "Conservative", LD: "Liberal Democrat", GRN: "Green", REF: "Reform UK", PC: "Plaid Cymru",
  UKIP: "UKIP", LIB: "Liberal Party", IND: "independent",
};

const listed = (xs: string[]) => (xs.length < 2 ? xs.join("") : `${xs.slice(0, -1).join(", ")} and ${xs[xs.length - 1]}`);

/** The question as read, as large chips: where, when, whose and which meetings ("Councils in Wales", "since May
 * 2022", "all parties", "full council and cabinet"). Each is the plan's own filter in words. */
export function planChips(plan: Plan, regions: Record<string, string> = {}, types: Record<string, string> = {},
  councilNames: Record<string, string> = {}): string[] {
  const f = plan.filters || {};
  const out: string[] = [];
  const where = [
    ...(f.councils || []).map((g) => councilNames[g] || g),
    ...(f.regions || []).map((r) => regions[r] || r),
    ...(f.nations || []).map((n) => NATION[n] || n),
  ];
  const kinds = (f.council_types || []).map((t) => types[t] || t);
  if (where.length && f.councils?.length) out.push(listed(where));
  else if (where.length) out.push(`${kinds.length ? listed(kinds) : "Councils"} in ${listed(where)}`);
  else out.push(kinds.length ? listed(kinds) : "Councils across the UK");
  if (f.date_from && f.date_to) out.push(`${longDate(f.date_from)} to ${longDate(f.date_to)}`);
  else if (f.date_from) out.push(`since ${monthYear(f.date_from)}`);
  else if (f.date_to) out.push(`May 2018 to ${longDate(f.date_to)}`);
  else out.push("since May 2018");
  const control = (f.control || []).map((c) => c === "NOC" ? "no overall control" : c.startsWith("MAYOR:")
    ? `a ${PARTY[c.slice(6)] || c.slice(6)} mayor` : c === "SA:NONE" ? "no mayor" : `${PARTY[c] || c.replace(/^LOCAL:/, "")} control`);
  if (control.length) out.push(`Under ${listed(control)}`);
  for (const p of f.parties || []) out.push(`Naming ${PARTY[p] || p} councillors`);
  if (!control.length && !(f.parties || []).length) out.push("all parties");
  const meetings = (f.kinds || []).map((k) => meetingLabel({ kind: k, committee: "" }) || k);
  out.push(meetings.length ? listed(meetings) : "full council and cabinet");
  if (f.named_votes_only) out.push("named votes only");
  return out;
}

export type Evidence = { records?: number; councils?: number; meetings?: number; kinds?: Record<string, number> };

/** What was found, in words: the running count while the cards arrive, then the summary from the search's own
 * figures ("24 records from 11 councils at 18 meetings: 15 from full council and 9 from cabinet"). */
export function foundWords(evidence: Evidence | null | undefined, shown: number, total: number): { n: number; words: string } {
  if (shown < total) return { n: shown, words: ` ${plural(shown, "record", "records")} found so far` };
  const e = evidence || {};
  if (!e.records || !e.councils) return { n: total, words: ` ${plural(total, "record", "records")} found` };
  const kinds = Object.entries(e.kinds || {}).filter(([, n]) => n > 0).sort((a, b) => b[1] - a[1])
    .map(([k, n]) => `${n} from ${meetingLabel({ kind: k, committee: KIND_LABEL[k]?.toLowerCase() || k })}`);
  // a strategic authority's meetings are its board's, its mayor's and its scrutiny committees' (decision 18)
  const authority = Object.keys(e.kinds || {}).some((k) => ["board", "mayor", "scrutiny"].includes(k));
  const bodies = authority ? plural(e.councils, "council or authority", "councils and authorities")
    : plural(e.councils, "council", "councils");
  return { n: e.records, words: ` ${plural(e.records, "record", "records")} from ${e.councils} ${bodies}` +
    (e.meetings ? ` at ${e.meetings} ${plural(e.meetings, "meeting", "meetings")}` : "") +
    (kinds.length > 1 ? `: ${listed(kinds)}` : "") };
}
