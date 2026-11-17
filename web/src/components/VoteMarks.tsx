/** Neutral marks for the sides of a vote: filled for, outlined against, hatched abstained (docs/DESIGN.md). */
import type { VoteSummary } from "../api";
import { sideLabel } from "../format";

export function Mark({ side }: { side: "for" | "against" | "abstain" }) {
  return <span className={`mark ${side}`} aria-hidden="true" />;
}

export function Tally({ counts, question }: { counts: VoteSummary["counts"]; question?: string | null }) {
  return (
    <span className="vote-tally">
      {(["for", "against", "abstain"] as const).map((side) => (
        <span key={side}>
          <Mark side={side} />
          {sideLabel(side, question)} {counts[side]}
        </span>
      ))}
    </span>
  );
}
