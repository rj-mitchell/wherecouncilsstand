import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AskSister, SisterLinks } from "../components/Sister";

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

describe("AskSister", () => {
  it("hands the question to Where MPs Stand in its ?q= parameter", () => {
    const { container } = render(<AskSister site="mps" question="What has been decided about bins & recycling?" />);
    const a = container.querySelector("a")!;
    expect(a.textContent).toBe("Ask Where MPs Stand the same question");
    expect(a.getAttribute("href")).toBe("https://wherempsstand.com/?q=What%20has%20been%20decided%20about%20bins%20%26%20recycling%3F");
    expect(container.querySelector("svg.wts-cloth--mps")).not.toBeNull();
  });
});
