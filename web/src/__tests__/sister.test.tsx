import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { SisterLinks } from "../components/Sister";

describe("SisterLinks", () => {
  it("names the sister site and shows its spine, so the reader knows they are leaving", () => {
    const { container } = render(
      <SisterLinks site="landlords">
        <a href="https://wherelandlordsstand.com/areas/barnsley/">Landlords in Barnsley</a>
      </SisterLinks>,
    );
    const aside = container.querySelector("aside")!;
    expect(aside.getAttribute("aria-label")).toBe("On Where Landlords Stand");
    expect(aside.textContent).toContain("On Where Landlords Stand");
    const spine = aside.querySelector("svg.wts-spine.wts-cloth--landlords")!;
    expect(spine.getAttribute("aria-hidden")).toBe("true");
    expect(spine.querySelector("rect")!.getAttribute("fill")).toBe("#40484D");
  });
});
