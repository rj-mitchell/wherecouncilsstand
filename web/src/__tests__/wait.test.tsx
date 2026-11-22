/** The wait for a new briefing, from the stream's events (family/BRIEFINGS.md, "The wait", kit 2.3.0): once the
 * server says the checks have begun (a progress event with step "checking"), the checking line shows under the text
 * until the final event, the stage list has "Checking" as Now, the line above the text no longer says "Writing from
 * these records only", and the status region says it once. */
import { act, fireEvent } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { CHECKING } from "../components/Wait";
import shown from "./fixtures/shown-briefing.json";

let stream: ReadableStreamDefaultController<Uint8Array>;
const send = async (ev: object) => {
  await act(async () => {
    stream.enqueue(new TextEncoder().encode(`data: ${JSON.stringify(ev)}\n\n`));
    for (let i = 0; i < 5; i++) await new Promise((r) => setTimeout(r, 0));
  });
};

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("hover"),
    addEventListener() {},
    removeEventListener() {},
  }));
  vi.stubGlobal("requestAnimationFrame", (f: FrameRequestCallback) => setTimeout(() => f(0), 0));
  vi.stubGlobal("fetch", vi.fn((url: string) => {
    if (url !== "/api/ask") return Promise.reject(new TypeError("Failed to fetch"));
    const body = new ReadableStream<Uint8Array>({ start: (c) => { stream = c; } });
    return Promise.resolve(new Response(body, { status: 200, headers: { "Content-Type": "text/event-stream" } }));
  }));
  history.replaceState(null, "", "/?q=" + encodeURIComponent("What have councils decided about bin collections?"));
  document.body.innerHTML = '<main><div id="app"></div></main>';
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
  history.replaceState(null, "", "/");
});

describe("the wait", () => {
  it("shows the checking line from the server's checking event until the final event, and says it once", async () => {
    await act(async () => {
      await import("../ask");
    });
    const status = () => document.querySelector('[role="status"]')!.textContent;
    const now = () => document.querySelector('.wts-stage[data-state="now"]')?.textContent;
    await act(async () => fireEvent.keyDown(document.getElementById("question")!, { key: "Enter" }));
    await send({ type: "plan", plan: { question: "q", search_text: "bin collections", filters: {} } });
    await send({ type: "sources", sources: shown.sources, candidates: 40, semantic: true, evidence: null });
    await send({ type: "text", text: "The minutes record that councils agreed." });
    expect(document.querySelector(".wait__only")?.textContent).toMatch(/^Writing from these 2 records only/);
    expect(document.querySelector(".wts-checking")).toBeNull();
    expect(now()).toBe("NowWriting from these records only");

    await send({ type: "progress", step: "checking" });
    const line = document.querySelector(".wts-checking")!;
    expect(line.textContent).toBe(CHECKING);
    expect(CHECKING).toBe("Checking every citation and quotation against the council minutes. The briefing is finished "
      + "when this is done.");
    expect(line.querySelector(".wts-checking__bar")).not.toBeNull();
    expect(line.previousElementSibling?.classList.contains("briefing-text")).toBe(true); // under the text
    expect(document.querySelector(".wait__only")).toBeNull();
    expect(document.querySelector(".wait")!.textContent).not.toContain("Writing from these"); // the stage list says Done
    expect(now()).toBe("NowChecking every citation and quotation");
    expect(status()).toBe(CHECKING);
    expect(document.querySelector(".wts-cursor")).toBeNull(); // the text is finished

    await send({ type: "final", answer: shown.answer, briefing_id: "abc" });
    expect(document.querySelector(".wts-checking")).toBeNull();
    expect(status()).toBe(CHECKING); // not said again while the counts run up
    expect(document.getElementById("check")).not.toBeNull();
    await act(async () => stream.close());
  });
});
