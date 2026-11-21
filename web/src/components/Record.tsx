/** The record beside a briefing (family/BRIEFINGS.md, "The record beside the briefing"): on wide screens a panel
 * beside the text, open from the start on the first source, with "Previous source" and "Next source"; on narrower
 * screens a sheet from the bottom of the screen that a chip opens, holding the same slip. */
import { useEffect, useLayoutEffect, useRef } from "react";
import { createPortal } from "react-dom";
import type { SourceCard } from "../api";
import type { Quoted } from "../checked";
import { Slip } from "./Briefing";

/** The panel. ``n`` is the source shown, ``nowSeg`` the passage of the briefing whose chip chose it (its quotations
 * are outlined), ``cited`` the sources the chips point to, in order. */
export function RecordPanel({ n, nowSeg, cited, byN, quoted, onStep, settling = false }: {
  n: number;
  nowSeg: number | null;
  cited: number[];
  byN: Record<number, SourceCard>;
  quoted: Record<number, Quoted[]>;
  onStep: (d: number) => void;
  settling?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const s = byN[n];
  // the chosen words in view inside the passage, which scrolls on its own
  useLayoutEffect(() => {
    const passage = ref.current?.querySelector<HTMLElement>(".wts-passage");
    const mark = ref.current?.querySelector<HTMLElement>("mark.wts-now") || ref.current?.querySelector<HTMLElement>("mark");
    if (passage) passage.scrollTop = mark ? Math.max(0, mark.offsetTop - passage.offsetTop - 24) : 0;
  }, [n, nowSeg]);
  if (!s) return null;
  return (
    <div ref={ref} className={`wts-record${settling ? " is-settling" : ""}`} id="record-panel">
      <p className="wts-record__title">
        The record <span>Source {n}, {cited.indexOf(n) + 1} of {cited.length}</span>
      </p>
      <Slip source={s} quoted={quoted[n]} nowSeg={nowSeg} passageId="record-passage" />
      <div className="wts-record__pager">
        <button type="button" onClick={() => onStep(-1)}>Previous source</button>
        <button type="button" onClick={() => onStep(1)}>Next source</button>
      </div>
    </div>
  );
}

/** The sheet: a dialog holding the source's slip. Focus moves to its heading, stays inside it, and goes back to the
 * chip that opened it when it closes (Close, Escape, or a tap outside it). */
export function Sheet({ n, nowSeg, source, quoted, onClose }: {
  n: number;
  nowSeg: number | null;
  source: SourceCard;
  quoted?: Quoted[];
  onClose: () => void;
}) {
  const sheet = useRef<HTMLDivElement>(null);
  const head = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    head.current?.focus();
    document.body.classList.add("has-sheet");
    const keys = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onClose();
        return;
      }
      if (e.key !== "Tab" || !sheet.current) return;
      const f = [...sheet.current.querySelectorAll<HTMLElement>("button, a[href], [tabindex='0']")];
      const i = f.indexOf(document.activeElement as HTMLElement);
      if (e.shiftKey && i <= 0) {
        e.preventDefault();
        f[f.length - 1].focus();
      } else if (!e.shiftKey && i === f.length - 1) {
        e.preventDefault();
        f[0].focus();
      } else if (i < 0) {
        e.preventDefault();
        f[0].focus();
      }
    };
    document.addEventListener("keydown", keys);
    return () => {
      document.removeEventListener("keydown", keys);
      document.body.classList.remove("has-sheet");
    };
  }, [onClose]);
  return createPortal(
    <div className="wts-cloth--councils">
      <div className="wts-sheet__back" onClick={onClose} />
      <div ref={sheet} className="wts-sheet" role="dialog" aria-modal="true" aria-labelledby="sheet-head" id="sheet">
        <div className="wts-sheet__head">
          <h2 id="sheet-head" ref={head} tabIndex={-1}>Source {n}: the record</h2>
          <button type="button" className="wts-sheet__close" onClick={onClose}>Close</button>
        </div>
        <Slip source={source} quoted={quoted} nowSeg={nowSeg} passageId="sheet-passage" short />
      </div>
    </div>,
    document.body,
  );
}
