// Accessibility check for CI (as Where MPs Stand's): loads the site's pages in Chromium, light and dark, at desktop
// and phone widths, and fails on any serious or critical WCAG 2.2 AA problem found by axe, or a page that scrolls
// sideways. It runs against the site on the made-up record (scripts/fixture_site.py). It also checks the pages the
// server sends with readable text (council and vote pages, the list of councils, the home page) with scripts off.
// Usage: node scripts/a11y.mjs http://127.0.0.1:8000   (with playwright and axe-core installed beside it)
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { chromium } from "playwright";

const require = createRequire(import.meta.url);
const axe = readFileSync(require.resolve("axe-core/axe.min.js"), "utf8");
const base = process.argv[2] ?? "http://127.0.0.1:8000";
const VOTE = "/votes/E08000038:1:10:0";
// a named vote hidden while a concern is decided (the made-up record hides Cardiff's): the note in its place
const HIDDEN = "/votes/W06000015:3:30:0";
// E47000002: South Yorkshire's strategic authority; E12000007: the GLA, not covered; E10000011: East Sussex, withheld
// the topic briefings (decision 35): the list, a topic the made-up record has a briefing for (written by the site's
// own weekly command, scripts/fixture_site.py), and one not written yet
const TOPIC = "/topics/council-tax-and-budgets";
const pages = ["/", "/councils", "/councils/E08000038", "/councils/W06000015", "/councils/E06000001", VOTE, "/about",
  "/topics", TOPIC, "/topics/adult-social-care",
  "/methodology", "/corrections", "/corrections?kind=statement", "/named", "/accessibility", "/privacy", "/terms",
  "/press", "/status", "/no-such-page",
  "/councils/E99999999", "/councils/E47000002", "/councils/E12000007", "/councils/E10000011", HIDDEN];
// a saved briefing, made up here and served in place of the API's answer, with each kind of point the family's checked
// briefing marks (the charity's family/BRIEFINGS.md): a quotation found word for word, one shown as the source's
// quotation by the display rule ("beside"), one not found word for word, text with no source, and text whose only
// citation failed the check (so was removed). Its marks are checked for contrast like everything else, and that each
// is drawn and has its words. The made-up record's own saved briefing (scripts/fixture_site.py) is checked as the
// server sends it, with the record beside it on a computer and in a sheet on a phone.
const SAMPLE = "a11ysample";
const SAVED = "/b/madeupbriefing";
const UNSUPPORTED = "Most councils agreed.";
const INVALID = "Barnsley closed four libraries in 2024.";
const MISQUOTE = '"we will keep every library open"';
const FOUND = '"the library strategy, including community libraries"';
const BESIDE = "“that the strategy be adopted”";
const quoted = ` The minutes record the leader saying ${MISQUOTE} in May`;
const source = { n: 1, title: "", url: "https://example.org/minutes", record_id: "E08000038:2:20", date: "2025-02-26",
  gss: "E08000038", council_name: "Barnsley Metropolitan Borough Council", committee: "Cabinet", kind: "cabinet",
  item_title: "Library Strategy", item_number: "20.", control: "LAB", group: "Councils controlled by Labour",
  named: [], text: "The Cabinet considered the library strategy, including community libraries. RESOLVED that the strategy be adopted.",
  votes: [] };
const sample = {
  id: SAMPLE, at: "2026-11-13T12:00:00Z", question: "What have councils decided about libraries?", options: {},
  events: [{ type: "sources", sources: [source], candidates: 1, semantic: true, evidence: {} },
    { type: "final", briefing_id: SAMPLE, answer: {
    segments: [
      { text: `Barnsley's cabinet considered ${FOUND}`, sources: [1], status: "cited" },
      { text: ". ", sources: [], status: "connective" },
      { text: UNSUPPORTED, sources: [], status: "unsupported" },
      { text: " ", sources: [], status: "connective" },
      { text: INVALID, sources: [], status: "invalid" },
      { text: quoted, sources: [1], status: "cited",
        misquotes: [{ start: quoted.indexOf(MISQUOTE), end: quoted.indexOf(MISQUOTE) + MISQUOTE.length, text: MISQUOTE }] },
      { text: ". The cabinet resolved ", sources: [], status: "unsupported" },
      { text: BESIDE, sources: [1], status: "cited", beside: true },
      { text: " in February 2025", sources: [1], status: "cited" },
      { text: ".", sources: [], status: "connective" },
    ],
    no_records: false, citations_total: 4, citations_invalid: 1, unsupported_segments: 2, loaded_words: 0,
    quotes_total: 3, quotes_unverified: 1 } }],
};
pages.push(`/b/${SAMPLE}`, SAVED);

// what each page must show once its script has drawn it, so a page that never loads isn't passed as accessible
// (the made-up record has a statement beside Barnsley's vote, so the vote's page and Barnsley's wait for it: decision 22)
const ready = { "/councils": "table", "/councils/E08000038": ".statements", "/councils/W06000015": ".facts",
  "/councils/E47000002": ".facts", "/corrections?kind=statement": "#st-text",
  [VOTE]: ".statement", "/status": ".status-list", "/corrections": ".corrections-log", [HIDDEN]: ".notice",
  [`/b/${SAMPLE}`]: ".wts-check", [SAVED]: ".wts-check", "/topics": ".topic-list", [TOPIC]: ".wts-check" };

const browser = await chromium.launch();
let failures = 0;
const fail = (msg) => {
  failures++;
  console.log(msg);
};
for (const scheme of ["light", "dark"]) {
  for (const width of [1280, 390]) {
    const ctx = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: scheme, bypassCSP: true });
    await ctx.route(`**/api/briefings/${SAMPLE}`, (route) =>
      route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(sample) }));
    const page = await ctx.newPage();
    page.on("pageerror", (err) => fail(`${scheme} ${width}px ${page.url()}: script error: ${err.message}`));
    for (const path of pages) {
      await page.goto(base + path, { waitUntil: "networkidle" }).catch(() => {});
      if (ready[path]) {
        await page.waitForSelector(ready[path], { timeout: 10_000 }).catch(() => fail(`${path}: never finished loading`));
      }
      await page.addScriptTag({ content: axe });
      const result = await page.evaluate(async () =>
        window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
      for (const v of result.violations.filter((v) => v.impact === "serious" || v.impact === "critical")) {
        fail(`${scheme} ${width}px ${path}: ${v.id} (${v.impact}) ${v.help}`);
        for (const n of v.nodes.slice(0, 3)) console.log(`    ${n.target.join(" ")}`);
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 1) fail(`${scheme} ${width}px ${path}: the page scrolls sideways by ${overflow}px`);
      if (path === `/b/${SAMPLE}`) {
        // every mark is drawn and has its words; the quotation the display rule gave its source is never marked as
        // having no source; the strip says the counts
        const drawn = await page.evaluate(() => ({
          marked: [...document.querySelectorAll(".answer .wts-nosource")].map((e) => e.textContent),
          missing: document.querySelector(".answer .wts-quote--missing")?.textContent ?? "",
          found: [...document.querySelectorAll(".answer .wts-quote--checked")].map((e) => e.textContent),
          strip: document.querySelector(".wts-check")?.textContent ?? "",
          chip: document.querySelector(".answer .wts-chip")?.textContent ?? "",
        }));
        const wrong = [
          !drawn.marked.some((m) => m.startsWith(UNSUPPORTED) && m.includes("(no source)")) && "the text with no source is not marked",
          !drawn.marked.some((m) => m.startsWith(INVALID) && m.includes("was removed")) && "the text whose citation failed is not marked",
          drawn.marked.some((m) => m.includes(BESIDE)) && "a quotation found word for word is marked as having no source",
          !drawn.missing.includes("Not found word for word") && "the quotation not found is not marked in words",
          !drawn.missing.includes("(quotation not found word for word in the minutes cited for it") && "the quotation not found is not explained",
          drawn.found.length !== 2 || !drawn.found.every((f) => f.includes("(quotation, found word for word in the minutes of source 1)"))
            ? "the quotations found are not each marked with their words" : false,
          !/Checked against the council minutes/.test(drawn.strip) && "no check strip",
          !/3\s*of 4\s*To check\s*citations matched/.test(drawn.strip) && "the strip's citations are wrong",
          drawn.chip !== "Source 1Barnsley Metropolitan Borough Council, cabinet, 26 February 2025" && `the chip reads "${drawn.chip}"`,
        ].filter(Boolean);
        for (const w of wrong) fail(`${scheme} ${width}px ${path}: ${w}`);
      }
      if ((path === SAVED || path === TOPIC) && width === 1280) {
        await page.waitForSelector("#record-panel", { timeout: 5_000 }).catch(() => {});
        const panel = await page.evaluate(() => document.querySelector("#record-panel .wts-slip__top")?.textContent ?? "");
        if (!panel) fail(`${scheme} ${width}px ${path}: the record is not open beside the briefing`);
      }
      if ((path === SAVED || path === TOPIC) && width === 390) {
        // the sheet: focus moves to its heading, stays inside it, and goes back to the chip when it closes
        const chip = page.locator(".answer .wts-chip").first();
        await chip.click();
        await page.waitForSelector("#sheet");
        const focused = await page.evaluate(() => document.activeElement?.id);
        if (focused !== "sheet-head") fail(`${scheme} ${width}px ${path}: the sheet's heading does not take focus`);
        await page.addScriptTag({ content: axe });
        const open = await page.evaluate(async () =>
          window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
        for (const v of open.violations.filter((v) => v.impact === "serious" || v.impact === "critical")) {
          fail(`${scheme} ${width}px ${path} (sheet open): ${v.id} (${v.impact}) ${v.help}`);
        }
        for (let i = 0; i < 6; i++) await page.keyboard.press("Tab");
        const inside = await page.evaluate(() => !!document.activeElement?.closest("#sheet"));
        if (!inside) fail(`${scheme} ${width}px ${path}: focus left the sheet`);
        await page.keyboard.press("Escape");
        const back = await page.evaluate(() => !document.querySelector("#sheet") && !!document.activeElement?.matches(".wts-chip"));
        if (!back) fail(`${scheme} ${width}px ${path}: Escape did not close the sheet and return focus to the chip`);
      }
    }
    await ctx.close();
  }
}

// Council and vote pages as sent by the server, before (or without) their scripts: the page's own scripts are
// blocked, so its readable copy is what is checked, both for axe and for its text.
const plain = [["/", "Council decisions, from the minutes"], ["/", "Every briefing, checked against the council minutes"], ["/councils", "Barnsley"],
  ["/councils/E08000038", "Members by party"], [VOTE, "Against"], [VOTE, "Not checked or endorsed by Where Councils Stand"],
  ["/councils/E47000002", "Constituent councils"], ["/corrections", "Briefing withdrawn"],
  ["/corrections", "A made-up correction"], [HIDDEN, "This page is hidden while a concern about it is decided."],
  ["/topics", "Council tax and budgets"], [TOPIC, "Checked against the council minutes"], [TOPIC, "word for word"],
  ["/", "Every topic, with the question each one asks"]];
for (const scheme of ["light", "dark"]) {
  for (const width of [1280, 390]) {
    const ctx = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: scheme, bypassCSP: true });
    await ctx.route(/\/assets\/.*\.js$/, (route) => route.abort());
    const page = await ctx.newPage();
    for (const [path, text] of plain) {
      await page.goto(base + path, { waitUntil: "networkidle" }).catch(() => {});
      const body = await page.locator("main").innerText();
      if (!body.includes(text) || body.includes("This page needs JavaScript")) fail(`no scripts ${path}: the page's text isn't there`);
      await page.addScriptTag({ content: axe });
      const result = await page.evaluate(async () =>
        window.axe.run(document, { runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"] } }));
      for (const v of result.violations.filter((v) => v.impact === "serious" || v.impact === "critical")) {
        fail(`no scripts ${scheme} ${width}px ${path}: ${v.id} (${v.impact}) ${v.help}`);
        for (const n of v.nodes.slice(0, 3)) console.log(`    ${n.target.join(" ")}`);
      }
      const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
      if (overflow > 1) fail(`no scripts ${scheme} ${width}px ${path}: the page scrolls sideways by ${overflow}px`);
    }
    await ctx.close();
  }
}
await browser.close();
console.log(failures ? `${failures} accessibility problem(s) found` : `No serious accessibility problems on ${pages.length} pages`);
process.exit(failures ? 1 : 0);
