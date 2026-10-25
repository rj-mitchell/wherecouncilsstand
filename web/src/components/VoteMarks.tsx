/** Neutral marks for the sides of a vote: filled for, outlined against, hatched abstained (docs/DESIGN.md). */
import type { VoteSummary } from "../api";
import { SIDE_LABEL } from "../format";

export function Mark({ side }: { side: "for" | "against" | "abstain" }) {
  return <span className={`mark ${side}`} aria-hidden="true" />;
}

export function Tally({ counts }: { counts: VoteSummary["counts"] }) {
  return (
    <span className="vote-tally">
      {(["for", "against", "abstain"] as const).map((side) => (
        <span key={side} style={{ marginInlineEnd: "0.9em" }}>
          <Mark side={side} />
          {SIDE_LABEL[side]} {counts[side]}
        </span>
      ))}
    </span>
  );
}
