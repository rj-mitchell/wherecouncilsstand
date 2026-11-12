/// <reference types="vitest" />
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const here = (p: string) => fileURLToPath(new URL(p, import.meta.url));

/** Pages share one head, header and footer: <!--#include header--> pulls in partials/header.html, and
 * <!--#include family/shelf--> the Where They Stand family kit's public/family/shelf.html (README, "In the family"). */
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
        return html;
      },
    },
  };
}

const pages = [
  "index", "councils", "council", "vote", "about", "methodology", "privacy", "corrections", "named", "accessibility", "terms",
  "press", "status", "404",
];

export default defineConfig({
  plugins: [partials(), react()],
  server: { proxy: { "/api": "http://127.0.0.1:8000" } },
  build: {
    outDir: "dist",
    sourcemap: false,
    rollupOptions: { input: Object.fromEntries(pages.map((p) => [p, here(`./${p}.html`)])) },
  },
  test: { environment: "jsdom" },
});
