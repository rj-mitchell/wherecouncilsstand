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
// E47000002: South Yorkshire's strategic authority; E12000007: the GLA, not covered; E10000011: East Sussex, withheld
const pages = ["/", "/councils", "/councils/E08000038", "/councils/W06000015", "/councils/E06000001", VOTE, "/about",
  "/methodology", "/corrections", "/corrections?kind=statement", "/named", "/accessibility", "/privacy", "/terms",
  "/press", "/status", "/no-such-page",
  "/councils/E99999999", "/councils/E47000002", "/councils/E12000007", "/councils/E10000011"];
// what each page must show once its script has drawn it, so a page that never loads isn't passed as accessible
// (the made-up record has a statement beside Barnsley's vote, so the vote's page and Barnsley's wait for it: decision 22)
const ready = { "/councils": "table", "/councils/E08000038": ".statements", "/councils/W06000015": ".cards",
  "/councils/E47000002": ".cards", "/corrections?kind=statement": "#st-text",
  [VOTE]: ".statement", "/status": ".status-list" };

const browser = await chromium.launch();
let failures = 0;
const fail = (msg) => {
  failures++;
  console.log(msg);
};
for (const scheme of ["light", "dark"]) {
  for (const width of [1280, 390]) {
    const ctx = await browser.newContext({ viewport: { width, height: 1000 }, colorScheme: scheme, bypassCSP: true });
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
    }
    await ctx.close();
  }
}

// Council and vote pages as sent by the server, before (or without) their scripts: the page's own scripts are
// blocked, so its readable copy is what is checked, both for axe and for its text.
const plain = [["/", "What has your council decided?"], ["/councils", "Barnsley"],
  ["/councils/E08000038", "Members by party"], [VOTE, "Against"], [VOTE, "Not checked or endorsed by Where Councils Stand"],
  ["/councils/E47000002", "Constituent councils"]];
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
