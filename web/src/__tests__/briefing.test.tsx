import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Answer } from "../api";
import { BriefingText, CheckNotices, MISQUOTE_TITLE } from "../components/Briefing";

describe("BriefingText", () => {
  it("sets headings, the In brief box, bullets, citations and unsupported text without injecting HTML", () => {
    const { container } = render(
      <BriefingText
        segments={[
          { text: "**In brief**\n\n- Councils closed toilets, as when Rother did", sources: [], status: "connective" },
          { text: " in June 2025", sources: [5], status: "cited" },
          { text: ".\n\n**Councils under no overall control**\n\nA claim with no source.", sources: [], status: "unsupported" },
          { text: "\n\n<img src=x onerror=alert(1)> is shown as text", sources: [2], status: "cited" },
        ]}
      />,
    );
    const brief = container.querySelector(".resolved");
    expect(brief?.querySelector("h2")?.textContent).toBe("In brief");
    expect(brief?.querySelectorAll("li")).toHaveLength(1);
    expect(container.querySelector('a.cite[href="#source-5"]')?.textContent).toBe("[5]");
    expect([...container.querySelectorAll("h2")].map((h) => h.textContent)).toEqual(["In brief", "Councils under no overall control"]);
    const unsupported = [...container.querySelectorAll(".unsupported")].map((e) => e.textContent);
    expect(unsupported).toContain("A claim with no source.");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)> is shown as text");
  });

  it("renders streaming text before the answer is checked", () => {
    const { container } = render(<BriefingText text={"**In brief**\n\n- First finding"} />);
    expect(container.querySelector(".resolved li")?.textContent).toBe("First finding");
  });

  it("marks text whose citations all failed the check as it marks text with no source", () => {
    const { container } = render(
      <BriefingText
        segments={[
          { text: "Rother closed two toilets", sources: [1], status: "cited" },
          { text: ". Every council in Sussex did the same.", sources: [], status: "invalid" },
        ]}
      />,
    );
    const marked = container.querySelector(".unsupported");
    expect(marked?.textContent).toBe(". Every council in Sussex did the same.");
    expect(marked?.getAttribute("title")).toBe("Not supported by a cited source");
    expect(container.querySelectorAll("a.cite")).toHaveLength(1);
  });

  it("marks a quotation not found word for word, and says so to a screen reader", () => {
    const text = 'The minutes record that the leader said "we will close every toilet" in June.';
    const start = text.indexOf('"');
    const end = text.lastIndexOf('"') + 1;
    const { container } = render(
      <BriefingText
        segments={[{ text, sources: [3], status: "cited", misquotes: [{ start, end, text: "we will close every toilet" }] }]}
      />,
    );
    const quote = container.querySelector(".misquote");
    expect(quote?.getAttribute("title")).toBe(MISQUOTE_TITLE);
    expect(quote?.querySelector(".visually-hidden")?.textContent).toBe(
      " (quotation not found word for word in the minutes cited for it)",
    );
    expect(quote?.textContent?.startsWith('"we will close every toilet"')).toBe(true);
    expect(container.querySelector("p")?.textContent).toMatch(/^The minutes record that the leader said "we will close/);
    expect(container.querySelector("p")?.textContent).toMatch(/cited for it\) in June\.\[3\]$/);
  });

  it("keeps a marked quotation in place across bold, a bullet and a line break, and explains it once", () => {
    // a bullet's marker is taken off the line, and bold is set: the marks follow the text, not the characters
    const first = '**In brief**\n\n- The cabinet was told "this budget is **balanced** and';
    const second = ' fair" by the leader.';
    const { container } = render(
      <BriefingText
        segments={[
          { text: first, sources: [], status: "connective", misquotes: [{ start: first.indexOf('"'), end: first.length, text: "q" }] },
          { text: second, sources: [2], status: "cited", misquotes: [{ start: 0, end: 6, text: "q" }] },
        ]}
      />,
    );
    const parts = [...container.querySelectorAll(".misquote")].map((e) => e.textContent?.replace(/ \(quotation.*\)$/, ""));
    expect(parts.join("")).toBe('"this budget is balanced and fair"');
    expect(container.querySelector("li strong .misquote")?.textContent).toBe("balanced");
    expect(container.querySelectorAll(".misquote .visually-hidden")).toHaveLength(1);
    expect(container.querySelector("li")?.textContent).toBe(
      'The cabinet was told "this budget is balanced and fair" (quotation not found word for word in the minutes cited for it) by the leader.[2]',
    );
  });
});

const answer: Answer = { segments: [], citations_total: 2, citations_invalid: 0, unsupported_segments: 0, quotes_unverified: 0 };

describe("CheckNotices", () => {
  it("says nothing when every point passed", () => {
    const { container } = render(<CheckNotices answer={answer} />);
    expect(container.textContent).toBe("");
  });

  it("explains marked text when its only failing is a citation that was removed", () => {
    render(
      <CheckNotices
        answer={{ ...answer, citations_invalid: 1, segments: [{ text: "A claim.", sources: [], status: "invalid" }] }}
      />,
    );
    expect(screen.getByText(/isn’t supported by a cited source/)).toBeTruthy();
    expect(screen.getByText(/One passage gave a source, but its citation failed the check against the minutes/)).toBeTruthy();
  });

  it("explains marked quotations", () => {
    const { container } = render(<CheckNotices answer={{ ...answer, quotes_unverified: 2 }} />);
    expect(container.textContent).toBe(
      "2 quotations marked like this were not found word for word in the minutes cited for them. Check the minutes before relying on them.",
    );
    expect(container.querySelector(".notice .misquote")).not.toBeNull();
  });
});

