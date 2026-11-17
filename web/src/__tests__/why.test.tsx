import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Why } from "../components/Why";
import about from "../../about.html?raw";
import methodology from "../../methodology.html?raw";
import partial from "../../partials/why.html?raw";

// the charity's glossary, "AI briefings": the line beside the question box, and points 1 to 5 for this site
const LINE = "Briefings are written by AI from the official record only, and every citation is checked.";
const POINTS = [
  "The AI is given only the council minutes and votes found for your question and may use nothing else.",
  "Each point links to its source. Citations are checked against the source text, quotations are checked word for word, and sentences that no source supports are flagged.",
  "Councils’ minutes are read in every day.",
  "If the record holds nothing relevant, the site says “No records found”.",
  "Evidence is drawn from across councils run by different parties.",
];

describe("Why", () => {
  it("shows one line, and a real disclosure that is closed until the reader opens it", () => {
    const { container } = render(<Why />);
    expect(container.querySelector(".why > p")!.textContent).toBe(LINE);
    const details = container.querySelector("details")!;
    expect(details.hasAttribute("open")).toBe(false);
    expect(details.querySelector("summary")!.textContent).toBe("How the briefings are checked");
  });

  it("opens to the family's five points as plain sentences, then a link to the methodology", () => {
    const { container } = render(<Why />);
    const points = [...container.querySelectorAll("details li")].map((x) => x.textContent!.replace(/\s+/g, " ").trim());
    expect(points).toEqual(POINTS);
    expect(container.querySelector("details strong")).toBeNull();
    const link = container.querySelector("details > p a")!;
    expect(link.textContent).toBe("More about the briefings");
    expect(link.getAttribute("href")).toBe("/methodology#ai-briefings");
  });
});

describe("the longer section on the About and methodology pages", () => {
  it("is headed as the glossary says, in plain paragraphs", () => {
    expect(partial).toContain('<h2 id="ai-briefings">AI briefings</h2>');
    expect(partial).toContain(">What the model is given</h3>");
    expect(partial).toContain("<h3>How it is checked</h3>");
    expect(partial).toContain("Briefings are written by AI.");
    expect(partial).not.toContain("<strong>");
  });

  it("is on both pages", () => {
    for (const page of [about, methodology]) expect(page).toContain("<!--#include why-->");
  });
});
