/** One council: coverage, the party in control over time, members by party, named votes and recent meetings. */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { getCouncil, type CouncilPage } from "./api";
import { Tally } from "./components/VoteMarks";
import { KIND_LABEL, longDate, markNav, monthYear, number, partyColour, setTitle, voteOn } from "./format";

const PAGE = 25;

function App() {
  const gss = decodeURIComponent(location.pathname.split("/")[2] || "");
  const [c, setC] = useState<CouncilPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [shown, setShown] = useState(PAGE);
  useEffect(() => {
    getCouncil(gss)
      .then((d) => {
        setC(d);
        setTitle(d.name);
      })
      .catch((e: Error) => setError(e.message));
  }, [gss]);
  if (error) return <p className="notice">{error}</p>;
  if (!c) return <p className="progress">Loading the council</p>;
  const short = c.name.replace(/ (Metropolitan Borough|Borough|District|County|City|County Borough) Council$| Council$/, "");
  return (
    <>
      <p className="meta">
        <a href="/councils">Councils</a> · {c.type_name} · {c.region_name}
      </p>
      <h1>{c.name}</h1>
      {!c.loaded ? (
        <p className="notice">
          This council isn't covered yet: its minutes aren't published through Modern.gov, or its site couldn't be read.
        </p>
      ) : (
        <>
          <p className="lede">
            Full council and cabinet meetings from {monthYear(c.from)} to {monthYear(c.to)}, read from the council's{" "}
            {c.site ? <a href={c.site}>own record</a> : "own record"}.
          </p>
          <div className="cards">
            <div className="card">
              <span className="figure">{c.control?.name || "Not recorded"}</span>
              <span className="label">in overall control{c.control?.as_of ? `, as listed on ${longDate(c.control.as_of)}` : ""}</span>
            </div>
            <div className="card">
              <span className="figure">{number(c.meetings)}</span>
              <span className="label">
                meetings: {number(c.council_meetings)} full council, {number(c.cabinet_meetings)} cabinet
                {c.policy_meetings ? `, ${number(c.policy_meetings)} policy committee` : ""}
              </span>
            </div>
            <div className="card">
              <span className="figure">{number(c.named_votes)}</span>
              <span className="label">named votes recorded in the minutes</span>
            </div>
          </div>
          <p>
            <a className="button" href={`/?q=${encodeURIComponent(`What has ${short} council decided about `)}`}>
              Ask about {short}
            </a>
          </p>

          {c.seats && (
            <>
              <h2 className="minute-heading">Members by party</h2>
              <p className="small">
                The {number(c.seats.total)} councillors listed at the full council meeting of {longDate(c.seats.date)}, with
                their party as the council recorded it.
              </p>
              <div className="seats-bar" role="img"
                aria-label={c.seats.parties.map((p) => `${p.name} ${p.members}`).join(", ")}>
                {c.seats.parties.map((p) => (
                  <span key={p.code} title={`${p.name}: ${p.members}`}
                    style={{ flexGrow: p.members, ["--c" as string]: partyColour(p.code) }} />
                ))}
              </div>
              <ul className="party-list">
                {c.seats.parties.map((p) => (
                  <li key={p.code}>
                    <span>
                      <span className="swatch" style={{ ["--c" as string]: partyColour(p.code) }} />
                      {p.name}
                    </span>
                    <span>{number(p.members)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}

          {c.control_timeline.length > 0 && (
            <>
              <h2 className="minute-heading">Party in overall control</h2>
              <ul className="timeline">
                {c.control_timeline.map((t) => (
                  <li key={t.from}>
                    <span>From {monthYear(t.from)}</span>
                    <span>{t.name}</span>
                  </li>
                ))}
              </ul>
              <p className="small">
                Read from each full council meeting's list of members: a party with more than half of them is in overall
                control. Changes show from the first meeting at which they were recorded.
              </p>
            </>
          )}

          <h2 className="minute-heading">Named votes ({number(c.votes.length)})</h2>
          {c.votes.length === 0 ? (
            <p className="small">No named votes were found in this council's minutes.</p>
          ) : (
            <ol className="sources">
              {c.votes.slice(0, shown).map((v) => (
                <li key={v.vote_id} className={`source ${v.kind}`}>
                  <span className="source-n">{v.number || "·"}</span>
                  <div>
                    <h3>
                      <a href={`/votes/${encodeURIComponent(v.vote_id)}`}>{v.item || "Named vote"}</a>
                    </h3>
                    <p className="meta">
                      {KIND_LABEL[v.kind] || v.committee} · {longDate(v.date)}
                      {v.question ? ` ·${voteOn(v.question)}` : ""}
                      {v.outcome ? ` · ${v.outcome}` : ""}
                    </p>
                    <Tally counts={v.counts} question={v.question} />
                    {v.partial && <p className="small">Only one side could be read from the minutes.</p>}
                  </div>
                </li>
              ))}
            </ol>
          )}
          {shown < c.votes.length && (
            <p>
              <button className="button secondary" onClick={() => setShown(shown + PAGE)}>
                Show more votes
              </button>
            </p>
          )}

          <h2 className="minute-heading">Meetings by year</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Year</th>
                  <th className="num">Full council</th>
                  <th className="num">Cabinet</th>
                  {c.policy_meetings ? <th className="num">Policy committee</th> : null}
                  <th className="num">With minutes</th>
                </tr>
              </thead>
              <tbody>
                {c.by_year.map((y) => (
                  <tr key={y.year}>
                    <td>{y.year}</td>
                    <td className="num">{y.council}</td>
                    <td className="num">{y.cabinet}</td>
                    {c.policy_meetings ? <td className="num">{y.policy}</td> : null}
                    <td className="num">{y.with_minutes}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <h2 className="minute-heading">Latest meetings</h2>
          <ul className="timeline">
            {c.recent.map((m) => (
              <li key={m.url}>
                <span>{longDate(m.date)}</span>
                <span>
                  <a href={m.url}>{m.committee}</a>
                  {m.items_with_minutes ? "" : <span className="muted"> · minutes not published yet</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}

markNav();
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
