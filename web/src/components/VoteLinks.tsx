/** Lists of links to named votes, as the server writes them in a page's readable text (api/plaintext.py): on a
 * council's page, its budget votes and every vote by year; on a vote's page, the votes near it. Every named vote can
 * be reached by a plain link, for readers and search engines alike. */
import type { VoteLink } from "../api";
import { KIND_LABEL, longDate, sideLabel } from "../format";

/** The result as the minutes give it, or nothing where it doesn't agree with the count (api/titles.py, outcome). */
export function shownOutcome(v: Pick<VoteLink, "outcome" | "counts" | "partial" | "question">): string {
  const c = v.counts;
  if (v.partial || v.question === "motion or amendment") return v.outcome;
  if ((v.outcome === "carried" && c.for < c.against) || (v.outcome === "lost" && c.for > c.against)) return "";
  return v.outcome;
}

/** "lost, for 10, against 19, abstained 2" */
export function shortTally(v: VoteLink): string {
  const sides = (["for", "against", "abstain"] as const)
    .map((side) => `${sideLabel(side, v.question)} ${v.counts[side]}`)
    .join(", ");
  const outcome = shownOutcome(v);
  return `${outcome ? `${outcome}, ` : ""}${sides}`.toLowerCase();
}

export function voteHref(id: string): string {
  return `/votes/${encodeURIComponent(id).replace(/%3A/gi, ":")}`;
}

export function VoteLinks({ votes }: { votes: VoteLink[] }) {
  return (
    <ul className="vote-links">
      {votes.map((v) => (
        <li key={v.vote_id}>
          <a href={voteHref(v.vote_id)}>{v.heading || v.item || "Named vote"}</a>: {KIND_LABEL[v.kind] || ""},{" "}
          {longDate(v.date)}; {shortTally(v)}.
        </li>
      ))}
    </ul>
  );
}

/** Named votes grouped by the year of their meeting, newest first (as they come). */
export function byYear<T extends { date: string }>(votes: T[]): [string, T[]][] {
  const years = new Map<string, T[]>();
  for (const v of votes) {
    const y = (v.date || "").slice(0, 4) || "Undated";
    years.set(y, [...(years.get(y) || []), v]);
  }
  return [...years.entries()];
}
