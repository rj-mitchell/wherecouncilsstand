import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CoverageLabel } from "../components/Coverage";

describe("CoverageLabel", () => {
  it("says how much is covered in neutral words, with a neutral mark", () => {
    const { container } = render(
      <>
        <CoverageLabel c="full" />
        <CoverageLabel c="partial" />
        <CoverageLabel c="not_yet" />
      </>,
    );
    expect([...container.querySelectorAll(".coverage-status")].map((e) => e.textContent)).toEqual(["Full", "Partial", "Not yet"]);
    expect([...container.querySelectorAll(".mark")].map((e) => e.className)).toEqual([
      "mark coverage-full",
      "mark coverage-partial",
      "mark coverage-not_yet",
    ]);
    expect(container.innerHTML).not.toMatch(/\brag\b|green|amber|\bred\b|working/i);
  });
});
