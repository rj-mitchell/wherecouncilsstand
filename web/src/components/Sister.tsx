/** Links to the charity's sister sites (README, "The Where They Stand family"). A link to a sister site always
 * names it and shows its spine, so the reader knows they are going to another site. The spine is the family kit's own
 * drawing, taken from its footer shelf (public/family/shelf.html, which the kit's sync script writes), never drawn
 * here, so it changes when the kit does; it takes its cloth from the kit's stylesheet, light or dark. The server
 * takes the same drawing from the same file for the pages it writes (src/councils/sisters.py, spine). */
import type { ReactNode } from "react";
import type { Answer } from "../api";
import shelf from "../../public/family/shelf.html?raw";

export const SISTERS = {
  landlords: { name: "Where Landlords Stand", url: "https://wherelandlordsstand.com" },
  mps: { name: "Where MPs Stand", url: "https://wherempsstand.com" },
} as const;

export type Sister = keyof typeof SISTERS;

/** The kit's spine for a sister site, as its shelf draws it, or "" if the shelf has none. */
export function kitSpine(site: Sister, from: string = shelf): string {
  const m = from.match(new RegExp(`<svg class="wts-spine wts-cloth--${site}"[\\s\\S]*?</svg>`));
  return m ? m[0] : "";
}

/** The sister site's spine from the kit, at the kit's size. It is decoration: the site's name is always beside it. */
export function Spine({ site }: { site: Sister }) {
  return <span className="spine" aria-hidden="true" dangerouslySetInnerHTML={{ __html: kitSpine(site) }} />;
}

/** A quiet block of links to one sister site, under its name and spine. */
export function SisterLinks({ site, children }: { site: Sister; children: ReactNode }) {
  return (
    <aside className="sister" aria-label={`On ${SISTERS[site].name}`}>
      <Spine site={site} />
      <div>
        <p className="sister-name">On {SISTERS[site].name}</p>
        {children}
      </div>
    </aside>
  );
}

/** "Ask Where MPs Stand the same question": one quiet line under a written briefing. Where MPs Stand reads ?q= into
 * its question box (its App.tsx), and keeps the first 500 characters. */
export function AskSister({ site, question }: { site: Sister; question: string }) {
  const href = `${SISTERS[site].url}/?q=${encodeURIComponent(question.slice(0, 500))}`;
  return (
    <p className="sister-ask">
      <Spine site={site} />
      <span>
        <a href={href}>Ask {SISTERS[site].name} the same question</a>
        <span className="muted">, on the record of the UK Parliament</span>
      </span>
    </p>
  );
}

/** Whether a briefing was written, so that the same question may be offered on a sister site: only under a written
 * briefing, never under "No records found", an error, or the sources alone (sources only, or a limit reached). */
export function writtenBriefing(s: { phase: string; question: string; answer: Answer | null; error: string | null }): boolean {
  return s.phase === "done" && !!s.question.trim() && !s.error && !!s.answer && !s.answer.no_records &&
    s.answer.segments.some((seg) => seg.text.trim() !== "");
}
