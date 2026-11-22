/** The home page: ask a question, read a checked briefing (family/BRIEFINGS.md in the charity's repository). A saved
 * briefing (/b/<id>) is shown the same way, finished at once. While a new briefing is written, the wait shows its
 * stages from the stream's real events in order; when it is done, the record sits beside it on wide screens and opens
 * in a sheet from a chip on narrower ones. */
import { StrictMode, useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState, type FocusEvent, type FormEvent,
  type MouseEvent } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { ask, getBriefing, getCouncils, getMeta, type Answer, type AskEvent, type Meta, type Plan, type SourceCard,
  type TopicRef } from "./api";
import { checkCounts, citedSources, countsSentence, flagged, quotations, quotedFrom, type Evidence } from "./checked";
import { BriefingText, CheckDetails, CheckStrip, type Checking } from "./components/Briefing";
import { PlanChips } from "./components/PlanChips";
import { RecordPanel, Sheet } from "./components/Record";
import { AskSister, writtenBriefing } from "./components/Sister";
import { Sources } from "./components/Sources";
import { Statements } from "./components/Statements";
import { Found, Pile, PlanRead, Spines, Stages } from "./components/Wait";
import { Why } from "./components/Why";
import { drawConnector as drawLine, WIDE } from "./connector";
import { briefingTitle, longDate, markNav, monthYear, number, setTitle } from "./format";

type State = {
  question: string;
  phase: "idle" | "reading" | "finding" | "writing" | "done" | "error";
  plan: Plan | null;
  sources: SourceCard[];
  evidence: Evidence | null;
  text: string;
  answer: Answer | null;
  note: string | null;
  error: string | null;
  briefingId: string | null;
  cached: boolean;
  savedAt: string | null;
  /** the sources cited so far as the text streams, from its citation events */
  lit: number[];
  /** a saved topic briefing's topic (decision 35), whose question is the topic's own */
  topic: TopicRef | null;
};

const EMPTY: State = { question: "", phase: "idle", plan: null, sources: [], evidence: null, text: "", answer: null,
  note: null, error: null, briefingId: null, cached: false, savedAt: null, lit: [], topic: null };

function apply(s: State, ev: AskEvent): State {
  switch (ev.type) {
    case "plan":
      return { ...s, plan: ev.plan, phase: "finding" };
    case "sources":
      return { ...s, sources: ev.sources, evidence: (ev.evidence as Evidence) || null, phase: "writing" };
    case "text":
      return { ...s, text: s.text + ev.text };
    case "citation": {
      const n = s.sources[Number(ev.search_result_index)]?.n;
      return n === undefined || s.lit.includes(n) ? s : { ...s, lit: [...s.lit, n] };
    }
    case "final":
      return { ...s, answer: ev.answer, note: ev.note || null, briefingId: ev.briefing_id || s.briefingId,
        cached: !!ev.cached, phase: "done" };
    case "error":
      return { ...s, error: ev.message, phase: "error" };
    default:
      return s;
  }
}

/** The wait, as it stands: whether it is shown, for which choice, its stage, the cards dealt into the pile, the
 * checks' results running up (null until the final event), and the cards whose citations have been checked. */
type Wait = { live: boolean; sourcesOnly: boolean; stage: number; dealt: number; run: (Checking & { citations: number; quotes: number }) | null;
  checked: number[] };
const NO_WAIT: Wait = { live: false, sourcesOnly: false, stage: -1, dealt: 0, run: null, checked: [] };

const reduced = () => matchMedia("(prefers-reduced-motion: reduce)").matches;
const canHover = () => matchMedia("(hover: hover)").matches;

function useMedia(query: string): boolean {
  const [on, setOn] = useState(() => matchMedia(query).matches);
  useEffect(() => {
    const m = matchMedia(query);
    const change = () => setOn(m.matches);
    m.addEventListener("change", change);
    return () => m.removeEventListener("change", change);
  }, [query]);
  return on;
}

/** The chip a pointer or focus event happened on, if any. */
const chipOf = (e: { target: EventTarget }) => (e.target as HTMLElement).closest?.<HTMLElement>(".wts-chip") || null;

function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState(() => new URLSearchParams(location.search).get("q") || "");
  const [detailed, setDetailed] = useState(false);
  const [s, setS] = useState<State>(EMPTY);
  const [wait, setWait] = useState<Wait>(NO_WAIT);
  const [said, setSaid] = useState("");
  const [active, setActive] = useState<{ n: number; seg: number | null; chip: HTMLElement | null } | null>(null);
  const [settling, setSettling] = useState(false);
  const [sheet, setSheet] = useState<{ n: number; seg: number | null } | null>(null);
  const wide = useMedia(WIDE);
  const abort = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);
  const gridRef = useRef<HTMLDivElement>(null);
  const textRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const pileRef = useRef<HTMLDivElement>(null);
  const timers = useRef<number[]>([]);
  const dealing = useRef<number | null>(null);
  const pinnedUntil = useRef(0);
  const sheetChip = useRef<HTMLElement | null>(null);

  const later = (f: () => void, ms: number) => timers.current.push(window.setTimeout(f, ms));
  const stopTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
    if (dealing.current !== null) clearInterval(dealing.current);
    dealing.current = null;
  };
  useEffect(() => stopTimers, []);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => setMeta(null));
    getCouncils()
      .then((d) => setNames(Object.fromEntries(d.councils.map((c) => [c.gss, c.name]))))
      .catch(() => undefined);
    const shared = location.pathname.match(/^\/b\/([\w-]+)/);
    if (shared) {
      getBriefing(shared[1])
        .then((b) => {
          let st: State = { ...EMPTY, question: b.question, phase: "reading", savedAt: b.at, topic: b.topic || null };
          for (const ev of b.events) st = apply(st, ev);
          setS({ ...st, briefingId: b.id });
          setQuestion(b.question);
          setTitle(briefingTitle(b.at));
        })
        .catch((e: Error) => setS({ ...EMPTY, phase: "error", error: e.message }));
    }
  }, []);

  // the home page's proof of the checking is for the home page: not under a briefing
  useEffect(() => {
    document.getElementById("proof")?.toggleAttribute("hidden", s.phase !== "idle");
  }, [s.phase]);

  // ---------- the wait ----------

  /** 2. The records found arrive as cards, one at a time (at once with reduced motion); the next event finishes
   * dealing at once. */
  function deal(total: number) {
    if (dealing.current !== null) clearInterval(dealing.current);
    dealing.current = null;
    if (reduced() || total === 0) {
      setWait((w) => ({ ...w, dealt: total }));
      return;
    }
    setWait((w) => ({ ...w, dealt: 1 }));
    let k = 1;
    dealing.current = window.setInterval(() => {
      k += 1;
      setWait((w) => ({ ...w, dealt: Math.min(total, k) }));
      if (k >= total && dealing.current !== null) {
        clearInterval(dealing.current);
        dealing.current = null;
      }
    }, 45);
  }
  function dealtAll(total: number) {
    if (dealing.current !== null) clearInterval(dealing.current);
    dealing.current = null;
    setWait((w) => ({ ...w, dealt: total }));
  }

  /** 4. The finished briefing is shown at once; the strip's counts run up through the real results, passage by
   * passage, each quotation taking its highlight in turn. 5. Then the pile settles into the record. */
  function check(answer: Answer) {
    const segs = answer.segments || [];
    const c = checkCounts(answer);
    const quotes = quotations(segs);
    const steps = segs.map((seg, i) => [seg, i] as const).filter(([seg]) => seg.status === "cited");
    if (reduced() || !steps.length) {
      // without movement: the results at once, in the same stage
      setWait((w) => ({ ...w, stage: 3, run: { citations: c.citations_matched, quotes: c.quotes_found, upTo: segs.length,
        flash: null } }));
      later(() => finish(answer), reduced() ? 400 : 0);
      return;
    }
    setWait((w) => ({ ...w, stage: 3, run: { citations: 0, quotes: 0, upTo: -1, flash: null } }));
    const stepMs = Math.min(110, 2400 / steps.length);
    let cit = 0, qt = 0;
    const done: number[] = [];
    steps.forEach(([seg, i], j) => {
      cit = Math.min(c.citations_matched, cit + (seg.sources || []).length);
      const found = quotes[i].filter((q) => q.endsHere && !q.missing && q.sources.length && !flagged(seg)).length;
      qt = Math.min(c.quotes_found, qt + found);
      if (found) for (const n of seg.sources || []) if (!done.includes(n)) done.push(n);
      const at = { citations: cit, quotes: qt, upTo: i, flash: i }, cards = [...done];
      later(() => setWait((w) => ({ ...w, run: at, checked: cards })), 250 + j * stepMs);
    });
    later(() => finish(answer), 250 + steps.length * stepMs + 500);
  }

  /** The end of the wait: the strip as it stays, the counts said once, and on wide screens the record beside it. */
  function finish(answer: Answer | null) {
    stopTimers();
    setWait(NO_WAIT);
    if (answer && !answer.no_records) {
      setSaid(countsSentence(answer));
      if (matchMedia(WIDE).matches && !reduced()) {
        setSettling(true);
        later(() => setSettling(false), 600);
      }
    }
  }

  function handle(ev: AskEvent, before: State, after: State, sourcesOnly: boolean) {
    if (ev.type === "plan") {
      setWait((w) => ({ ...w, stage: 1 }));
      setSaid("Searching the record.");
    } else if (ev.type === "sources") {
      setWait((w) => ({ ...w, stage: Math.max(w.stage, 1) }));
      deal(after.sources.length);
    } else if ((ev.type === "text" || ev.type === "citation") && before.text === "" && !before.lit.length) {
      dealtAll(after.sources.length);
      setWait((w) => ({ ...w, stage: 2 }));
      setSaid(`Writing the briefing from these ${after.sources.length} records only.`);
    } else if (ev.type === "final") {
      const a = ev.answer;
      if (a && !a.no_records) {
        dealtAll(after.sources.length);
        setSaid("Checking every citation and quotation.");
        check(a);
        // on a phone the strip can be below the screen while the cards fill it: brought into view, but only from
        // above, so a reader already further down is not moved
        requestAnimationFrame(() => {
          const strip = document.getElementById("check");
          if (strip && strip.getBoundingClientRect().top > innerHeight)
            strip.scrollIntoView({ block: "nearest", behavior: reduced() ? "auto" : "smooth" });
        });
      } else if (!a && after.sources.length) {
        // sources only (or no briefing could be written): the records dealt in full, then the list of sources
        setWait((w) => ({ ...w, sourcesOnly: true, stage: 2 }));
        setSaid(`${after.sources.length} records found. ${sourcesOnly ? "Sources only: no" : "No"} briefing was written.`);
        const end = () => (dealing.current !== null ? later(end, 100) : later(() => finish(null), 900));
        end();
      } else {
        finish(null);
        setSaid(a?.no_records ? "No records found." : ev.note || "");
      }
    } else if (ev.type === "error") {
      finish(null);
      setSaid(ev.message);
    }
  }

  async function run(q: string, sourcesOnly: boolean) {
    if (q.trim().length < 3) return;
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    stopTimers();
    setActive(null);
    setSheet(null);
    let st: State = { ...EMPTY, question: q, phase: "reading" };
    setS(st);
    setWait({ ...NO_WAIT, live: true, sourcesOnly, stage: 0 });
    setSaid("Reading the question.");
    setTitle(briefingTitle(new Date().toISOString()));
    if (location.pathname !== "/") history.replaceState(null, "", "/");
    requestAnimationFrame(() => resultRef.current?.focus());
    try {
      await ask({ question: q, mode: detailed ? "comprehensive" : "summary", sources_only: sourcesOnly }, (ev) => {
        const before = st;
        st = apply(st, ev);
        setS(st);
        if (!ctrl.signal.aborted) handle(ev, before, st, sourcesOnly);
      }, ctrl.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        finish(null);
        setS({ ...st, phase: "error", error: (e as Error).message });
        setSaid((e as Error).message);
      }
    }
  }

  function submit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    const how = ((e.nativeEvent as SubmitEvent).submitter as HTMLButtonElement | null)?.value;
    run(question, how === "sources");
  }

  // ---------- the finished briefing and the record beside it ----------

  const answer = s.answer && !s.answer.no_records ? s.answer : null;
  const byN = useMemo(() => Object.fromEntries(s.sources.map((x) => [x.n, x])), [s.sources]);
  const quoted = useMemo(() => (answer ? quotedFrom(answer) : {}), [answer]);
  const cited = useMemo(() => (answer ? citedSources(answer).filter((n) => byN[n]) : []), [answer, byN]);
  const panel = !!answer && !wait.live && wide && cited.length > 0;

  /** A line from the chosen chip's line of text to its passage, across the gutter. */
  const drawConnector = useCallback((chip: HTMLElement | null) => {
    drawLine(svgRef.current, gridRef.current, textRef.current, chip);
  }, []);

  // open from the start on the first source, as the text cites them
  useEffect(() => {
    if (!panel) {
      if (!answer) setActive(null);
      return;
    }
    if (active && byN[active.n]) return;
    const first = textRef.current?.querySelector<HTMLElement>(".wts-chip");
    setActive({ n: first ? Number(first.dataset.source) : cited[0], seg: first ? Number(first.dataset.seg) : null, chip: null });
  }, [panel, answer, cited, byN, active]);

  // the chosen chip marked, and joined to its passage
  useLayoutEffect(() => {
    for (const c of textRef.current?.querySelectorAll<HTMLElement>(".wts-chip") || []) {
      const on = !!active && panel && Number(c.dataset.source) === active.n && (!active.chip || c === active.chip);
      c.setAttribute("aria-current", String(on));
    }
    drawConnector(panel ? active?.chip || null : null);
  }, [active, panel, drawConnector, answer]);

  // as the reader scrolls a wide screen, the chip nearest the upper third of the window leads, unless they have just
  // chosen one
  useEffect(() => {
    if (!panel) return;
    let ticking = false;
    const onScroll = () => {
      if (ticking) return;
      ticking = true;
      requestAnimationFrame(() => {
        ticking = false;
        const chips = [...(textRef.current?.querySelectorAll<HTMLElement>(".wts-chip") || [])];
        const current = chips.find((c) => c.getAttribute("aria-current") === "true") || null;
        if (Date.now() < pinnedUntil.current) {
          drawConnector(current);
          return;
        }
        const line = innerHeight * 0.38;
        let best: HTMLElement | null = null, bd = Infinity;
        for (const c of chips) {
          const r = c.getBoundingClientRect();
          const d = Math.abs(r.top - line);
          if (r.bottom > 0 && r.top < innerHeight && d < bd) {
            bd = d;
            best = c;
          }
        }
        if (best && best !== current) setActive({ n: Number(best.dataset.source), seg: Number(best.dataset.seg), chip: best });
        else drawConnector(current);
      });
    };
    const onResize = () => drawConnector(textRef.current?.querySelector<HTMLElement>('.wts-chip[aria-current="true"]') || null);
    addEventListener("scroll", onScroll, { passive: true });
    addEventListener("resize", onResize);
    return () => {
      removeEventListener("scroll", onScroll);
      removeEventListener("resize", onResize);
    };
  }, [panel, drawConnector]);

  // a sheet is for narrower screens: widening the window closes it
  useEffect(() => {
    if (wide) setSheet(null);
  }, [wide]);

  function choose(chip: HTMLElement, pin: number) {
    pinnedUntil.current = Date.now() + pin;
    setActive({ n: Number(chip.dataset.source), seg: Number(chip.dataset.seg), chip });
  }
  function onChipClick(e: MouseEvent) {
    const chip = chipOf(e);
    if (!chip || !answer) return;
    if (matchMedia(WIDE).matches) {
      if (wait.live) finish(answer); // the checks' results shown at once
      choose(chip, 4000);
    } else {
      sheetChip.current = chip;
      setSheet({ n: Number(chip.dataset.source), seg: Number(chip.dataset.seg) });
    }
  }
  function onChipFocus(e: FocusEvent) {
    const chip = chipOf(e);
    if (chip && panel) choose(chip, 4000);
  }
  function onChipHover(e: MouseEvent) {
    const chip = chipOf(e);
    if (chip && panel && canHover() && chip.getAttribute("aria-current") !== "true") choose(chip, 2500);
  }
  function step(d: number) {
    if (!cited.length) return;
    const i = cited.indexOf(active?.n ?? cited[0]);
    const n = cited[(i + d + cited.length) % cited.length];
    const chip = textRef.current?.querySelector<HTMLElement>(`.wts-chip[data-source="${n}"]`) || null;
    pinnedUntil.current = Date.now() + 4000;
    setActive({ n, seg: chip ? Number(chip.dataset.seg) : null, chip });
    chip?.scrollIntoView({ block: "center", behavior: reduced() ? "auto" : "smooth" });
  }
  const closeSheet = useCallback(() => {
    setSheet(null);
    sheetChip.current?.focus();
  }, []);

  // ---------- the cards in the pile, brought into view as they are cited ----------

  useEffect(() => {
    const pile = pileRef.current;
    const n = s.lit[s.lit.length - 1];
    const card = n === undefined ? null : pile?.querySelector<HTMLElement>(`.wts-card[data-source="${n}"]`);
    if (!pile || !card) return;
    // inside the pile only: the page itself does not move
    pile.scrollTop = Math.max(0, card.offsetTop - pile.offsetTop - 40);
    pile.scrollLeft = Math.max(0, card.offsetLeft - pile.offsetLeft - 40);
  }, [s.lit, wait.dealt]);
  useEffect(() => {
    // the newest card in view while they arrive
    const pile = pileRef.current;
    if (!pile || s.lit.length) return;
    pile.scrollTop = pile.scrollHeight;
    pile.scrollLeft = pile.scrollWidth;
  }, [wait.dealt, s.lit.length]);

  const t = meta?.totals;
  const busy = wait.live || ["reading", "finding", "writing"].includes(s.phase);
  const shareUrl = s.briefingId ? `${location.origin}/b/${s.briefingId}` : null;
  const written = !!answer || (!!s.text && !wait.sourcesOnly);
  const pile = wait.live && s.sources.length > 0 && wait.stage >= 1 ? (
    <Pile ref={pileRef} sources={s.sources} dealt={wait.dealt} lit={s.lit} checked={wait.checked} />
  ) : null;
  const side = (wide && pile) || (panel && active) ? (
    <aside className="record-col" aria-label="The record beside the briefing">
      {wide && pile ? (
        <div className="record-col__pile">
          <p className="wts-record__title">
            The records found <span aria-hidden="true">{wait.dealt}</span>
          </p>
          {pile}
        </div>
      ) : (
        panel && active && <RecordPanel n={active.n} nowSeg={active.seg} cited={cited} byN={byN} quoted={quoted} onStep={step}
          settling={settling} />
      )}
    </aside>
  ) : null;

  return (
    <>
      <div className="home-top">
        <h1>Council decisions, from the minutes</h1>
        <p className="lede">
          Ask about anything councils across the UK have discussed, decided or voted on at full council and cabinet, and
          England’s strategic authorities at their boards and scrutiny committees.
        </p>
        <form className="ask-form" onSubmit={submit}>
          <label htmlFor="question" className="visually-hidden">
            Your question
          </label>
          <textarea id="question" value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)}
            placeholder="For example: what have councils decided about weekly bin collections?"
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
                e.preventDefault();
                if (!busy) run(question, false);
              }
            }} />
          <div className="ask-options">
            <button className="button" type="submit" name="how" value="briefing" disabled={busy || question.trim().length < 3}>
              {busy && !wait.sourcesOnly ? "Asking" : "Ask"}
            </button>
            <button className="button secondary" type="submit" name="how" value="sources"
              disabled={busy || question.trim().length < 3}>
              Sources only (no AI)
            </button>
            <label>
              <input type="checkbox" checked={detailed} onChange={(e) => setDetailed(e.target.checked)} /> Detailed briefing
            </label>
          </div>
        </form>
        <Why />
        {t && (
          <p className="small record">
            The record holds {number(t.meetings)} meetings and {number(t.named_votes)} named votes from{" "}
            {number(t.loaded)} councils since {monthYear(meta?.start)}
            {meta?.last_update ? <>, and was last updated on {longDate(meta.last_update.finished)}</> : null}.{" "}
            <a href="/councils">Which councils are covered</a>
          </p>
        )}
      </div>

      {/* the one place the page says what it is doing, each stage once (family/BRIEFINGS.md, "The wait") */}
      <p className="visually-hidden" role="status" aria-live="polite">{said}</p>

      <div ref={resultRef} tabIndex={-1} className="result">
        {s.phase === "idle" && meta && (
          <>
            <h2>Questions to try</h2>
            <ul className="examples">
              {meta.examples.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => { setQuestion(q); run(q, false); }}>
                    {q}
                  </button>
                </li>
              ))}
            </ul>
          </>
        )}
        {s.phase !== "idle" && (
          <article className="briefing briefing--checked wts-cloth--councils" aria-labelledby="briefing-question">
            <p className="briefing-head" id="briefing-question">
              <span>
                {s.topic ? (
                  <>
                    Topic briefing, <a href={s.topic.path}>{s.topic.title}</a>: <em>{s.question}</em>
                  </>
                ) : (
                  <>
                    {s.savedAt ? "Asked by a reader" : "Your question"}: <em>{s.question}</em>
                  </>
                )}
              </span>
              <span>{longDate(s.savedAt || new Date().toISOString())}</span>
            </p>
            {s.plan && !wait.live && <PlanChips plan={s.plan} meta={meta} councilNames={names} />}
            {wait.live && <Stages stage={wait.stage} sourcesOnly={wait.sourcesOnly} />}
            <div ref={gridRef} className={`result-grid${side ? " has-record" : ""}`}>
              <div className="result-main">
                {wait.live && (
                  <div className="wait">
                    {!s.plan && <Spines />}
                    {s.plan && <PlanRead plan={s.plan} regions={meta?.regions} types={meta?.types} councilNames={names} />}
                    {wait.stage >= 1 && s.sources.length > 0 && (
                      <Found evidence={s.evidence} shown={wait.dealt} total={s.sources.length} />
                    )}
                    {!wide && pile}
                    {wait.stage >= 2 && !wait.sourcesOnly && (
                      <p className="wait__only">
                        Writing from these {s.sources.length} records only. The AI may use these and nothing else.
                      </p>
                    )}
                  </div>
                )}
                {written && <p className="ai-label">Briefing written by AI</p>}
                {answer && <CheckStrip answer={answer} running={wait.run} />}
                <div ref={textRef} className="briefing-text" onClick={onChipClick} onFocus={onChipFocus}
                  onMouseOver={onChipHover}>
                  {s.answer ? (
                    <BriefingText segments={s.answer.segments} sources={s.sources} checking={wait.run} />
                  ) : (
                    s.text && <BriefingText text={s.text} cursor={wait.live} />
                  )}
                </div>
                {s.note && <p className="notice info">{s.note}</p>}
                {s.error && <p className="notice">{s.error}</p>}
                {answer && (
                  <>
                    {(answer.loaded_words || 0) > 0 && (
                      <p className="notice">
                        {answer.loaded_words === 1 ? "One word" : `${answer.loaded_words} words`} in the briefing’s own voice
                        may be loaded. Briefings are meant to report what the minutes record, in neutral words.
                      </p>
                    )}
                    {!wait.live && <CheckDetails answer={answer} found={s.sources.length} />}
                    {shareUrl && !wait.live && (
                      <>
                        <p className="small">
                          Link to this briefing: <a href={shareUrl}>{shareUrl}</a>
                        </p>
                        <p className="small">
                          <a href={`/corrections?page=${encodeURIComponent(shareUrl)}`}>Report a problem with this briefing</a>
                        </p>
                      </>
                    )}
                  </>
                )}
                {writtenBriefing(s) && !wait.live && <AskSister site="mps" question={s.question} />}
              </div>
              {side}
              <svg className="wts-connector" ref={svgRef} aria-hidden="true" focusable="false" />
            </div>
          </article>
        )}
        {/* statements in their authors' own words beside a saved briefing (decision 22), after it, never in it */}
        {s.savedAt && s.briefingId && <Statements page={`/b/${s.briefingId}`} />}
        {!wait.live && <Sources sources={s.sources} />}
      </div>
      {sheet && byN[sheet.n] && (
        <Sheet n={sheet.n} nowSeg={sheet.seg} source={byN[sheet.n]} quoted={quoted[sheet.n]} onClose={closeSheet} />
      )}
    </>
  );
}

/** The home page's proof is drawn without a script, its sentence set beside the passage it came from. Where the
 * script runs, the two highlights are made level, and the rule between them drawn at their first line, whatever the
 * width (the kit's --wts-join). */
function alignProof() {
  const pair = document.querySelector<HTMLElement>("#proof .wts-proof__pair");
  if (!pair || pair.offsetParent === null) return;
  const left = pair.firstElementChild as HTMLElement | null;
  const quote = pair.querySelector(".wts-proof__said .wts-quote"), mark = pair.querySelector(".wts-passage mark");
  if (!left || !quote || !mark) return;
  if (!matchMedia("(min-width: 48rem)").matches) {
    left.style.removeProperty("padding-block-start");
    return;
  }
  left.style.setProperty("padding-block-start", "0px");
  const q = quote.getClientRects()[0], m = mark.getClientRects()[0], box = pair.getBoundingClientRect();
  if (!q || !m) return;
  left.style.setProperty("padding-block-start", `${Math.max(0, m.top - q.top)}px`);
  pair.style.setProperty("--wts-join", `${m.top - box.top + m.height / 2}px`);
}

markNav();
alignProof();
addEventListener("resize", alignProof);
document.fonts?.ready.then(alignProof);
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
