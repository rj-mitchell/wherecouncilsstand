import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Why } from "../components/Why";
import about from "../../about.html?raw";
import methodology from "../../methodology.html?raw";
import partial from "../../partials/why.html?raw";

const LEADS = ["Only the record.", "Every point linked and checked.", "Up to date.", "It says when there is nothing.",
  "Balanced by design."];
const CLOSING = "Briefings here are written by AI too. The difference is what the AI is given and how it is checked.";

describe("Why", () => {
  it("shows one line, and a real disclosure that is closed until the reader opens it", () => {
    const { container } = render(<Why />);
    expect(container.querySelector(".why > p")!.textContent)
      .toBe("Answers only from the official record, every point linked and checked.");
    const details = container.querySelector("details")!;
    expect(details.hasAttribute("open")).toBe(false);
    expect(details.querySelector("summary")!.textContent).toBe("Why use this rather than a chatbot?");
  });

  it("opens to the family's five points, in order, and says briefings are written by AI too", () => {
    const { container } = render(<Why />);
    const points = [...container.querySelectorAll("details li strong")].map((x) => x.textContent);
    expect(points).toEqual(LEADS);
    const closing = container.querySelector("details > p")!;
    expect(closing.textContent).toContain(CLOSING);
    const link = closing.querySelector("a")!;
    expect(link.textContent).toBe("How it works");
    expect(link.getAttribute("href")).toBe("/methodology#why");
  });
});

describe("the longer section on the About and How it works pages", () => {
  it("has the same points in the same order, and two more", () => {
    const leads = [...partial.matchAll(/<p><strong>([^<]+)<\/strong>/g)].map((m) => m[1]);
    expect(leads).toEqual([...LEADS, "Records searched in full.", "Open."]);
    expect(partial).toContain('<h2 class="minute-heading" id="why">Why use this rather than a chatbot?</h2>');
  });

  it("is on both pages, ending with the same closing line as the home page", () => {
    for (const page of [about, methodology]) expect(page).toContain(`<!--#include why-->\n        <p>${CLOSING}`);
  });
});
