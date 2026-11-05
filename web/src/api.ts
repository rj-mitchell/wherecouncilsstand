/** The web service's API (src/councils/api/app.py): types and calls. */

export type Plan = {
  question: string;
  search_text: string;
  filters: {
    date_from?: string | null;
    date_to?: string | null;
    councils?: string[];
    nations?: string[];
    regions?: string[];
    council_types?: string[];
    kinds?: string[];
    control?: string[];
    parties?: string[];
    named_votes_only?: boolean;
  };
  interpretation?: string;
  parser?: string;
  group_by?: string;
  unresolved_councils?: string[];
};

export type SourceCard = {
  n: number;
  title: string;
  url: string;
  record_id: string;
  date: string;
  gss: string;
  council_name: string;
  committee: string;
  kind: string; // council | cabinet | policy
  item_title: string;
  item_number: string;
  control: string | null;
  group: string;
  text: string;
  votes: { vote_id: string; text: string }[];
};

export type Segment = { text: string; sources: number[]; status: string; loaded?: unknown[]; misquotes?: unknown[] };

export type Answer = {
  segments: Segment[];
  no_records?: boolean;
  citations_total: number;
  citations_invalid: number;
  unsupported_segments?: number;
  loaded_words?: number;
  quotes_unverified?: number;
};

export type AskEvent =
  | { type: "plan"; plan: Plan }
  | { type: "sources"; sources: SourceCard[]; candidates: number; semantic: boolean; evidence: unknown }
  | { type: "text"; text: string }
  | { type: "citation" }
  | { type: "final"; answer: Answer | null; note?: string; briefing_id?: string; cached?: boolean }
  | { type: "error"; message: string };

export type Meta = {
  site: { name: string; url: string; donate_url: string | null };
  totals: {
    councils: number;
    loaded: number;
    meetings: number;
    named_votes: number;
    from: string;
    to: string;
    ratings?: Record<string, number>;
  };
  last_update: { finished: string } | null;
  briefings: boolean;
  default_years: number;
  start: string;
  examples: string[];
  regions: Record<string, string>;
  types: Record<string, string>;
};

export type Control = { code: string; name: string; as_of?: string } | null;

export type CouncilRow = {
  gss: string;
  name: string;
  nation: string;
  type: string;
  type_name: string;
  region: string;
  region_name: string;
  site: string | null;
  status: string;
  loaded: boolean;
  meetings?: number;
  council_meetings?: number;
  cabinet_meetings?: number;
  policy_meetings?: number;
  from?: string;
  to?: string;
  with_minutes?: number;
  named_votes?: number;
  control?: Control;
  /** How well the council works here: green (fully), amber (with a gap), red (not loaded). */
  rating: "green" | "amber" | "red";
  reasons: string[];
};

export type VoteSummary = {
  vote_id: string;
  date: string;
  committee: string;
  kind: string;
  item: string;
  number: string;
  question: string;
  outcome: string;
  url: string;
  counts: { for: number; against: number; abstain: number };
  by_party: Record<"for" | "against" | "abstain", { party: string; n: number }[]>;
  partial: boolean;
};

export type CouncilPage = CouncilRow & {
  control_timeline: { from: string; code: string; name: string }[];
  seats: { date: string; total: number; parties: { code: string; name: string; members: number }[] } | null;
  by_year: { year: number; council: number; cabinet: number; policy: number; with_minutes: number }[];
  votes: VoteSummary[];
  recent: { date: string; committee: string; kind: string; url: string; items_with_minutes: number }[];
};

export type VotePage = VoteSummary & {
  gss: string;
  council: string;
  control: string | null;
  excerpt: string;
  from_table: boolean;
  members: { side: "for" | "against" | "abstain"; name: string; written: string; matched: boolean; party: string | null }[];
};

async function json<T>(r: Response): Promise<T> {
  if (!r.ok) {
    let detail = `${r.status}`;
    try {
      detail = (await r.json()).detail ?? detail;
    } catch {
      /* not JSON */
    }
    throw new Error(String(detail));
  }
  return r.json() as Promise<T>;
}

export const getMeta = () => fetch("/api/meta").then((r) => json<Meta>(r));
export const getCouncils = () =>
  fetch("/api/councils").then((r) => json<{ totals: Meta["totals"]; councils: CouncilRow[] }>(r));
export const getCouncil = (gss: string) => fetch(`/api/councils/${encodeURIComponent(gss)}`).then((r) => json<CouncilPage>(r));
export const getVote = (id: string) => fetch(`/api/votes/${encodeURIComponent(id)}`).then((r) => json<VotePage>(r));
export const getBriefing = (id: string) =>
  fetch(`/api/briefings/${encodeURIComponent(id)}`).then((r) =>
    json<{ id: string; at: string; question: string; options: Record<string, unknown>; events: AskEvent[] }>(r),
  );

export async function sendReport(body: { kind: string; page: string; message: string; contact: string }) {
  return fetch("/api/report", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  }).then((r) => json<{ ok: boolean; id: number }>(r));
}

/** Ask a question: the briefing arrives as server-sent events, passed to ``onEvent`` as they come. */
export async function ask(
  body: { question: string; mode?: string; sources_only?: boolean; plan?: Record<string, unknown> | null },
  onEvent: (ev: AskEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  const r = await fetch("/api/ask", {
    method: "POST",
    headers: { "Content-Type": "application/json", Accept: "text/event-stream" },
    body: JSON.stringify(body),
    signal,
  });
  if (!r.ok || !r.body) {
    await json(r);
    return;
  }
  const reader = r.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) >= 0) {
      const chunk = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      const data = chunk
        .split("\n")
        .filter((l) => l.startsWith("data: "))
        .map((l) => l.slice(6))
        .join("\n");
      if (data) onEvent(JSON.parse(data) as AskEvent);
    }
  }
}
