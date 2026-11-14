import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { Statement } from "../api";
import { ReportForm, words } from "../components/ReportForm";
import { NOT_ENDORSED, StatementCard, safeLink } from "../components/Statements";

const STATEMENT: Statement = {
  id: 7,
  page: "/votes/E08000038:1:10:0",
  council: "E08000038",
  name: "An Example Councillor",
  role: "Councillor, a made-up council",
  text: "First paragraph.\n\nSecond paragraph.",
  link: "https://example.org/minutes",
  shown_on: "2026-11-12",
  about: "Notice of Motion, 26 February 2025",
};

describe("StatementCard", () => {
  it("is headed with its author's name and date, and says it is their own words", () => {
    const { container } = render(<StatementCard s={STATEMENT} />);
    const article = container.querySelector("article.statement")!;
    const heading = article.querySelector("h2")!;
    expect(heading.textContent).toBe("Statement from An Example Councillor, 12 November 2026");
    expect(article.getAttribute("aria-labelledby")).toBe(heading.id);
    // a search engine may show the page, but never quotes a statement as the site's own words
    expect(article.hasAttribute("data-nosnippet")).toBe(true);
    expect([...article.querySelectorAll(".statement-text p")].map((p) => p.textContent)).toEqual([
      "First paragraph.",
      "Second paragraph.",
    ]);
    expect(article.querySelector(".statement-note")!.textContent).toBe(
      "In their own words. Not checked or endorsed by Where Councils Stand.",
    );
    expect(NOT_ENDORSED).toBe("In their own words. Not checked or endorsed by Where Councils Stand.");
    const link = article.querySelector(".statement-link a")!;
    expect(link.getAttribute("href")).toBe("https://example.org/minutes");
    expect(link.getAttribute("rel")).toContain("nofollow");
    expect(article.querySelector(".statement-about")).toBeNull(); // beside its own item
  });

  it("shows a link to the record only when it is a web address", () => {
    expect(safeLink("https://example.org/minutes?id=1&x=2")).toBe("https://example.org/minutes?id=1&x=2");
    for (const bad of ["javascript:alert(1)", "data:text/html,x", "https://example.org/a b", "//example.org", "", null])
      expect(safeLink(bad)).toBeNull();
    const { container } = render(<StatementCard s={{ ...STATEMENT, link: "javascript:alert(1)" }} />);
    expect(container.querySelector(".statement-link")).toBeNull();
    expect(container.querySelector("a")).toBeNull();
    expect(container.querySelector(".statement-text")!.textContent).toContain("First paragraph.");
  });

  it("says which item it is about on a council's page, under a lower heading", () => {
    const { container } = render(<StatementCard s={STATEMENT} level={3} here="/councils/E08000038" />);
    expect(container.querySelector("h3")).not.toBeNull();
    const about = container.querySelector(".statement-about a")!;
    expect(about.getAttribute("href")).toBe("/votes/E08000038:1:10:0");
    expect(about.textContent).toBe("Notice of Motion, 26 February 2025");
  });
});

describe("ReportForm", () => {
  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it("offers the policy's three routes by their family names, and keeps the takedown request", () => {
    render(<ReportForm search="" />);
    const options = [...(screen.getByLabelText("What is it about?") as HTMLSelectElement).options];
    expect(options.map((o) => [o.value, o.textContent])).toEqual([
      ["error", "Something is wrong"],
      ["unfair", "You've been characterised unfairly"],
      ["statement", "Add a statement in your own words"],
      ["takedown", "A takedown request"],
      ["other", "Something else"],
    ]);
  });

  it("preselects the route named in ?kind=, as links such as ?kind=takedown expect", () => {
    for (const kind of ["takedown", "unfair", "error", "other"]) {
      const { unmount } = render(<ReportForm search={`?kind=${kind}`} />);
      expect((screen.getByLabelText("What is it about?") as HTMLSelectElement).value).toBe(kind);
      unmount();
    }
    render(<ReportForm search="?kind=nonsense" />);
    expect((screen.getByLabelText("What is it about?") as HTMLSelectElement).value).toBe("error");
  });

  it("shows the statement form for ?kind=statement, counts words and refuses more than 150", () => {
    render(<ReportForm search="?kind=statement&page=/votes/E08000038:1:10:0" />);
    expect((screen.getByLabelText("Address of the page it's about") as HTMLInputElement).value).toBe(
      "/votes/E08000038:1:10:0",
    );
    fireEvent.change(screen.getByLabelText("Your name, as it should be shown"), { target: { value: "A Councillor" } });
    fireEvent.change(screen.getByLabelText("Your role"), { target: { value: "Councillor" } });
    fireEvent.change(screen.getByLabelText("Your email address, to confirm it's you"), { target: { value: "a@b.gov.uk" } });
    const send = screen.getByRole("button", { name: "Send the statement" }) as HTMLButtonElement;
    const text = screen.getByLabelText("Your statement");
    fireEvent.change(text, { target: { value: Array(150).fill("word").join(" ") } });
    expect(screen.getByText("150 of 150 words")).not.toBeNull();
    expect(send.disabled).toBe(true); // not yet confirmed as acting for them
    fireEvent.click(screen.getByLabelText(/I'm the councillor or council this is about/));
    expect(send.disabled).toBe(false);
    fireEvent.change(text, { target: { value: Array(151).fill("word").join(" ") } });
    expect(screen.getByText("151 of 150 words: 1 too many")).not.toBeNull();
    expect(text.getAttribute("aria-invalid")).toBe("true");
    expect(send.disabled).toBe(true);
  });

  it("sends a statement to its own address, with every field, and thanks its author", async () => {
    const fetch = vi.fn(async () => new Response(JSON.stringify({ ok: true, id: 12 }), { status: 200 }));
    vi.stubGlobal("fetch", fetch);
    render(<ReportForm search="?kind=statement" />);
    fireEvent.change(screen.getByLabelText("Address of the page it's about"), { target: { value: "/councils/E08000038" } });
    fireEvent.change(screen.getByLabelText("Your name, as it should be shown"), { target: { value: "A Councillor" } });
    fireEvent.change(screen.getByLabelText("Your role"), { target: { value: "Councillor" } });
    fireEvent.change(screen.getByLabelText("Your statement"), { target: { value: "My view." } });
    fireEvent.change(screen.getByLabelText("Your email address, to confirm it's you"), { target: { value: "a@b.gov.uk" } });
    fireEvent.click(screen.getByLabelText(/I'm the councillor or council this is about/));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Send the statement" }));
    });
    const [url, init] = fetch.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/statements");
    expect(JSON.parse(init.body as string)).toEqual({
      page: "/councils/E08000038", name: "A Councillor", role: "Councillor", text: "My view.", link: "",
      email: "a@b.gov.uk", acting: true,
    });
    expect(screen.getByRole("status").textContent).toContain("reference 12");
    expect(screen.getByRole("status").textContent).toContain(
      "We reply within 5 working days, and decide within 20 working days.",
    );
  });

  it("counts words as the service does", () => {
    expect(words("  one two\n\nthree ")).toBe(3);
    expect(words("")).toBe(0);
  });
});
