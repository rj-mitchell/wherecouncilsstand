import { act } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { drawWhenLoaded } from "../draw";
import { byYear, shortTally, shownOutcome } from "../components/VoteLinks";

afterEach(() => {
  document.body.innerHTML = "";
});

describe("drawWhenLoaded", () => {
  it("keeps the server's text until the record has come, then draws the page once", async () => {
    document.body.innerHTML = '<div id="app"><h1>From the server</h1></div>';
    let arrive: (v: string) => void = () => {};
    const record = new Promise<string>((r) => (arrive = r));
    await act(async () => drawWhenLoaded(() => record, (v) => <h1>{v}</h1>, (m) => <p>{m}</p>, "Getting it"));
    // no "Getting it" line in the text's place: that moved the page twice (a layout shift)
    expect(document.getElementById("app")!.innerHTML).toBe("<h1>From the server</h1>");
    await act(async () => arrive("From the app"));
    expect(document.getElementById("app")!.innerHTML).toBe("<h1>From the app</h1>");
  });

  it("says it is waiting only where the server sent no text, and gives the error if the record can't be had", async () => {
    document.body.innerHTML = '<div id="app"></div>';
    let fail: (e: Error) => void = () => {};
    const record = new Promise<string>((_, r) => (fail = r));
    await act(async () => drawWhenLoaded(() => record, (v) => <h1>{v}</h1>, (m) => <p>{m}</p>, "Getting it"));
    expect(document.getElementById("app")!.textContent).toBe("Getting it");
    await act(async () => fail(new Error("There is no named vote at this address.")));
    expect(document.getElementById("app")!.textContent).toBe("There is no named vote at this address.");
  });

  it("leaves the server's text as it is if the record can't be had", async () => {
    // a search engine drawing the page may be refused the record by robots.txt (decision 30)
    document.body.innerHTML = '<div id="app"><h1>From the server</h1></div>';
    let fail: (e: Error) => void = () => {};
    const record = new Promise<string>((_, r) => (fail = r));
    await act(async () => drawWhenLoaded(() => record, (v) => <h1>{v}</h1>, (m) => <p>{m}</p>, "Getting it"));
    await act(async () => fail(new TypeError("Failed to fetch")));
    expect(document.getElementById("app")!.innerHTML).toBe("<h1>From the server</h1>");
  });
});

describe("vote links", () => {
  const v = { outcome: "carried", counts: { for: 3, against: 5, abstain: 1 }, partial: false, question: "" };
  it("leave out a result that contradicts the count, as the server does", () => {
    expect(shownOutcome(v)).toBe("");
    expect(shownOutcome({ ...v, outcome: "lost" })).toBe("lost");
    expect(shortTally({ ...v, outcome: "lost", vote_id: "x", date: "2026-02-26", kind: "council", item: "" })).toBe(
      "lost, for 3, against 5, abstained 1",
    );
  });
  it("group votes by year, newest first as they come", () => {
    expect(byYear([{ date: "2026-02-01" }, { date: "2026-01-01" }, { date: "2025-03-01" }]).map(([y, vs]) => [y, vs.length])).toEqual([
      ["2026", 2],
      ["2025", 1],
    ]);
  });
});
