/// <reference types="vitest/config" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/** The kit's stylesheets keep fixed names and are cached for an hour, so each page asks for them with the kit's own
 * hash (public/family/VERSION) in the address: after a kit update, a new page never gets an old stylesheet. */
const kitHash = readFileSync(here("./public/family/VERSION"), "utf8").match(/sha256 ([0-9a-f]{12})/)?.[1] ?? "";
const versionKit = (html: string) =>
  kitHash ? html.replace(/(href=")(\/family\/[\w-]+\.css)(")/g, `$1$2?v=${kitHash}$3`) : html;

/** Pages share one head, header and footer: <!--#include header--> pulls in partials/header.html, and
 * <!--#include family/shelf--> the Where They Stand family kit's public/family/shelf.html (README, "The Where They
 * Stand family"). */
function partials(): Plugin {
  const file = (name: string) =>
    name.startsWith("family/") ? here(`./public/${name}.html`) : here(`./partials/${name}.html`);
  return {
    name: "html-partials",
    transformIndexHtml: {
      order: "pre",
      handler: (html) => {
        for (let depth = 0; depth < 5 && html.includes("<!--#include "); depth++) {
          html = html.replace(/<!--#include ((?:family\/)?[\w-]+)-->/g, (_m, name: string) => readFileSync(file(name), "utf8"));
        }
        return versionKit(html);
      },
    },
  };
}

const pages = [
  "index", "councils", "council", "vote", "topics", "topic", "about", "methodology", "privacy", "privacy-measurement", "corrections", "named", "accessibility", "terms",
  "press", "status", "404",
];

export default defineConfig({
  plugins: [partials(), react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    rolldownOptions: { input: Object.fromEntries(pages.map((p) => [p, here(`./${p}.html`)])) },
  },
  test: { environment: "jsdom" },
});
