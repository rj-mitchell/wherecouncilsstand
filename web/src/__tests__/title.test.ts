import { describe, expect, it } from "vitest";
import { briefingTitle, setTitle } from "../format";

describe("a briefing's title", () => {
  it("is made by the site from the date, never from the reader's question", () => {
    expect(briefingTitle("2026-11-18T21:12:19+00:00")).toBe("Briefing from council minutes, 18 November 2026");
    expect(briefingTitle(null)).toBe("Briefing from council minutes");
    setTitle(briefingTitle("2026-11-18"));
    expect(document.title).toBe("Briefing from council minutes, 18 November 2026 | Where Councils Stand");
  });
});
