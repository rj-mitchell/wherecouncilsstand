/** Dates, numbers and labels as the site writes them. */

const MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
  "November", "December"];

export function longDate(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  return `${d} ${MONTHS[m - 1]} ${y}`;
}

export function monthYear(iso: string | null | undefined): string {
  if (!iso) return "";
  const [y, m] = iso.slice(0, 10).split("-").map(Number);
  return `${MONTHS[m - 1]} ${y}`;
}

export const number = (n: number | undefined | null) => (n ?? 0).toLocaleString("en-GB");

export const KIND_LABEL: Record<string, string> = { council: "Full council", cabinet: "Cabinet", policy: "Policy committee" };

export const SIDE_LABEL = { for: "For", against: "Against", abstain: "Abstained" } as const;

/** The CSS colour variable for a party code, for charts only (docs/DESIGN.md). */
export function partyColour(code: string): string {
  return ["LAB", "CON", "LD", "REF", "GRN", "PC"].includes(code) ? `var(--party-${code})` : "var(--party-other)";
}

export function setTitle(title: string) {
  document.title = title ? `${title} — Where Councils Stand` : "Where Councils Stand";
}

export function markNav() {
  const here = location.pathname.replace(/\/$/, "") || "/";
  for (const a of document.querySelectorAll<HTMLAnchorElement>(".site-nav a")) {
    const target = a.getAttribute("href") || "";
    if (target === here || (target !== "/" && here.startsWith(target))) a.setAttribute("aria-current", "page");
  }
}
