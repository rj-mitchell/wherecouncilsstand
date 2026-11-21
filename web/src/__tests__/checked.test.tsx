/** A checked briefing as the server shows it (fixtures/shown-briefing.json, which tests/test_checked_briefings.py
 * checks is exactly what /api/briefings/<id> sends): the display rule's quotation is never marked as having no
 * source, the strip's counts are wts-core's check_counts, and every mark has its words. */
import { fireEvent, render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Answer, SourceCard } from "../api";
import { checkCounts, chipLabel, foundWords, planChips, quotedFrom, highlights } from "../checked";
import { BriefingText, CheckDetails, CheckStrip, Slip } from "../components/Briefing";
import { Stages } from "../components/Wait";
import shown from "./fixtures/shown-briefing.json";

const answer = shown.answer as Answer;
const sources = shown.sources as SourceCard[];

function drawn() {
  return render(<BriefingText segments={answer.segments} sources={sources} />).container;
}

describe("the display rule, through the renderer", () => {
  it("never marks a quotation found word for word as having no source", () => {
    const c = drawn();
    for (const mark of c.querySelectorAll(".wts-nosource")) {
      expect(mark.querySelector(".wts-quote--checked")).toBeNull();
      expect(mark.textContent).not.toMatch(/“that weekly bin collections be restored”/);
    }
    const beside = [...c.querySelectorAll(".wts-quote--checked")].find((q) => q.textContent!.includes("weekly bin collections"))!;
    expect(beside).toBeTruthy();
    expect(beside.closest(".wts-nosource")).toBeNull();
    // the words before it keep their mark, and its chip follows the date the citation sat on
    const before = c.querySelector("#nosource-0")!;
    expect(before.textContent).toMatch(/^At Barnsley, the minutes record a motion/);
    const chip = c.querySelector('button.wts-chip[data-source="2"]')!;
    expect(chip.textContent).toBe("Source 2Barnsley Metropolitan Borough Council, full council, 26 February 2025");
  });

  it("gives the strip check_counts' numbers", () => {
    expect(checkCounts(answer)).toEqual(shown.counts);
    const strip = render(<CheckStrip answer={answer} />).container;
    expect([...strip.querySelectorAll(".wts-check__num")].map((n) => Number(n.textContent))).toEqual([
      shown.counts.citations_matched, shown.counts.quotes_found, shown.counts.no_source]);
    expect(strip.querySelector("h2")!.textContent).toBe("Checked against the council minutes");
    expect(strip.textContent).toContain(`${shown.counts.citations_matched}of ${shown.counts.citations_total}To checkcitations matched to the record`);
  });
});

describe("the check strip", () => {
  it("shows each count with a point to check in words and links to the first one, which is on the page", () => {
    const strip = render(<CheckStrip answer={answer} />).container;
    const items = [...strip.querySelectorAll(".wts-check__item")];
    expect(items.map((i) => i.querySelector(".wts-check__glyph")!.textContent)).toEqual(["!", "!", "!"]);
    expect(items.map((i) => i.querySelector(".wts-check__badge")?.textContent)).toEqual(["To check", "To check", "To check"]);
    const text = drawn();
    for (const a of strip.querySelectorAll<HTMLAnchorElement>(".wts-check__first")) {
      expect(a.textContent).toBe("Show the first");
      expect(text.querySelector(a.getAttribute("href")!)).not.toBeNull();
    }
    expect(strip.querySelector(".wts-check__more")!.getAttribute("href")).toBe("#check-details");
  });

  it("while the results run up, hides the moving numbers from screen readers and counts the sentences last", () => {
    const strip = render(<CheckStrip answer={answer} running={{ citations: 1, quotes: 0 }} />).container;
    expect(strip.querySelector("ul")!.getAttribute("aria-hidden")).toBe("true");
    expect([...strip.querySelectorAll(".wts-check__num")].map((n) => n.textContent)).toEqual(["1", "0"]);
    expect(strip.textContent).toContain("sentences without a source: counted last");
    expect(strip.querySelector(".wts-check__badge")).toBeNull();
  });

  it("shows ticks when everything passed", () => {
    const clean: Answer = { segments: [{ text: "Barnsley agreed.", sources: [1], status: "cited" }], citations_total: 1,
      citations_invalid: 0, quotes_total: 0, quotes_unverified: 0 };
    const strip = render(<CheckStrip answer={clean} />).container;
    expect([...strip.querySelectorAll(".wts-check__glyph")].map((g) => g.textContent)).toEqual(["✓", "✓", "✓"]);
    expect(strip.textContent).toContain("1of 1citation matched to the record");
  });
});

describe("every mark has its words", () => {
  it("for quotations, text with no source and chips", () => {
    const c = drawn();
    for (const q of c.querySelectorAll(".wts-quote--checked")) {
      expect(q.querySelector(".wts-vh")!.textContent).toMatch(/^ \(quotation, found word for word in the minutes of source \d+\)$/);
    }
    const missing = c.querySelector(".wts-quote--missing")!;
    expect(missing.querySelector(".wts-quote__tick")!.textContent).toBe("Not found word for word");
    expect(missing.querySelector(".wts-vh")!.textContent).toMatch(/not found word for word in the minutes cited for it/);
    const marks = [...c.querySelectorAll(".wts-nosource")];
    expect(marks).toHaveLength(shown.counts.no_source);
    expect(marks.map((m) => m.querySelector(".wts-vh")!.textContent)).toEqual([
      " (no source)", " (no source)", " (its citation did not match the minutes and was removed)"]);
    // "No source" in words on the first, as the kit has it
    expect(marks.map((m) => !!m.querySelector(".wts-nosource__tag"))).toEqual([true, false, false]);
    for (const chip of c.querySelectorAll("button.wts-chip")) {
      expect(chip.hasAttribute("aria-label")).toBe(false);
      expect(chip.querySelector("[aria-hidden]")).toBeNull();
    }
  });

  it("in the check details, which keep the verifier's own counts", () => {
    const c = render(<CheckDetails answer={answer} found={sources.length} />).container;
    expect(c.querySelector("h2")!.textContent).toBe("How this briefing was checked");
    expect(c.textContent).toContain("Each of the 4 citations was checked against the minutes it cites: 1 did not match");
    expect(c.textContent).toContain("Each of the 3 quotations was looked for word for word in the minutes cited for it: 1 could not be found");
    expect(c.textContent).toContain(`${answer.unsupported_segments} sentences that no cited source supports`);
    expect(c.textContent).toContain("A quotation found word for word in the minutes cited straight after it is shown");
  });
});

describe("the record's slip", () => {
  it("is a page of minutes with the quoted words highlighted, the chosen ones outlined", () => {
    const q = quotedFrom(answer);
    const s = sources.find((x) => x.n === 1)!;
    const c = render(<Slip source={s} quoted={q[1]} nowSeg={q[1][0].seg} passageId="p" />).container;
    expect(c.querySelector(".wts-slip__top")!.textContent).toBe("Guildford Borough CouncilFull Council, 5 March 2025");
    expect(c.querySelector(".wts-slip__heading")!.textContent).toBe("Item 20: Waste and Recycling Strategy");
    expect(c.querySelector(".wts-slip__who strong")!.textContent).toBe("Councillor Julia McShane");
    expect(c.querySelector("mark.wts-now")!.textContent).toBe(
      "the waste and recycling strategy, including fortnightly bin collections");
    expect(c.querySelector(".wts-passage")!.getAttribute("aria-label")).toBe("The passage from source 1");
    expect(c.querySelector(".wts-slip__found")!.textContent).toBe("✓ Highlighted words found word for word");
    expect(c.querySelector("a")!.textContent).toBe("The minutes on Guildford Borough Council’s website");
    // the quotation not found is not highlighted in the record
    expect(highlights(s.text, q[1], null).length).toBe(1);
  });
});

describe("the wait's words", () => {
  it("reads the plan as large chips from its own filters", () => {
    expect(planChips({ question: "q", search_text: "q", filters: { nations: ["wales"], date_from: "2022-05-01" } })).toEqual(
      ["Councils in Wales", "since May 2022", "all parties", "full council and cabinet"]);
    expect(planChips({ question: "q", search_text: "q", filters: { control: ["LAB"], kinds: ["cabinet"] } })).toEqual(
      ["Councils across the UK", "since May 2018", "Under Labour control", "cabinet"]);
  });

  it("counts the records as they arrive, then sums them up from the search's own figures", () => {
    expect(foundWords({ records: 24, councils: 11, meetings: 18, kinds: { council: 15, cabinet: 9 } }, 5, 24)).toEqual(
      { n: 5, words: " records found so far" });
    expect(foundWords({ records: 24, councils: 11, meetings: 18, kinds: { council: 15, cabinet: 9 } }, 24, 24).words).toBe(
      " records from 11 councils at 18 meetings: 15 from full council and 9 from cabinet");
  });

  it("names the stage it is at in words, and has two stages for sources only", () => {
    const c = render(<Stages stage={1} sourcesOnly={false} />).container;
    expect([...c.querySelectorAll(".wts-stage")].map((s) => s.textContent)).toEqual([
      "✓ DoneReading the question", "NowSearching the record", "NextWriting from these records only",
      "NextChecking every citation and quotation"]);
    expect(render(<Stages stage={2} sourcesOnly />).container.querySelectorAll(".wts-stage")).toHaveLength(2);
  });

  it("chips name the council, the meeting and the date", () => {
    expect(chipLabel(sources[0])).toBe("Guildford Borough Council, full council, 5 March 2025");
  });
});

describe("waiting while the checks' results run up", () => {
  it("shows the text at once, its quotations taking their highlight in turn", () => {
    const c = render(<BriefingText segments={answer.segments} sources={sources} checking={{ upTo: 1, flash: 1 }} />).container;
    const quotes = [...c.querySelectorAll(".wts-quote")];
    expect(quotes.map((q) => q.className)).toEqual([
      "wts-quote wts-quote--checked is-flash", "wts-quote", "wts-quote wts-quote--missing"]);
    expect(c.textContent).toContain("Every council in the region did the same.");
    fireEvent.click(c.querySelector("button.wts-chip")!); // a chip is a real button while it waits
  });
});
