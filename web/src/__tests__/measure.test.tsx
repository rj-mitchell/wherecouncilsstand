/** The family kit's conversion marks (docs/DECISIONS.md, 36; the charity's family/MEASUREMENT.md). They are on the
 * pages whether measurement is on or off, and do nothing unless the kit's measure.js is on the page (only while the
 * switch is on) and the reader has agreed: a source chip and every link to the council's own minutes (source_opened),
 * the end of a finished briefing (briefing_read, once for each briefing), and a report or statement sent
 * (report_sent, which the form tells measure.js about). */
import { act, fireEvent, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Answer, SourceCard } from "../api";
import { CheckDetails, Chip, Slip } from "../components/Briefing";
import { ReportForm } from "../components/ReportForm";
import { Sources } from "../components/Sources";

const source: SourceCard = {
  n: 1, title: "", url: "https://example.org/minutes", record_id: "r1", date: "2025-02-26", gss: "E08000038",
  council_name: "Barnsley Metropolitan Borough Council", committee: "Cabinet", kind: "cabinet", item_title: "Libraries",
  item_number: "4.", control: null, group: "", text: "The minutes.", votes: [],
};
const answer = { segments: [], citations_total: 1 } as unknown as Answer;

afterEach(() => {
  vi.unstubAllGlobals();
  delete (window as { wtsMeasure?: unknown }).wtsMeasure;
});

describe("the conversion marks", () => {
  it("mark a chip and each link to the council's own minutes as a source opened", () => {
    const chip = render(<Chip n={1} source={source} />).container;
    expect(chip.querySelector("button.wts-chip")?.getAttribute("data-wts-conversion")).toBe("source_opened");
    const slip = render(<Slip source={source} nowSeg={null} passageId="p1" />).container;
    expect(slip.querySelector('a[href="https://example.org/minutes"]')?.getAttribute("data-wts-conversion")).toBe("source_opened");
    const list = render(<Sources sources={[source]} />).container;
    expect(list.querySelector('a[href="https://example.org/minutes"]')?.getAttribute("data-wts-conversion")).toBe("source_opened");
    // a link within the site is not a source
    expect(list.querySelector('a[href="/councils/E08000038"]')?.hasAttribute("data-wts-conversion")).toBe(false);
  });

  it("mark the end of a finished briefing, once for each briefing", () => {
    const end = render(<CheckDetails answer={answer} found={1} briefing="abc123" />).container.firstElementChild!;
    expect(end.getAttribute("data-wts-conversion")).toBe("briefing_read");
    expect(end.getAttribute("data-wts-briefing")).toBe("abc123");
    const unsaved = render(<CheckDetails answer={answer} found={1} />).container.firstElementChild!;
    expect(unsaved.getAttribute("data-wts-conversion")).toBe("briefing_read");
    expect(unsaved.hasAttribute("data-wts-briefing")).toBe(false);
  });
});

describe("a report sent", () => {
  async function send(ok: boolean) {
    vi.stubGlobal("fetch", vi.fn(() => Promise.resolve(new Response(JSON.stringify(ok ? { ok: true, id: 7 } : { detail: "No." }),
      { status: ok ? 200 : 422, headers: { "Content-Type": "application/json" } }))));
    const { container } = render(<ReportForm search="" />);
    fireEvent.change(container.querySelector("#message")!, { target: { value: "The party is wrong." } });
    await act(async () => {
      fireEvent.submit(container.querySelector("form")!);
    });
    return container;
  }

  it("is told to measure.js once it has been received, and only then", async () => {
    const conversion = vi.fn(() => true);
    (window as { wtsMeasure?: unknown }).wtsMeasure = { conversion };
    expect((await send(false)).textContent).toContain("couldn’t be sent");
    expect(conversion).not.toHaveBeenCalled();
    expect((await send(true)).textContent).toContain("reference 7");
    expect(conversion).toHaveBeenCalledTimes(1);
    expect(conversion).toHaveBeenCalledWith("report_sent");
  });

  it("is sent as before while measurement is off (no measure.js on the page)", async () => {
    expect((await send(true)).textContent).toContain("reference 7");
  });
});
