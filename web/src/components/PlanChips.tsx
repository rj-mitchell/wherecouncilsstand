/** What the question was read as: the filters the evidence was limited to. */
import type { Meta, Plan } from "../api";
import { longDate } from "../format";

const PARTY: Record<string, string> = {
  LAB: "Labour", CON: "Conservative", LD: "Liberal Democrats", GRN: "Green", REF: "Reform UK", PC: "Plaid Cymru",
  UKIP: "UKIP", LIB: "Liberal Party", IND: "Independent", NOC: "no overall control",
};

const NATION: Record<string, string> = {
  england: "England", wales: "Wales", scotland: "Scotland", northern_ireland: "Northern Ireland",
};

export function PlanChips({ plan, meta, councilNames }: { plan: Plan; meta: Meta | null; councilNames: Record<string, string> }) {
  const f = plan.filters || {};
  const chips: string[] = [];
  if (f.date_from || f.date_to)
    chips.push(`${f.date_from ? longDate(f.date_from) : "May 2018"} to ${f.date_to ? longDate(f.date_to) : "today"}`);
  for (const g of f.councils || []) chips.push(councilNames[g] || g);
  for (const c of f.control || [])
    chips.push(c === "NOC" ? "Councils under no overall control" : `Councils under ${PARTY[c] || c.replace(/^LOCAL:/, "")} control`);
  for (const p of f.parties || []) chips.push(`Naming ${PARTY[p] || p} councillors`);
  for (const n of f.nations || []) chips.push(NATION[n] || n);
  for (const r of f.regions || []) chips.push(meta?.regions[r] || r);
  for (const t of f.council_types || []) chips.push(meta?.types[t] || t);
  for (const k of f.kinds || []) chips.push(k === "council" ? "Full council" : k === "cabinet" ? "Cabinet" : k);
  if (f.named_votes_only) chips.push("Named votes only");
  return (
    <div className="plan">
      {plan.interpretation && <p className="small">{plan.interpretation}</p>}
      {chips.length > 0 && (
        <ul className="chips" aria-label="The evidence was limited to">
          {chips.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
