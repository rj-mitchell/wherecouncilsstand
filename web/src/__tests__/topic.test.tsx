/** A topic's page (decision 35): the server writes the briefing in the family's markup (src/councils/api/checked.py),
 * and this page's script only adds the record beside it or the sheet. The server's copy must draw what the app draws:
 * fixtures/shown-briefing.html is the server's markup for the renderer's own test answer (tests/test_topics.py writes
 * and checks it), and here the app draws the same answer and the two are compared, element by element. Then the
 * script on a page the server wrote: the record opens beside the briefing on a wide screen, and a chip opens the sheet
 * on a phone. */
import { act, fireEvent } from "@testing-library/react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Answer, SourceCard } from "../api";
import { BriefingText, CheckDetails, CheckStrip } from "../components/Briefing";
import server from "./fixtures/shown-briefing.html?raw";
import shown from "./fixtures/shown-briefing.json";

const answer = shown.answer as Answer;
const sources = shown.sources as SourceCard[];

/** Markup as the browser reads it, so that the two are compared as documents rather than as strings (an
 * apostrophe the server escapes, the order React and the server write nothing differently in). */
function normal(html: string): string {
  const box = document.createElement("div");
  box.innerHTML = html;
  return box.innerHTML;
}

async function drawnByTheApp(): Promise<string> {
  const box = document.createElement("div");
  const root = createRoot(box);
  await act(async () => {
    root.render(
      <>
        <CheckStrip answer={answer} />
        <BriefingText segments={answer.segments} sources={sources} />
        <CheckDetails answer={answer} found={sources.length} />
      </>,
    );
  });
  const html = box.innerHTML;
  root.unmount();
  return html;
}

describe("the server's copy of a checked briefing", () => {
  it("is the app's, element for element", async () => {
    expect(normal(server.trim())).toBe(normal(await drawnByTheApp()));
  });
});

function page(wide: boolean) {
  vi.stubGlobal("matchMedia", (q: string) => ({
    matches: q.includes("min-width: 64rem") ? wide : q.includes("hover") ? true : false,
    addEventListener() {},
    removeEventListener() {},
  }));
  document.body.innerHTML = `<main><div id="app"><article class="briefing briefing--checked wts-cloth--councils">
    <div class="result-grid" id="topic-grid"><div class="result-main"><div class="briefing-text" id="topic-text">
    </div></div></div></article><script type="application/json" id="topic-data"></script></div></main>`;
  document.getElementById("topic-text")!.innerHTML = server.slice(server.indexOf('<div class="answer">'),
    server.indexOf('<section class="check-details"'));
  document.getElementById("topic-data")!.textContent = JSON.stringify({ answer, sources });
}

describe("the topic page's script", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
  });

  it("opens the record beside the briefing on a wide screen, on the first chip's source", async () => {
    page(true);
    const { start } = await import("../topic");
    await act(async () => start());
    const grid = document.getElementById("topic-grid")!;
    expect(grid.classList.contains("has-record")).toBe(true);
    const panel = grid.querySelector("aside.record-col #record-panel")!;
    expect(panel.querySelector(".wts-record__title")!.textContent).toBe("The record Source 2, 2 of 2");
    expect(panel.querySelector(".wts-slip__top")!.textContent).toMatch(/^Barnsley Metropolitan Borough Council/);
    expect(grid.querySelector("svg.wts-connector")!.getAttribute("aria-hidden")).toBe("true");
    // choosing another chip shows its source
    const guildford = document.querySelector<HTMLElement>('.wts-chip[data-source="1"]')!;
    await act(async () => fireEvent.click(guildford));
    expect(panel.querySelector(".wts-slip__top")!.textContent).toMatch(/^Guildford Borough Council/);
    expect(guildford.getAttribute("aria-current")).toBe("true");
  });

  it("opens a sheet from a chip on a phone, with no record beside the briefing", async () => {
    page(false);
    const { start } = await import("../topic");
    await act(async () => start());
    const grid = document.getElementById("topic-grid")!;
    expect(grid.classList.contains("has-record")).toBe(false);
    expect(grid.querySelector("#record-panel")).toBeNull();
    await act(async () => fireEvent.click(document.querySelector<HTMLElement>('.wts-chip[data-source="1"]')!));
    const sheet = document.getElementById("sheet")!;
    expect(sheet.getAttribute("role")).toBe("dialog");
    expect(document.activeElement?.id).toBe("sheet-head");
    expect(sheet.querySelector(".wts-slip__top")!.textContent).toMatch(/^Guildford Borough Council/);
  });
});
