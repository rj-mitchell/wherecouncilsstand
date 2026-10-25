/** Every council in England and Wales: which are covered, from when, and which party is in control. */
import { StrictMode, useEffect, useMemo, useState } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { getCouncils, type CouncilRow } from "./api";
import { markNav, monthYear, number, setTitle } from "./format";

const WHY_NOT: Record<string, string> = {
  blocked: "Its Modern.gov site refused automated requests.",
  unreachable: "Its Modern.gov site couldn't be reached.",
  none: "It doesn't publish its minutes through Modern.gov.",
  ok: "Its Modern.gov site returned errors when loaded.",
};

function App() {
  const [rows, setRows] = useState<CouncilRow[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState("");
  const [nation, setNation] = useState("");
  const [control, setControl] = useState("");
  useEffect(() => {
    setTitle("Councils");
    getCouncils().then((d) => setRows(d.councils)).catch((e: Error) => setError(e.message));
  }, []);
  const controls = useMemo(
    () => [...new Set((rows || []).filter((r) => r.control).map((r) => r.control!.name))].sort(),
    [rows],
  );
  if (error) return <p className="notice">The list of councils couldn't be loaded: {error}</p>;
  if (!rows) return <p className="progress">Loading the councils</p>;
  const match = (r: CouncilRow) =>
    (!q || r.name.toLowerCase().includes(q.toLowerCase())) && (!nation || r.nation === nation);
  const covered = rows.filter((r) => r.loaded && match(r) && (!control || r.control?.name === control));
  const missing = rows.filter((r) => !r.loaded && match(r));
  return (
    <>
      <h1>Councils</h1>
      <p className="lede">
        {number(rows.filter((r) => r.loaded).length)} of the {number(rows.length)} principal councils in England and Wales are
        covered: those whose minutes are published through Modern.gov and could be read. Coverage starts in May 2018.
      </p>
      <div className="filters" role="search">
        <div className="field">
          <label htmlFor="q">Council name</label>
          <input id="q" value={q} onChange={(e) => setQ(e.target.value)} placeholder="For example: Barnsley" />
        </div>
        <div className="field">
          <label htmlFor="nation">Nation</label>
          <select id="nation" value={nation} onChange={(e) => setNation(e.target.value)}>
            <option value="">England and Wales</option>
            <option value="england">England</option>
            <option value="wales">Wales</option>
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
      <div className="table-wrap">
        <table>
          <thead>
            <tr>
              <th>Council</th>
              <th>In overall control</th>
              <th className="num wide-only">Meetings</th>
              <th className="num">Named votes</th>
              <th className="wide-only">From</th>
            </tr>
          </thead>
          <tbody>
            {covered.map((r) => (
              <tr key={r.gss}>
                <td>
                  <a href={`/councils/${r.gss}`}>{r.name}</a>
                  <div className="muted">{r.type_name} · {r.region_name}</div>
                </td>
                <td>{r.control?.name || "Not recorded"}</td>
                <td className="num wide-only">{number(r.meetings)}</td>
                <td className="num">{number(r.named_votes)}</td>
                <td className="wide-only">{monthYear(r.from)}</td>
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
                    <td>{r.name}</td>
                    <td>{WHY_NOT[r.status] || "Not loaded yet."}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
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
