/** Every principal council in the UK, and England's strategic authorities: which are covered, from when, and which
 * party is in control (for an authority, its mayor's party). */
import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { getCouncils, type CouncilRow, type Coverage } from "./api";
import { CoverageLabel } from "./components/Coverage";
import { markNav, monthYear, number, setTitle } from "./format";

function CoverageCell({ r }: { r: CouncilRow }) {
  return (
    <>
      <CoverageLabel c={r.coverage} />
      {r.reasons.map((why) => (
        <div key={why} className="muted">
          {why}
        </div>
      ))}
    </>
  );
}

const AUTHORITY = "strategic_authority";

function Authorities({ rows }: { rows: CouncilRow[] }) {
  const covered = rows.filter((r) => r.loaded).length;
  return (
    <>
      <h2 className="minute-heading" id="strategic-authorities">
        Strategic authorities ({number(covered)} of {number(rows.length)} covered)
      </h2>
      <p>
        England's combined authorities, combined county authorities and the Greater London Authority: their boards, and
        their overview and scrutiny committees. Each is shown with its mayor's party, which isn't control of the authority
        or of its councils; one without a mayor has no single party.
      </p>
      <div className="table-wrap">
        <table className="stack-table" role="table">
          <thead role="rowgroup">
            <tr role="row">
              <th scope="col" role="columnheader">Strategic authority</th>
              <th scope="col" role="columnheader">Mayor</th>
              <th scope="col" role="columnheader" className="num wide-only">Meetings</th>
              <th scope="col" role="columnheader" className="num">Named votes</th>
              <th scope="col" role="columnheader">Coverage</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {rows.map((r) => (
              <tr key={r.gss} role="row">
                <th scope="row" role="rowheader">
                  <a href={`/councils/${encodeURIComponent(r.gss)}`}>{r.name}</a>
                  <div className="muted">
                    {r.kind_name} · {(r.regions || []).map((x) => x.name).join(" and ") || r.region_name}
                  </div>
                </th>
                <td role="cell" data-label="Mayor">
                  {r.control?.mayor ? `${r.control.mayor} (${r.control.name.replace(/^Mayor: /, "")})` : "No mayor"}
                </td>
                <td role="cell" className="num wide-only">{r.loaded ? number(r.meetings) : "–"}</td>
                <td role="cell" className="num" data-label="Named votes">{r.loaded ? number(r.named_votes) : "–"}</td>
                <td role="cell" data-label="Coverage">
                  <CoverageCell r={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

function App() {
  const [all, setRows] = useState<CouncilRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [nation, setNation] = useState("");
  const [control, setControl] = useState("");
  const [coverage, setCoverage] = useState("");
  useEffect(() => {
    setTitle("Councils");
    getCouncils().then((d) => setRows(d.councils)).catch((e: Error) => setError(e.message));
  }, []);
  const rows = useMemo(() => (all ? all.filter((r) => r.type !== AUTHORITY) : null), [all]);
  const authorities = useMemo(() => (all ? all.filter((r) => r.type === AUTHORITY) : []), [all]);
  const controls = useMemo(
    () => [...new Set((rows || []).filter((r) => r.control).map((r) => r.control!.name))].sort(),
    [rows],
  );
  if (error)
    return (
      <>
        <h1>Councils</h1>
        <p className="notice">The list of councils couldn't be loaded: {error}</p>
      </>
    );
  if (!rows) return <p className="progress">Loading the councils</p>;
  const match = (r: CouncilRow) =>
    (!q || r.name.toLowerCase().includes(q.toLowerCase())) &&
    (!nation || r.nation === nation) &&
    (!coverage || r.coverage === coverage);
  const count = (k: Coverage) => rows.filter((r) => r.coverage === k).length;
  const covered = rows.filter((r) => r.loaded && match(r) && (!control || r.control?.name === control));
  const missing = rows.filter((r) => !r.loaded && match(r));
  return (
    <>
      <h1>Councils</h1>
      <p className="lede">
        {number(rows.filter((r) => r.loaded).length)} of the {number(rows.length)} principal councils in the UK are
        covered: those whose minutes are published through a system we can read (Modern.gov, CMIS or CoINS). Coverage
        starts in May 2018.
      </p>
      <p>
        Coverage: {(["full", "partial", "not_yet"] as const).map((k, i) => (
          <span key={k}>
            {i > 0 && " · "}
            <CoverageLabel c={k} /> {number(count(k))}
          </span>
        ))}
        . Coverage says how much of each council's record the site can read, not how well the council works. It is
        worked out from what is loaded, and kept up to date by the nightly update.
        {authorities.length > 0 && (
          <>
            {" "}
            England's <a href="#strategic-authorities">strategic authorities</a> are listed after the councils.
          </>
        )}
      </p>
      <div className="filters" role="search">
        <div className="field">
          <label htmlFor="q">Council name</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: Barnsley" />
        </div>
        <div className="field">
          <label htmlFor="nation">Nation</label>
          <select id="nation" value={nation} onChange={(e) => setNation(e.target.value)}>
            <option value="">All of the UK</option>
            <option value="england">England</option>
            <option value="wales">Wales</option>
            <option value="scotland">Scotland</option>
            <option value="northern_ireland">Northern Ireland</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="coverage">Coverage</label>
          <select id="coverage" value={coverage} onChange={(e) => setCoverage(e.target.value)}>
            <option value="">Any</option>
            <option value="full">Full</option>
            <option value="partial">Partial</option>
            <option value="not_yet">Not yet</option>
          </select>
        </div>
        <div className="field">
          <label htmlFor="control">In control now</label>
          <select id="control" value={control} onChange={(e) => setControl(e.target.value)}>
            <option value="">Any</option>
            {controls.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </div>
      </div>
      <h2 className="minute-heading">Covered ({number(covered.length)})</h2>
      {/* On a phone each row is a block: the council as its heading, then the rest as labelled pairs (data-label;
          docs/DESIGN.md, "Tables"). The roles keep it a table for screen readers once the display changes. */}
      <div className="table-wrap">
        <table className="stack-table" role="table">
          <thead role="rowgroup">
            <tr role="row">
              <th scope="col" role="columnheader">Council</th>
              <th scope="col" role="columnheader">In overall control</th>
              <th scope="col" role="columnheader" className="num wide-only">Meetings</th>
              <th scope="col" role="columnheader" className="num">Named votes</th>
              <th scope="col" role="columnheader" className="wide-only">From</th>
              <th scope="col" role="columnheader">Coverage</th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {covered.map((r) => (
              <tr key={r.gss} role="row">
                <th scope="row" role="rowheader">
                  <a href={`/councils/${r.gss}`}>{r.name}</a>
                  <div className="muted">{r.type_name} · {r.region_name}</div>
                </th>
                <td role="cell" data-label="In overall control">{r.control?.name || "Not recorded"}</td>
                <td role="cell" className="num wide-only">{number(r.meetings)}</td>
                <td role="cell" className="num" data-label="Named votes">{number(r.named_votes)}</td>
                <td role="cell" className="wide-only nowrap">{monthYear(r.from)}</td>
                <td role="cell" data-label="Coverage">
                  <CoverageCell r={r} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="small">
        "In overall control" is read from the councillors listed at the council's latest full council meeting: a party with
        more than half of them, otherwise no overall control. It is as the council recorded it, not a judgement.
      </p>
      {!control && missing.length > 0 && (
        <>
          <h2 className="minute-heading">Not covered yet ({number(missing.length)})</h2>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Council</th>
                  <th>Why not</th>
                </tr>
              </thead>
              <tbody>
                {missing.map((r) => (
                  <tr key={r.gss}>
                    <td>
                      <a href={`/councils/${encodeURIComponent(r.gss)}`}>{r.name}</a>
                    </td>
                    <td>
                      <CoverageCell r={r} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
      {authorities.length > 0 && <Authorities rows={authorities} />}
    </>
  );
}

markNav();
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
