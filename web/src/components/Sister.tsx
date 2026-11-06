/** Links to the charity's sister sites (README, "In the family"). A link to a sister site always names it and shows
 * its spine, so the reader knows they are going to another site. The spine is drawn as the family kit draws it
 * (public/family: marks.mjs's bookSpine), and takes its cloth from the kit's stylesheet, light or dark. */
import type { ReactNode } from "react";

export const SISTERS = {
  landlords: { name: "Where Landlords Stand", url: "https://wherelandlordsstand.com", cloth: "#40484D" },
  mps: { name: "Where MPs Stand", url: "https://wherempsstand.com", cloth: "#1D4535" },
} as const;

export type Sister = keyof typeof SISTERS;

export function Spine({ site, height = 24 }: { site: Sister; height?: number }) {
  return (
    <svg className={`wts-spine wts-cloth--${site}`} width="10" height={height} viewBox={`0 0 10 ${height}`}
      aria-hidden="true" focusable="false">
      <rect className="wts-spine__cloth" width="10" height={height} fill={SISTERS[site].cloth} />
      <path className="wts-spine__gilt" d={`M0 4.5h10M0 7h10M0 ${height - 4}h10`} stroke="#D9BC72" strokeWidth="1.2"
        fill="none" />
    </svg>
  );
}

/** A quiet block of links to one sister site, under its name and spine. */
export function SisterLinks({ site, children }: { site: Sister; children: ReactNode }) {
  return (
    <aside className="sister" aria-label={`On ${SISTERS[site].name}`}>
      <Spine site={site} height={32} />
      <div>
        <p className="sister-name">On {SISTERS[site].name}</p>
        {children}
      </div>
    </aside>
  );
}
