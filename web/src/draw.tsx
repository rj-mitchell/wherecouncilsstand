/** How a page drawn from the record starts. The server sends each council's and vote's page with its text already
 * in place (api/plaintext.py); that text stays until the record has come, and the app then draws the page once. It
 * used to put a "Getting …" line in the text's place and then draw the page, so everything moved twice: a layout
 * shift readers see and search engines measure. The line is shown only where the server sent no text. If the record
 * can't be had, the server's text stays as it is: only a page the server sent no text into says what went wrong. A
 * search engine drawing the page may be refused the record (robots.txt), and must still see the page (decision 30). */
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";

export function drawWhenLoaded<T>(
  load: () => Promise<T>,
  page: (record: T) => ReactNode,
  failed: (message: string) => ReactNode,
  waiting: string,
) {
  const el = document.getElementById("app")!;
  const root = createRoot(el);
  const draw = (node: ReactNode) => root.render(<StrictMode>{node}</StrictMode>);
  const served = !!el.textContent?.trim();
  if (!served) draw(<p className="progress">{waiting}</p>);
  load()
    .then((record) => draw(page(record)))
    .catch((e: Error) => {
      if (!served) draw(failed(e.message));
    });
}
