/** The wait for a briefing, drawn from the stream's real events in order (family/BRIEFINGS.md, "The wait"): the
 * stages, the family's spines before the first event, the question as read, the records found arriving as pages of
 * minutes into a pile, and the line that says the AI writes from these records only. Nothing here is invented and
 * nothing waits for an animation: each part is drawn when its event has arrived. */
import { forwardRef, type CSSProperties } from "react";
import type { Plan, SourceCard } from "../api";
import { firstWords, foundWords, itemLabel, meetingLabel, planChips, type Evidence } from "../checked";
import { longDate } from "../format";

export const STAGES = ["Reading the question", "Searching the record", "Writing from these records only",
  "Checking every citation and quotation"];

/** The stages, the one now marked in words as well as by its border. Sources only has the first two. */
export function Stages({ stage, sourcesOnly }: { stage: number; sourcesOnly: boolean }) {
  const names = sourcesOnly ? STAGES.slice(0, 2) : STAGES;
  return (
    <ol className="wts-stages" aria-label="Preparing the briefing">
      {names.map((n, i) => {
        const state = i < stage ? "done" : i === stage ? "now" : "next";
        return (
          <li key={n} className="wts-stage" data-state={state}>
            <span className="wts-stage__state">{state === "done" ? "✓ Done" : state === "now" ? "Now" : "Next"}</span>
            <span>{n}</span>
          </li>
        );
      })}
    </ol>
  );
}

const CLOTHS = ["mps", "councils", "landlords", "countries", "lives"];
const HEIGHTS = [64, 56, 70, 60, 52];

/** The family's book spines, in the five cloths, before the first event has arrived. */
export function Spines() {
  return (
    <div className="wts-spines" aria-hidden="true">
      {CLOTHS.map((c, i) => (
        <span key={c} style={{ "--c": `var(--wts-cloth-${c})`, "--i": i, "--h": `${HEIGHTS[i]}px` } as CSSProperties} />
      ))}
    </div>
  );
}

/** The question as read, as large chips, with the plan's own reading under them. */
export function PlanRead({ plan, regions, types, councilNames }: {
  plan: Plan;
  regions?: Record<string, string>;
  types?: Record<string, string>;
  councilNames?: Record<string, string>;
}) {
  return (
    <>
      <ul className="wts-plan" aria-label="The question as read">
        {planChips(plan, regions, types, councilNames).map((c) => <li key={c}>{c}</li>)}
      </ul>
      {plan.interpretation && <p className="wait__reading">{plan.interpretation}</p>}
    </>
  );
}

/** What was found, in words: the running count while the cards arrive, then the summary. */
export function Found({ evidence, shown, total }: { evidence: Evidence | null; shown: number; total: number }) {
  const f = foundWords(evidence, shown, total);
  return (
    <p className="wts-found">
      <strong>{f.n}</strong>
      {f.words}
    </p>
  );
}

/** A record found, as a card in the record's own form, a page of minutes: the council and the date, the meeting and
 * the item, and its real first words. */
function Card({ s, cited, checked, tilt }: { s: SourceCard; cited: boolean; checked: boolean; tilt: number }) {
  const meeting = meetingLabel(s);
  return (
    <li className={`wts-card${cited ? " is-cited" : ""}${checked ? " is-checked" : ""}`} data-source={s.n}
      style={{ "--wts-r": `${tilt}deg` } as CSSProperties}>
      <div className="wts-card__top">
        <span className="wts-card__sym">{s.council_name}</span>
        <span>{longDate(s.date)}</span>
      </div>
      <div className="wts-card__who">
        {meeting.charAt(0).toUpperCase() + meeting.slice(1)}, {itemLabel(s)}
        <span className="wts-card__cited"> Cited</span>
      </div>
      <div className="wts-card__line">{firstWords(s.text)}</div>
    </li>
  );
}

/** The pile of records found: down the side on wide screens, along a shelf on phones (the kit's styles). It scrolls,
 * so it can be reached by keyboard. */
export const Pile = forwardRef<HTMLDivElement, { sources: SourceCard[]; dealt: number; lit: number[]; checked: number[] }>(
  function Pile({ sources, dealt, lit, checked }, ref) {
    return (
      <div className="wts-pile" tabIndex={0} aria-label="The records found" id="pile" ref={ref}>
        <ul>
          {sources.slice(0, dealt).map((s, i) => (
            <Card key={s.n} s={s} cited={lit.includes(s.n)} checked={checked.includes(s.n)} tilt={((i % 5) - 2) * 1.2} />
          ))}
        </ul>
      </div>
    );
  },
);
