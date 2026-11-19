/** One named vote: who voted which way, with their party on the date, and the passage it was read from. */
import "./styles.css";
import { drawWhenLoaded } from "./draw";
import { getVote, type VotePage } from "./api";
import { Statements } from "./components/Statements";
import { VoteLinks, voteHref } from "./components/VoteLinks";
import { Mark, Tally } from "./components/VoteMarks";
import { KIND_LABEL, longDate, markNav, setTitle, sideLabel, voteOn } from "./format";

function Vote({ v, id }: { v: VotePage; id: string }) {
  return (
    <>
      <p className="meta">
        <a href={`/councils/${v.gss}`}>{v.council}</a>
      </p>
      <h1>{v.heading || v.item || "Named vote"}</h1>
      <p className="lede">
        {KIND_LABEL[v.kind] || v.committee}, {longDate(v.date)}
        {`: a named vote${voteOn(v.question)}`}
        {v.outcome ? `, ${v.outcome}` : ""}.
      </p>
      <p>
        <Tally counts={v.counts} question={v.question} />
      </p>
      <p className="small">
        {v.is_authority
          ? `The authority’s mayor on the date: ${(v.control || "not recorded").replace(/^Mayor: /, "")} (a strategic authority isn’t run by a party). Each member’s party is the one their home council recorded for them at the time, where the site has it; otherwise the authority’s.`
          : `Party in overall control of the council on the date: ${v.control || "not recorded"}.`}{" "}
        {v.is_authority ? null : "Each councillor’s party is the one the council recorded for them at the time."}
      </p>
      {v.partial && (
        <p className="notice">
          Only one side of this vote could be read from the minutes. The others may be recorded in a form that couldn’t be
          read, or not at all.
        </p>
      )}
      <div className="vote-sides">
        {(["for", "against", "abstain"] as const).map((side) => {
          const members = v.members.filter((m) => m.side === side);
          if (!members.length) return null;
          return (
            <section key={side} className="vote-side">
              <h2>
                <Mark side={side} />
                {sideLabel(side, v.question)} ({members.length})
              </h2>
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
      <h2>From the minutes</h2>
      {v.from_table ? (
        <p className="small">The minutes set this vote out as a table, with a row or column for each councillor.</p>
      ) : (
        <blockquote className="excerpt">{v.excerpt}</blockquote>
      )}
      <p className="small">
        <a href={v.url}>The item in the council’s own minutes</a>. Names are matched to the councillors listed at the
        meeting. The names of people who aren’t councillors are removed.
      </p>
      {v.siblings && v.siblings.length > 0 && (
        <>
          <h2>Other named votes on this item</h2>
          <VoteLinks votes={v.siblings} />
        </>
      )}
      {v.same_meeting && v.same_meeting.length > 0 && (
        <>
          <h2>Other named votes at this meeting</h2>
          <VoteLinks votes={v.same_meeting} />
        </>
      )}
      {(v.earlier || v.later) && (
        <nav className="vote-steps" aria-label="Named votes before and after this one">
          <ul>
            {(
              [
                [`Earlier named vote at ${v.council}`, v.earlier],
                [`Later named vote at ${v.council}`, v.later],
              ] as const
            ).map(([what, x]) =>
              x ? (
                <li key={what}>
                  {what}: <a href={voteHref(x.vote_id)}>{x.heading || "Named vote"}</a>, {longDate(x.date)}
                </li>
              ) : null,
            )}
          </ul>
        </nav>
      )}
      <p className="small">
        <a href={`/corrections?page=${encodeURIComponent(location.href)}`}>Report a problem with this vote</a>, or see{" "}
        <a href="/named">If you’re named on this site</a>.
      </p>
      <Statements page={`/votes/${id}`} />
    </>
  );
}

markNav();
const id = decodeURIComponent(location.pathname.split("/")[2] || "");
drawWhenLoaded(
  () =>
    getVote(id).then((v) => {
      setTitle(v.title || `${v.item || "Named vote"}, ${v.council}`);
      return v;
    }),
  (v) => <Vote v={v} id={id} />,
  (message) => (
    <>
      <h1>Named vote</h1>
      <p className="notice">{message}</p>
    </>
  ),
  "Getting the vote",
);
