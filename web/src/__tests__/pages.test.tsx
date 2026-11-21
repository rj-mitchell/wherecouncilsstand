/** The pages the server writes their text into keep that text when the record can't be fetched: Google's renderer
 * obeys robots.txt for the fetches a page makes, and the charity's crawler check found the list of councils, a
 * council's page and a vote's page replacing their text with "Failed to fetch" (decision 30). */
import { act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const SERVED = '<div id="app"><h1>From the server</h1><p>The record, as the server wrote it.</p></div>';

beforeEach(() => {
  vi.resetModules();
  vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("Failed to fetch"))));
  document.body.innerHTML = SERVED;
});

afterEach(() => {
  vi.unstubAllGlobals();
  document.body.innerHTML = "";
});

describe("a page whose record can't be fetched", () => {
  for (const page of ["councils", "council", "vote"]) {
    it(`keeps the server's text: ${page}`, async () => {
      await act(async () => {
        await import(`../${page}.tsx`);
      });
      await act(async () => {
        await new Promise((r) => setTimeout(r, 0));
      });
      expect(fetch).toHaveBeenCalled();
      expect(document.getElementById("app")!.innerHTML).toBe(SERVED.slice('<div id="app">'.length, -"</div>".length));
      expect(document.body.textContent).not.toMatch(/Failed to fetch|couldn’t be loaded/);
    });
  }
});
