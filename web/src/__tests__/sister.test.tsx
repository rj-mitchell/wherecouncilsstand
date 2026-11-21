import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Answer } from "../api";
import { AskSister, SisterLinks, writtenBriefing } from "../components/Sister";

describe("SisterLinks", () => {
  it("names the sister site and shows its spine, so the reader knows they are leaving", () => {
    const { container } = render(
      <SisterLinks site="landlords">
        <a href="https://wherelandlordsstand.com/areas/barnsley/">Landlords in Barnsley</a>
      </SisterLinks>,
    );
    const aside = container.querySelector("aside")!;
    expect(aside.getAttribute("aria-label")).toBe("On Where Landlords Stand");
    expect(aside.textContent).toContain("On Where Landlords Stand");
    const spine = aside.querySelector("svg.wts-spine.wts-cloth--landlords")!;
    expect(spine.getAttribute("aria-hidden")).toBe("true");
    expect(spine.querySelector("rect")!.getAttribute("fill")).toBe("#40484D");
  });
});

describe("AskSister", () => {
  it("hands the question to Where MPs Stand in its ?q= parameter", () => {
    const { container } = render(<AskSister site="mps" question="What has been decided about bins & recycling?" />);
    const a = container.querySelector("a")!;
    expect(a.textContent).toBe("Ask Where MPs Stand the same question");
    expect(a.getAttribute("href")).toBe("https://wherempsstand.com/?q=What%20has%20been%20decided%20about%20bins%20%26%20recycling%3F");
    expect(container.querySelector("svg.wts-cloth--mps")).not.toBeNull();
  });
});

describe("writtenBriefing", () => {
  const written: Answer = { segments: [{ text: "The minutes record that the council agreed.", sources: [1], status: "supported" }],
    citations_total: 1, citations_invalid: 0 };
  const noRecords: Answer = { segments: [{ text: "No records found.", sources: [], status: "connective" }], no_records: true,
    citations_total: 0, citations_invalid: 0 };
  const done = { phase: "done", question: "What have councils decided about libraries?", error: null };

  it("offers the same question on the sister site only under a written briefing", () => {
    expect(writtenBriefing({ ...done, answer: written })).toBe(true);
    expect(writtenBriefing({ ...done, answer: noRecords })).toBe(false);              // "No records found"
    expect(writtenBriefing({ ...done, answer: null })).toBe(false);                   // sources only, or over a limit
    expect(writtenBriefing({ ...done, phase: "error", answer: null, error: "The briefing could not be written." })).toBe(false);
    expect(writtenBriefing({ ...done, phase: "writing", answer: null })).toBe(false); // still being written
  });
});
