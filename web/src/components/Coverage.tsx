import type { Coverage } from "../api";

/** How fully the site reads each council's record, in neutral marks (docs/DESIGN.md): filled for full, half filled
 * for partial, outlined for not yet. It describes the site's reading, never the council. */
export const COVERAGE: Record<Coverage, string> = { full: "Full", partial: "Partial", not_yet: "Not yet" };

export function CoverageLabel({ c }: { c: Coverage }) {
  return (
    <span className="coverage">
      <span className={`mark coverage-${c}`} aria-hidden="true" />
      {COVERAGE[c]}
    </span>
  );
}
