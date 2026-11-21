/** The MPs whose seats overlap a council, on Where MPs Stand (decision 31): named under that site's name and the
 * family kit's own spine, each linking to the MP's page there, and a seat with no MP listed is named but not linked. */
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import shelf from "../../public/family/shelf.html?raw";
import { kitSpine } from "../components/Sister";

const COUNCIL = {
  gss: "E10000016", name: "Kent County Council", nation: "england", type: "county", type_name: "County council",
  region: "E12000008", region_name: "South East", site: null, status: "none", loaded: false, coverage: "not_yet",
  reasons: ["It doesn’t publish its minutes through a system we can read yet."], control_timeline: [], seats: null,
  by_year: [], votes: [], recent: [], landlords: null,
  mps: {
    site: "Where MPs Stand", url: "https://wherempsstand.com", fetched: "2026-11-21",
    seats: [
      { code: "E14001071", name: "Ashford", mp: { name: "Sojan Joseph", party: "Labour", url: "https://wherempsstand.com/people/5166/sojan-joseph" } },
      { code: "E14001172", name: "Canterbury", mp: null },
    ],
  },
};

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("fetch", vi.fn((url: string) =>
    Promise.resolve(new Response(JSON.stringify(url.startsWith("/api/statements") ? { statements: [] } : COUNCIL),
      { status: 200, headers: { "Content-Type": "application/json" } }))));
  document.body.innerHTML = '<div id="app"></div>';
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("a council's MPs", () => {
  it("uses the kit's own drawing of Where MPs Stand's spine", () => {
    const spine = kitSpine("mps");
    expect(shelf).toContain(spine);
    expect(spine).toMatch(/^<svg class="wts-spine wts-cloth--mps"/);
    expect(spine).toContain('fill="#1D4535"');
  });

  it("lists each seat's MP with a link to their page, under the sister site's name and spine", async () => {
    await act(async () => {
      await import("../council");
    });
    await act(async () => {
      await new Promise((r) => setTimeout(r, 0));
    });
    const section = document.querySelector("section.seats")!;
    expect(section.querySelector("h2")!.textContent).toBe("MPs whose seats overlap this council");
    expect(section.textContent).toContain("On Where MPs Stand");
    expect(section.querySelector(".spine svg.wts-spine.wts-cloth--mps")).not.toBeNull();
    expect(section.querySelector(".spine")!.getAttribute("aria-hidden")).toBe("true");
    const items = [...section.querySelectorAll("li")].map((li) => li.textContent);
    expect(items).toEqual(["Sojan Joseph, Labour, MP for Ashford", "Canterbury: no MP listed on Where MPs Stand"]);
    const links = [...section.querySelectorAll("a")];
    expect(links.map((a) => a.getAttribute("href"))).toEqual(["https://wherempsstand.com/people/5166/sojan-joseph"]);
  });
});
