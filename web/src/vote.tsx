/** One named vote: who voted which way, with their party on the date, and the passage it was read from. */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { getVote, type VotePage } from "./api";
import { Mark, Tally } from "./components/VoteMarks";
import { KIND_LABEL, longDate, markNav, setTitle, sideLabel, voteOn } from "./format";

function App() {
  const id = decodeURIComponent(location.pathname.split("/")[2] || "");
  const [v, setV] = useState<VotePage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getVote(id)
      .then((d) => {
        setV(d);
        setTitle(`${d.item || "Named vote"}, ${d.council}`);
      })
      .catch((e: Error) => setError(e.message));
  }, [id]);
  if (error) return <p className="notice">{error}</p>;
  if (!v) return <p className="progress">Loading the vote</p>;
  return (
    <>
      <p className="meta">
        <a href="/councils">Councils</a> · <a href={`/councils/${v.gss}`}>{v.council}</a>
      </p>
      <h1>{v.item || "Named vote"}</h1>
      <p className="lede">
        {KIND_LABEL[v.kind] || v.committee}, {longDate(v.date)}
        {`: a named vote${voteOn(v.question)}`}
        {v.outcome ? `, ${v.outcome}` : ""}.
      </p>
      <p>
        <Tally counts={v.counts} question={v.question} />
      </p>
      <p className="small">
        Party in overall control of the council on the date: {v.control || "not recorded"}. Each councillor's party is the one
        the council recorded for them at the time.
      </p>
      {v.partial && (
        <p className="notice">
          Only one side of this vote could be read from the minutes. The others may be recorded in a form that couldn't be
          read, or not at all.
        </p>
      )}
      <div className="vote-sides">
        {(["for", "against", "abstain"] as const).map((side) => {
          const members = v.members.filter((m) => m.side === side);
          if (!members.length) return null;
          return (
            <section key={side} className="vote-side">
              <h3>
                <Mark side={side} />
                {sideLabel(side, v.question)} ({members.length}):
              </h3>
              <ul>
                {members.map((m, i) => (
                  <li key={i}>
                    {m.name}
                    {m.party ? <span className="muted"> ({m.party})</span> : <span className="muted"> (not matched to a member)</span>}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
      <h2 className="minute-heading">From the minutes</h2>
      {v.from_table ? (
        <p className="small">The minutes set this vote out as a table, with a row or column for each councillor.</p>
      ) : (
        <blockquote className="prose">{v.excerpt}</blockquote>
      )}
      <p className="small">
        <a href={v.url}>The item in the council's own minutes</a> · Names are matched to the councillors listed at the meeting.
        The names of people who aren't councillors are removed. <a href={`/corrections?page=${encodeURIComponent(location.href)}`}>Report a problem with this vote</a>
      </p>
    </>
  );
}

markNav();
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
