import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { SourceCard } from "../api";
import { Sources } from "../components/Sources";

const card = (n: number, more: Partial<SourceCard>): SourceCard => ({
  n,
  title: "",
  url: "https://example.org/minutes",
  record_id: `E08000017:1:${n}`,
  date: "2026-03-02",
  gss: "E08000017",
  council_name: "Barchester Metropolitan Borough Council",
  committee: "Cabinet",
  kind: "cabinet",
  item_title: "Section 114 notice",
  item_number: "7.",
  control: "REF",
  group: "Councils controlled by Reform UK",
  text: "The Mayor said that the council had received a Section 114 notice.",
  votes: [],
  ...more,
});

describe("Sources", () => {
  it("gives each passage's people their own party under a heading that names only the council's control", () => {
    const { container } = render(
      <Sources
        sources={[
          card(1, { named: ["Jo Smith, the directly elected mayor (Labour; not the party in control)"] }),
          card(2, { group: "Councils controlled by Labour", control: "LAB", named: [] }),
          card(3, { group: "Councils controlled by Labour", control: "LAB" }),
        ]}
      />,
    );
    expect([...container.querySelectorAll(".group-heading")].map((h) => h.textContent)).toEqual([
      "Councils controlled by Reform UK",
      "Councils controlled by Labour",
    ]);
    const named = [...container.querySelectorAll(".named")].map((p) => p.textContent);
    expect(named).toEqual([
      "People in this passage, with their party on the date: Jo Smith, the directly elected mayor (Labour; not the party in control).",
    ]);
  });
});
