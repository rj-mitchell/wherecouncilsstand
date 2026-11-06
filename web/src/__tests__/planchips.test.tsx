import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { Plan } from "../api";
import { PlanChips } from "../components/PlanChips";

const plan = (nations: string[]): Plan => ({ question: "q", search_text: "q", filters: { nations } });

describe("PlanChips", () => {
  it("names each of the four nations as the question was read", () => {
    const { container } = render(
      <PlanChips plan={plan(["england", "wales", "scotland", "northern_ireland"])} meta={null} councilNames={{}} />,
    );
    expect([...container.querySelectorAll(".chips li")].map((li) => li.textContent)).toEqual([
      "England",
      "Wales",
      "Scotland",
      "Northern Ireland",
    ]);
  });
});

describe("PlanChips for strategic authorities", () => {
  it("labels a mayor's party as the mayor's, never as a council's control", () => {
    const p: Plan = {
      question: "q",
      search_text: "q",
      filters: { control: ["LAB", "MAYOR:LAB", "MAYOR:LD", "SA:NONE"], council_types: ["strategic_authority"], kinds: ["scrutiny"] },
    };
    const { container } = render(<PlanChips plan={p} meta={null} councilNames={{}} />);
    expect([...container.querySelectorAll(".chips li")].map((li) => li.textContent)).toEqual([
      "Councils under Labour control",
      "Strategic authorities with a Labour mayor",
      "Strategic authorities with a Liberal Democrat mayor",
      "Strategic authorities without a mayor",
      "strategic_authority",
      "Overview and scrutiny",
    ]);
  });
});
