import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { BriefingText } from "../components/Briefing";

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
});
