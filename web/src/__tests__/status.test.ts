import { describe, expect, it } from "vitest";
import { statusRows, type Status } from "../status";

const base: Status = {
  councils: 383,
  loaded: 295,
  meetings: 43281,
  named_votes: 8944,
  start: "2018-05-01",
  latest_meeting: "2026-11-05",
  last_update: { finished: "2026-11-06T04:38:22", councils: 295, changed: 40, new_meetings: 12, failed: 2, ok: true },
  briefings: "available",
  briefings_note: null,
};

describe("statusRows", () => {
  it("says what is covered and when it was last brought up to date", () => {
    const rows = Object.fromEntries(statusRows(base).map(([t, v]) => [t, v]));
    expect(rows["Councils covered"]).toBe("295 of 383");
    expect(rows["Meetings"]).toBe("43,281 since 1 May 2018");
    expect(rows["Most recent meeting"]).toBe("5 November 2026");
    expect(rows["Last update"]).toBe("6 November 2026 at 04:38 UTC (completed, 12 new meetings)");
    expect(rows["Briefings"]).toBe("Available");
  });

  it("says when briefings are paused, and why, and when an update needs attention", () => {
    const rows = statusRows({
      ...base,
      briefings: "paused",
      briefings_note: "The site has reached today's limit on new briefings, which keeps its costs down.",
      last_update: { ...base.last_update!, ok: false, failed: 40 },
    });
    const byTerm = Object.fromEntries(rows.map(([t, v, s]) => [t, [v, s]]));
    expect(byTerm["Briefings"]).toEqual(["Paused. The site has reached today's limit on new briefings, which keeps its costs down.", "paused"]);
    expect(byTerm["Last update"][0]).toMatch(/needs attention: 40 councils could not be read/);
    expect(statusRows({ ...base, last_update: null }).at(-1)).toEqual(["Last update", "None recorded yet"]);
  });
});

describe("statusRows with strategic authorities", () => {
  it("counts them apart from councils", () => {
    const rows = Object.fromEntries(statusRows({ ...base, authorities: 20, authorities_loaded: 13 }).map(([t, v]) => [t, v]));
    expect(rows["Councils covered"]).toBe("295 of 383");
    expect(rows["Strategic authorities covered"]).toBe("13 of 20");
  });
});
