import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SourceCard } from "../api";
import { BriefingText, Chip } from "../components/Briefing";

const card = (n: number, council: string, kind: string, committee: string, date: string): SourceCard => ({
  n, title: "", url: `https://example.org/${n}`, record_id: `r${n}`, date, gss: "E08000038", council_name: council,
  committee, kind, item_title: "An item", item_number: "4.", control: null, group: "", text: "The minutes.", votes: [],
});

describe("BriefingText", () => {
  it("sets headings, the In brief box, bullets, chips and text with no source without injecting HTML", () => {
    const { container } = render(
      <BriefingText
        sources={[card(5, "Rother District Council", "cabinet", "Cabinet", "2025-06-12")]}
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
    const chip = container.querySelector('button.wts-chip[data-source="5"]')!;
    expect(chip.textContent).toBe("Source 5Rother District Council, cabinet, 12 June 2025");
    expect([...container.querySelectorAll("h2")].map((h) => h.textContent)).toEqual(["In brief", "Councils under no overall control"]);
    const marked = [...container.querySelectorAll(".wts-nosource")].map((e) => e.textContent);
    expect(marked).toContain("A claim with no source.No source (no source)");
    expect(container.querySelector("img")).toBeNull();
    expect(container.textContent).toContain("<img src=x onerror=alert(1)> is shown as text");
  });

  it("renders streaming text before the answer is checked, with a cursor", () => {
    const { container } = render(<BriefingText text={"**In brief**\n\n- First finding"} cursor />);
    expect(container.querySelector(".resolved li")?.textContent).toBe("First finding");
    expect(container.querySelector(".resolved li .wts-cursor")?.getAttribute("aria-hidden")).toBe("true");
  });

  it("keeps the space after a passage with no source outside its mark, so its tag never touches the next word", () => {
    const { container } = render(
      <BriefingText
        sources={[card(1, "Rother District Council", "cabinet", "Cabinet", "2025-06-12")]}
        segments={[
          { text: "Most councils agreed. ", sources: [], status: "unsupported" },
          { text: "Rother closed two toilets", sources: [1], status: "cited" },
        ]}
      />,
    );
    const marked = container.querySelector(".wts-nosource")!;
    expect(marked.textContent).toBe("Most councils agreed.No source (no source)");
    expect(marked.nextSibling?.textContent).toBe(" ");
    expect(container.textContent).toContain("(no source) Rother closed two toilets");
  });

  it("marks text whose citations all failed the check as text with no source, and says why", () => {
    const { container } = render(
      <BriefingText
        segments={[
          { text: "Rother closed two toilets", sources: [1], status: "cited" },
          { text: ". Every council in Sussex did the same.", sources: [], status: "invalid" },
        ]}
      />,
    );
    const marked = container.querySelector(".wts-nosource")!;
    expect(marked.id).toBe("nosource-1");
    expect(marked.firstChild?.textContent).toBe(". Every council in Sussex did the same.");
    expect(marked.querySelector(".wts-nosource__tag")?.textContent).toBe("No source");
    expect(marked.querySelector(".wts-vh")?.textContent).toBe(" (its citation did not match the minutes and was removed)");
    expect(container.querySelectorAll("button.wts-chip")).toHaveLength(1);
  });

  it("marks a quotation not found word for word, in words and to a screen reader", () => {
    const text = 'The minutes record that the leader said "we will close every toilet" in June.';
    const start = text.indexOf('"');
    const end = text.lastIndexOf('"') + 1;
    const { container } = render(
      <BriefingText segments={[{ text, sources: [3], status: "cited", misquotes: [{ start, end, text: "we will close every toilet" }] }]} />,
    );
    const quote = container.querySelector(".wts-quote--missing")!;
    expect(quote.id).toBe(`misquote-0-${start}`);
    expect(quote.querySelector(".wts-quote__tick")?.textContent).toBe("Not found word for word");
    expect(quote.querySelector(".wts-vh")?.textContent).toBe(
      " (quotation not found word for word in the minutes cited for it, source 3)",
    );
    expect(container.querySelector(".wts-quote--checked")).toBeNull();
    expect(container.querySelector("p")?.textContent).toMatch(/^The minutes record that the leader said "we will close/);
  });

  it("keeps a marked quotation in place across bold, a bullet and a line break, and explains it once", () => {
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
    const parts = [...container.querySelectorAll(".wts-quote--missing")].map((e) =>
      [...e.childNodes].filter((n) => !(n instanceof HTMLElement && n.matches(".wts-vh, .wts-quote__tick"))).map((n) => n.textContent).join(""));
    expect(parts.join("")).toBe('"this budget is balanced and fair"');
    expect(container.querySelector("li .wts-quote--missing strong")?.textContent).toBe("balanced");
    expect(container.querySelectorAll(".wts-quote--missing .wts-vh")).toHaveLength(1);
  });

  it("shows a quotation found word for word in the record's own words, with its tick and its words", () => {
    const { container } = render(
      <BriefingText segments={[{ text: 'Guildford resolved "that the strategy be adopted"', sources: [4], status: "cited" }]} />,
    );
    const q = container.querySelector(".wts-quote--checked")!;
    expect(q.querySelector(".wts-quote__tick")?.textContent).toBe("✓ word for word");
    expect(q.querySelector(".wts-quote__tick")?.getAttribute("aria-hidden")).toBe("true");
    expect(q.querySelector(".wts-vh")?.textContent).toBe(" (quotation, found word for word in the minutes of source 4)");
  });

  it("shows two runs next to each other from the same source with one chip", () => {
    const { container } = render(
      <BriefingText segments={[
        { text: "Barnsley consulted", sources: [1], status: "cited" },
        { text: " ", sources: [], status: "connective" },
        { text: "and then agreed.", sources: [1], status: "cited" },
      ]} />,
    );
    expect(container.querySelectorAll("button.wts-chip")).toHaveLength(1);
  });
});

describe("Chip", () => {
  it("is named by its own words: no aria-label, nothing hidden from screen readers (WCAG 2.5.3)", () => {
    const { container } = render(
      <Chip n={3} source={card(3, "Barnsley Metropolitan Borough Council", "council", "Full Council", "2026-02-26")} />,
    );
    expect(container.innerHTML).toBe(
      '<button type="button" class="wts-chip" data-source="3" data-wts-conversion="source_opened"><span class="wts-chip__in">' +
        '<span class="wts-chip__n">' +
        '<span class="wts-vh">Source</span> 3</span><span>Barnsley Metropolitan Borough Council, full council, 26 February 2026' +
        "</span></span></button>",
    );
  });

  it("names a committee by its own name", () => {
    const { container } = render(
      <Chip n={1} source={card(1, "Glasgow City Council", "policy", "City Administration Committee", "2024-01-25")} />,
    );
    expect(container.textContent).toBe("Source 1Glasgow City Council, City Administration Committee, 25 January 2024");
  });
});
