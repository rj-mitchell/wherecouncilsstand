/** A briefing as the reader sees it: the model's text, with each cited span followed by its source numbers, set
 * from a small, safe subset of Markdown (headings in bold on their own line, bullets, bold). No HTML is injected.
 * The checks' points to check are marked: text no cited source supports, and quotations not found word for word. */
import { Fragment, type ReactNode } from "react";
import type { Answer, Segment } from "../api";

/** A quotation not found word for word, as offsets into a run's text. `note`: the screen reader's explanation goes
 * after it (not where the quotation carries on into the next segment, so it is said once). */
type Mark = { start: number; end: number; note: boolean };
type Run = { text: string; sources: number[]; status: string; misquotes: Mark[] };

/** What a marked quotation is, for a pointer (title) and for a screen reader (said straight after it). */
export const MISQUOTE_TITLE = "Not found word for word in the minutes cited for it";
const MISQUOTE_SAID = " (quotation not found word for word in the minutes cited for it)";

/** Text that no cited source supports: none was given ("unsupported"), or every citation it gave failed the check
 * against the minutes and was removed ("invalid"). Both are marked alike. */
export function unsupported(status: string) {
  return status === "unsupported" || status === "invalid";
}

/** Text with the marked quotations in it: each fragment inside a mark is wrapped, and the explanation follows the
 * mark's last fragment. */
function marked(text: string, from: number, marks: Mark[], key: string): ReactNode[] {
  const cuts = new Set([0, text.length]);
  for (const m of marks) {
    for (const at of [m.start - from, m.end - from]) if (at > 0 && at < text.length) cuts.add(at);
  }
  const at = [...cuts].sort((a, b) => a - b);
  const out: ReactNode[] = [];
  for (let i = 0; i < at.length - 1; i++) {
    const [a, b] = [at[i], at[i + 1]];
    const mark = marks.find((m) => m.start - from < b && a < m.end - from);
    if (!mark) {
      out.push(<Fragment key={`${key}f${i}`}>{text.slice(a, b)}</Fragment>);
      continue;
    }
    const last = mark.note && b >= mark.end - from;
    out.push(
      <span key={`${key}f${i}`} className="misquote" title={MISQUOTE_TITLE}>
        {text.slice(a, b)}
        {last && <span className="visually-hidden">{MISQUOTE_SAID}</span>}
      </span>,
    );
  }
  return out;
}

/** Bold (**…**) inside a line, and the marked quotations (offsets into the line's text). */
function inline(text: string, key: string, marks: Mark[] = []): ReactNode[] {
  const out: ReactNode[] = [];
  let pos = 0;
  text.split(/(\*\*[^*]+\*\*)/g).forEach((p, i) => {
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4)
      out.push(<strong key={`${key}b${i}`}>{marked(p.slice(2, -2), pos + 2, marks, `${key}b${i}`)}</strong>);
    else if (p) out.push(...marked(p, pos, marks, `${key}t${i}`));
    pos += p.length;
  });
  return out;
}

function Cites({ sources }: { sources: number[] }) {
  if (!sources.length) return null;
  return (
    <>
      {sources.map((n) => (
        <a key={n} className="cite" href={`#source-${n}`} aria-label={`Source ${n}`}>
          [{n}]
        </a>
      ))}
    </>
  );
}

/** The marks inside text from `start` to `end` of a run, as offsets into that text. */
function within(marks: Mark[], start: number, end: number): Mark[] {
  return marks
    .filter((m) => m.start < end && start < m.end)
    .map((m) => ({ start: Math.max(m.start, start) - start, end: Math.min(m.end, end) - start, note: m.note && m.end <= end }));
}

/** Lines of runs: each run keeps its citation, so a line can mix cited and uncited text. */
function lines(runs: Run[]): Run[][] {
  const out: Run[][] = [[]];
  for (const run of runs) {
    const pieces = run.text.split("\n");
    let start = 0;
    pieces.forEach((piece, i) => {
      if (i > 0) out.push([]);
      // the citation belongs after the last piece of the run
      out[out.length - 1].push({
        ...run,
        text: piece,
        sources: i === pieces.length - 1 ? run.sources : [],
        misquotes: within(run.misquotes, start, start + piece.length),
      });
      start += piece.length + 1;
    });
  }
  return out;
}

function lineText(line: Run[]) {
  return line.map((r) => r.text).join("");
}

function renderLine(line: Run[], key: string, strip: RegExp | null = null): ReactNode[] {
  return line.map((r, i) => {
    let text = r.text;
    let marks = r.misquotes;
    if (i === 0 && strip) {
      const cut = text.length - text.replace(strip, "").length;
      text = text.slice(cut);
      marks = within(marks, cut, cut + text.length);
    }
    const content = inline(text, `${key}-${i}`, marks);
    return (
      <Fragment key={`${key}-${i}`}>
        {unsupported(r.status) && text.trim() ? (
          <span className="unsupported" title="Not supported by a cited source">
            {content}
          </span>
        ) : (
          content
        )}
        <Cites sources={r.sources} />
      </Fragment>
    );
  });
}

export function BriefingText({ segments, text }: { segments?: Segment[]; text?: string }) {
  const runs: Run[] = segments
    ? segments.map((s, i) => ({
        text: s.text,
        sources: s.sources || [],
        status: s.status,
        misquotes: (s.misquotes || []).map((m) => ({
          start: m.start,
          end: m.end,
          // a quotation that carries on into the next segment is explained once, where it ends
          note: !(m.end >= s.text.length && (segments[i + 1]?.misquotes || []).some((n) => n.start === 0 && n.text === m.text)),
        })),
      }))
    : [{ text: text || "", sources: [], status: "connective", misquotes: [] }];
  const all = lines(runs);
  // blocks: headings, bullet lists and paragraphs; the "In brief" section is set on a panel
  const sections: { heading: Run[] | null; blocks: ReactNode[] }[] = [{ heading: null, blocks: [] }];
  let list: ReactNode[] | null = null;
  const flush = () => {
    if (list) sections[sections.length - 1].blocks.push(<ul key={`ul${sections.length}-${sections[sections.length - 1].blocks.length}`}>{list}</ul>);
    list = null;
  };
  all.forEach((line, i) => {
    const t = lineText(line).trim();
    if (!t) {
      flush();
      return;
    }
    if (/^\*\*[^*]+\*\*:?$/.test(t) || /^#{1,3}\s/.test(t)) {
      flush();
      sections.push({ heading: line, blocks: [] });
      return;
    }
    if (/^\s*[-*•]\s+/.test(lineText(line))) {
      list = list || [];
      list.push(<li key={i}>{renderLine(line, `l${i}`, /^\s*[-*•]\s+/)}</li>);
      return;
    }
    flush();
    sections[sections.length - 1].blocks.push(<p key={i}>{renderLine(line, `p${i}`)}</p>);
  });
  flush();
  return (
    <div className="answer">
      {sections.map((s, i) => {
        const title = s.heading ? lineText(s.heading).replace(/^#{1,3}\s*/, "").replace(/\*\*/g, "").replace(/:$/, "").trim() : null;
        const body = (
          <>
            {title && <h2>{title}</h2>}
            {s.blocks}
          </>
        );
        return /^in brief$/i.test(title || "") ? (
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

/** Under a checked briefing: what its marks mean, for each kind it has. Text no cited source supports (with or without
 * a citation that failed the check), and quotations not found word for word. */
export function CheckNotices({ answer }: { answer: Answer }) {
  const failed = answer.segments.filter((s) => s.status === "invalid").length;
  const flagged = (answer.unsupported_segments || 0) + failed;
  const misquoted = answer.quotes_unverified || 0;
  const them = misquoted === 1 ? "it" : "them";
  return (
    <>
      {flagged > 0 && (
        <p className="notice">
          Text <span className="unsupported">marked like this</span> isn’t supported by a cited source. Treat it with care,
          and check the minutes.
          {failed === 1 && " One passage gave a source, but its citation failed the check against the minutes and was removed."}
          {failed > 1 &&
            ` ${failed} passages gave sources, but their citations failed the check against the minutes and were removed.`}
        </p>
      )}
      {misquoted > 0 && (
        <p className="notice">
          {misquoted === 1 ? "One quotation" : `${misquoted} quotations`} <span className="misquote">marked like this</span>{" "}
          {misquoted === 1 ? "was" : "were"} not found word for word in the minutes cited for {them}. Check the minutes
          before relying on {them}.
        </p>
      )}
    </>
  );
}
