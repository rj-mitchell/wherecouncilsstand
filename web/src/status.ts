/** The status page: the shared page script, and the live figures from /api/status. */
import "./static";
import { longDate, number } from "./format";

export interface Status {
  councils: number;
  loaded: number;
  authorities?: number;
  authorities_loaded?: number;
  meetings: number;
  named_votes: number;
  start: string;
  latest_meeting: string | null;
  last_update: {
    finished: string | null;
    councils: number | null;
    changed: number | null;
    new_meetings: number | null;
    failed: number;
    ok: boolean;
  } | null;
  briefings: "available" | "paused" | "unavailable";
  briefings_note: string | null;
}

const BRIEFINGS: Record<Status["briefings"], string> = {
  available: "Available",
  paused: "Paused",
  unavailable: "Unavailable (sources only)",
};

/** The rows of the status list, as [term, value, state]. */
export function statusRows(s: Status): [string, string, string?][] {
  const rows: [string, string, string?][] = [
    ["Briefings", BRIEFINGS[s.briefings] + (s.briefings_note ? `. ${s.briefings_note}` : ""), s.briefings],
    ["Search, council and vote pages", "Available", "available"],
    ["Councils covered", `${number(s.loaded)} of ${number(s.councils)}`],
    ...(s.authorities
      ? ([["Strategic authorities covered", `${number(s.authorities_loaded)} of ${number(s.authorities)}`]] as [string, string][])
      : []),
    ["Meetings", `${number(s.meetings)} since ${longDate(s.start)}`],
    ["Named votes", number(s.named_votes)],
    ["Most recent meeting", s.latest_meeting ? longDate(s.latest_meeting) : "None loaded yet"],
  ];
  const u = s.last_update;
  if (u?.finished) {
    const time = u.finished.slice(11, 16);
    const what = u.ok
      ? `completed${u.new_meetings ? `, ${number(u.new_meetings)} new meeting${u.new_meetings === 1 ? "" : "s"}` : ""}`
      : `needs attention: ${number(u.failed)} council${u.failed === 1 ? "" : "s"} could not be read`;
    rows.push(["Last update", `${longDate(u.finished)}${time ? ` at ${time} UTC` : ""} (${what})`, u.ok ? "available" : "paused"]);
  } else {
    rows.push(["Last update", "None recorded yet"]);
  }
  return rows;
}

async function showStatus(el: HTMLElement) {
  try {
    const resp = await fetch("/api/status");
    if (!resp.ok) throw new Error(String(resp.status));
    const dl = document.createElement("dl");
    dl.className = "status-list";
    for (const [term, value, state] of statusRows((await resp.json()) as Status)) {
      const dt = document.createElement("dt");
      dt.textContent = term;
      const dd = document.createElement("dd");
      dd.textContent = value;
      if (state) dd.dataset.state = state;
      dl.append(dt, dd);
    }
    el.replaceChildren(dl);
  } catch {
    const p = document.createElement("p");
    p.className = "notice";
    p.textContent = "The service isn't answering just now, so its status can't be shown. Please try again in a few minutes.";
    el.replaceChildren(p);
  }
}

const live = document.getElementById("status-live");
if (live) void showStatus(live);
