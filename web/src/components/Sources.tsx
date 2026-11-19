/** The sources a briefing drew on: minutes, numbered as the briefing cites them, grouped as the evidence was balanced.
 * A group's heading names the councils' control; each source gives the people its passage is about with their own
 * party, so that no one's point reads as the controlling party's (decision 27). */
import type { SourceCard } from "../api";
import { KIND_LABEL, longDate } from "../format";

export function Sources({ sources }: { sources: SourceCard[] }) {
  if (!sources.length) return null;
  const groups: { name: string; items: SourceCard[] }[] = [];
  for (const s of sources) {
    const g = groups.find((x) => x.name === s.group);
    if (g) g.items.push(s);
    else groups.push({ name: s.group, items: [s] });
  }
  // grouped, each source's heading sits under its group's
  const Heading = groups.length > 1 ? "h4" : "h3";
  return (
    <section aria-labelledby="sources-heading" className="briefing">
      <h2 id="sources-heading">
        Sources: the councils’ own minutes ({sources.length})
      </h2>
      {groups.map((g) => (
        <div key={g.name}>
          {groups.length > 1 && <h3 className="group-heading">{g.name}</h3>}
          <ol className="sources">
            {g.items.map((s) => (
              <li key={s.n} id={`source-${s.n}`} className={`source ${s.kind}`}>
                <span className="source-n">{s.n}</span>
                <div>
                  <Heading>
                    <a href={s.url} rel="noreferrer">
                      {s.item_number ? `${s.item_number} ` : ""}
                      {s.item_title}
                    </a>
                  </Heading>
                  <p className="meta">
                    <a href={`/councils/${s.gss}`}>{s.council_name}</a>, {KIND_LABEL[s.kind] || s.committee} ({s.committee}),{" "}
                    {longDate(s.date)}
                  </p>
                  {s.named && s.named.length > 0 && (
                    <p className="small named">People in this passage, with their party on the date: {s.named.join("; ")}.</p>
                  )}
                  <details>
                    <summary>The passage</summary>
                    <blockquote>{s.text}</blockquote>
                  </details>
                  {s.votes?.length > 0 && (
                    <p className="small">
                      {s.votes.map((v, i) => (
                        <span key={v.vote_id}>
                          {i ? ", " : ""}
                          <a href={`/votes/${encodeURIComponent(v.vote_id)}`}>
                            Named vote{s.votes.length > 1 ? ` ${i + 1}` : ""}: who voted which way
                          </a>
                        </span>
                      ))}
                    </p>
                  )}
                </div>
              </li>
            ))}
          </ol>
        </div>
      ))}
    </section>
  );
}
