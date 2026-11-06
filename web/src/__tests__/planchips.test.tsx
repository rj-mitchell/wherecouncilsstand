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
