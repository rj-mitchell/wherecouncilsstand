/** A briefing as the reader sees it: the model's text, with each cited span followed by its source numbers, set
 * from a small, safe subset of Markdown (headings in bold on their own line, bullets, bold). No HTML is injected. */
import { Fragment, type ReactNode } from "react";
import type { Segment } from "../api";

type Run = { text: string; sources: number[]; status: string };

/** Bold (**…**) inside a line. */
function inline(text: string, key: string): ReactNode[] {
  const out: ReactNode[] = [];
  const parts = text.split(/(\*\*[^*]+\*\*)/g);
  parts.forEach((p, i) => {
    if (p.startsWith("**") && p.endsWith("**") && p.length > 4) out.push(<strong key={`${key}b${i}`}>{p.slice(2, -2)}</strong>);
    else if (p) out.push(<Fragment key={`${key}t${i}`}>{p}</Fragment>);
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

/** Lines of runs: each run keeps its citation, so a line can mix cited and uncited text. */
function lines(runs: Run[]): Run[][] {
  const out: Run[][] = [[]];
  for (const run of runs) {
    const pieces = run.text.split("\n");
    pieces.forEach((piece, i) => {
      if (i > 0) out.push([]);
      // the citation belongs after the last piece of the run
      out[out.length - 1].push({ ...run, text: piece, sources: i === pieces.length - 1 ? run.sources : [] });
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
    if (i === 0 && strip) text = text.replace(strip, "");
    const content = inline(text, `${key}-${i}`);
    return (
      <Fragment key={`${key}-${i}`}>
        {r.status === "unsupported" && text.trim() ? (
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
    ? segments.map((s) => ({ text: s.text, sources: s.sources || [], status: s.status }))
    : [{ text: text || "", sources: [], status: "connective" }];
  const all = lines(runs);
  // blocks: headings, bullet lists and paragraphs; the "In brief" section is boxed, like a resolution
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
