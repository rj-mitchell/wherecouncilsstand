/** One council, or one strategic authority: coverage, the party in control over time (an authority's mayors),
 * members, named votes and recent meetings, and the links between authorities and their councils. */
import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { getCouncil, type CouncilPage } from "./api";
import { SisterLinks } from "./components/Sister";
import { Tally } from "./components/VoteMarks";
import { KIND_LABEL, longDate, markNav, monthYear, number, partyColour, setTitle, voteOn } from "./format";

const PAGE = 25;
const AUTHORITY = "strategic_authority";

/** "Part of: West Yorkshire Combined Authority" on a council's page. */
function PartOf({ c }: { c: CouncilPage }) {
  const links = c.authorities || [];
  if (!links.length) return null;
  return (
    <p className="part-of">
      Part of:{" "}
      {links.map((a, i) => (
        <span key={a.gss}>
          {i > 0 && ", "}
          <a href={`/councils/${encodeURIComponent(a.gss)}`}>{a.name}</a>
          {a.role === "constituent" ? "" : ` (${a.role_name.toLowerCase()})`}
        </span>
      ))}
    </p>
  );
}

function Votes({ c, whose }: { c: CouncilPage; whose: string }) {
  const [shown, setShown] = useState(PAGE);
  return (
    <>
      <h2 className="minute-heading">Named votes ({number(c.votes.length)})</h2>
      {c.votes.length === 0 ? (
        <p className="small">No named votes were found in {whose}.</p>
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
    </>
  );
}

function ByYear({ c, kinds }: { c: CouncilPage; kinds: (keyof CouncilPage["by_year"][number])[] }) {
  return (
    <>
      <h2 className="minute-heading">Meetings by year</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Year</th>
              {kinds.map((k) => (
                <th key={k} className="num">
                  {KIND_LABEL[k]}
                </th>
              ))}
              <th className="num">With minutes</th>
            </tr>
          </thead>
          <tbody>
            {c.by_year.map((y) => (
              <tr key={y.year}>
                <td>{y.year}</td>
                {kinds.map((k) => (
                  <td key={k} className="num">
                    {y[k]}
                  </td>
                ))}
                <td className="num">{y.with_minutes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function Recent({ c }: { c: CouncilPage }) {
  return (
    <>
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
  );
}

const SOURCE: Record<string, string> = {
  "home council": "home council's record",
  authority: "the authority's record",
  "as elected": "as elected",
};

/** A strategic authority's page (decisions 17 to 20). */
function Authority({ c }: { c: CouncilPage }) {
  const regions = (c.regions || []).map((r) => r.name).join(" and ") || c.region_name;
  const constituents = (c.constituents || []).filter((m) => m.role === "constituent");
  const others = (c.constituents || []).filter((m) => m.role !== "constituent");
  const mayors = c.mayors || [];
  const short = c.name.replace(/ (Mayoral )?Combined( County)? Authority$/, "");
  const category = c.category_name ? `; ${c.category_name.charAt(0).toLowerCase()}${c.category_name.slice(1)}` : "";
  const councilList = (rows: typeof constituents) =>
    rows.map((m, i) => (
      <span key={m.gss}>
        {i > 0 && ", "}
        <a href={`/councils/${encodeURIComponent(m.gss)}`}>{m.name}</a>
        {m.from ? ` (from ${longDate(m.from)})` : ""}
        {m.to ? ` (until ${longDate(m.to)})` : ""}
      </span>
    ));
  const mayorSection = (
    <>
      <h2 className="minute-heading">{mayors.length ? "Mayors" : "Mayor"}</h2>
      {mayors.length ? (
        <>
          <ul className="timeline">
            {mayors.map((m) => (
              <li key={m.from}>
                <span>
                  From {longDate(m.from)}
                  {m.to ? ` to ${longDate(m.to)}` : ""}
                </span>
                <span>
                  {m.name} ({m.party_name})
                </span>
              </li>
            ))}
          </ul>
          <p className="small">
            Each with the party they were elected for. A strategic authority isn't run by a party: its mayor's party is
            shown in place of a party in control, and briefings group it with authorities whose mayor has the same party,
            never with councils.
          </p>
        </>
      ) : (
        <p className="small">
          It has no mayor, so no single party controls it: its members are appointed by its councils, each with the same
          say.
        </p>
      )}
    </>
  );
  return (
    <>
      <p className="meta">
        <a href="/councils">Councils</a> · Strategic authority · {regions}
      </p>
      <h1>{c.name}</h1>
      <p>
        {c.kind_name}
        {category}
        {c.created ? `. Created ${c.created}` : ""}.
      </p>
      {constituents.length > 0 && <p>Constituent councils: {councilList(constituents)}.</p>}
      {others.length > 0 && <p>Non-constituent councils: {councilList(others)}.</p>}
      {!c.loaded ? (
        <>
          <p className="notice">
            This strategic authority isn't covered yet. {c.reasons.join(" ")} Strategic authorities are covered when
            their minutes are published through a system the site can read and their site can be read.
          </p>
          {mayorSection}
        </>
      ) : (
        <>
          <p className="lede">
            Board, and overview and scrutiny committee meetings from {monthYear(c.from)} to {monthYear(c.to)}, read from
            the authority's {c.site ? <a href={c.site}>own record</a> : "own record"}.
          </p>
          <div className="cards">
            <div className="card">
              <span className="figure">{c.control?.mayor || "No mayor"}</span>
              <span className="label">
                {c.control?.mayor
                  ? `mayor (${c.control.name.replace(/^Mayor: /, "")}) since ${longDate(c.control.since)}`
                  : "no single party"}
              </span>
            </div>
            <div className="card">
              <span className="figure">{number(c.meetings)}</span>
              <span className="label">
                meetings: {number(c.board_meetings)} board, {number(c.scrutiny_meetings)} overview and scrutiny
                {c.mayor_meetings ? `, ${number(c.mayor_meetings)} of the mayor's decisions` : ""}
              </span>
            </div>
            <div className="card">
              <span className="figure">{number(c.named_votes)}</span>
              <span className="label">named votes recorded in the minutes</span>
            </div>
          </div>
          <p>
            <a className="button" href={`/?q=${encodeURIComponent(`What has the ${c.name} decided about `)}`}>
              Ask about {short}
            </a>
          </p>
          {mayorSection}

          {c.members && c.members.members.length > 0 && (
            <>
              <h2 className="minute-heading">Members</h2>
              <p className="small">
                Listed at the {c.members.committee} meeting of {longDate(c.members.date)}, with each member's role and
                their party on the date: from their home council's record where the site has it, otherwise the
                authority's. Appointed members who aren't councillors aren't named.
              </p>
              <div className="table-wrap">
                <table>
                  <thead>
                    <tr>
                      <th>Member</th>
                      <th>Role</th>
                      <th>Party on the date</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.members.members.map((m, i) => (
                      <tr key={`${m.name}-${i}`}>
                        <td>
                          {m.name || <span className="muted">Name not shown (not a councillor)</span>}
                          {m.home && (
                            <div className="muted">
                              <a href={`/councils/${encodeURIComponent(m.home.gss)}`}>{m.home.name}</a>
                            </div>
                          )}
                        </td>
                        <td>
                          {m.role_name}
                          {m.attendance && !/^present/i.test(m.attendance) && (
                            <div className="muted">{m.attendance}</div>
                          )}
                        </td>
                        <td>
                          {m.party ? (
                            <>
                              <span className="swatch" style={{ ["--c" as string]: partyColour(m.party_code) }} />
                              {m.party}
                              <div className="muted">{SOURCE[m.party_source || ""] || "as recorded"}</div>
                            </>
                          ) : (
                            <span className="muted">None recorded</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          <Votes c={c} whose="this authority's minutes" />
          <ByYear c={c} kinds={c.mayor_meetings ? ["board", "scrutiny", "mayor"] : ["board", "scrutiny"]} />
          <Recent c={c} />
        </>
      )}
    </>
  );
}

function App() {
  const gss = decodeURIComponent(location.pathname.split("/")[2] || "");
  const [c, setC] = useState<CouncilPage | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    getCouncil(gss)
      .then((d) => {
        setC(d);
        setTitle(d.name);
      })
      .catch((e: Error) => setError(e.message));
  }, [gss]);
  if (error)
    return (
      <>
        <h1>Council</h1>
        <p className="notice">{error}</p>
      </>
    );
  if (!c) return <p className="progress">Loading the council</p>;
  if (c.type === AUTHORITY) return <Authority c={c} />;
  const ll = c.landlords;
  const landlords = ll && (ll.council || ll.area) && (
    <SisterLinks site="landlords">
      <ul>
        {ll.council && (
          <li>
            <a href={ll.council.url}>{ll.council.name} as a landlord</a>
          </li>
        )}
        {ll.area && (
          <li>
            <a href={ll.area.url}>
              {ll.area.landlords === 1
                ? `The social landlord with homes in ${ll.area.name}`
                : `The ${number(ll.area.landlords)} social landlords with homes in ${ll.area.name}`}
            </a>
          </li>
        )}
      </ul>
    </SisterLinks>
  );
  const short = c.name.replace(/ (Metropolitan Borough|Borough|District|County|City|County Borough) Council$| Council$/, "");
  return (
    <>
      <p className="meta">
        <a href="/councils">Councils</a> · {c.type_name} · {c.region_name}
      </p>
      <h1>{c.name}</h1>
      <PartOf c={c} />
      {!c.loaded ? (
        <>
          <p className="notice">
            This council isn't covered yet. {c.reasons.join(" ")} Councils are covered when their minutes are published
            through a system the site can read (Modern.gov, CMIS or CoINS) and their site can be read.
          </p>
          {landlords}
        </>
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
          {landlords}

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

          <Votes c={c} whose="this council's minutes" />
          <ByYear c={c} kinds={c.policy_meetings ? ["council", "cabinet", "policy"] : ["council", "cabinet"]} />
          <Recent c={c} />
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
