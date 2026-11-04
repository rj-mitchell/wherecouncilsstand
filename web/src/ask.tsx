/** The home page: ask a question, read a sourced briefing. A saved briefing (/b/<id>) is shown the same way. */
import { StrictMode, useEffect, useRef, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { ask, getBriefing, getCouncils, getMeta, type Answer, type AskEvent, type Meta, type Plan, type SourceCard } from "./api";
import { BriefingText } from "./components/Briefing";
import { PlanChips } from "./components/PlanChips";
import { Sources } from "./components/Sources";
import { longDate, markNav, monthYear, number, setTitle } from "./format";

type State = {
  question: string;
  phase: "idle" | "reading" | "finding" | "writing" | "done" | "error";
  plan: Plan | null;
  sources: SourceCard[];
  text: string;
  answer: Answer | null;
  note: string | null;
  error: string | null;
  briefingId: string | null;
  cached: boolean;
  savedAt: string | null;
};

const EMPTY: State = { question: "", phase: "idle", plan: null, sources: [], text: "", answer: null, note: null, error: null,
  briefingId: null, cached: false, savedAt: null };

function apply(s: State, ev: AskEvent): State {
  switch (ev.type) {
    case "plan":
      return { ...s, plan: ev.plan, phase: "finding" };
    case "sources":
      return { ...s, sources: ev.sources, phase: "writing" };
    case "text":
      return { ...s, text: s.text + ev.text };
    case "final":
      return { ...s, answer: ev.answer, note: ev.note || null, briefingId: ev.briefing_id || s.briefingId,
        cached: !!ev.cached, phase: "done" };
    case "error":
      return { ...s, error: ev.message, phase: "error" };
    default:
      return s;
  }
}

function App() {
  const [meta, setMeta] = useState<Meta | null>(null);
  const [names, setNames] = useState<Record<string, string>>({});
  const [question, setQuestion] = useState(() => new URLSearchParams(location.search).get("q") || "");
  const [sourcesOnly, setSourcesOnly] = useState(false);
  const [detailed, setDetailed] = useState(false);
  const [s, setS] = useState<State>(EMPTY);
  const abort = useRef<AbortController | null>(null);
  const resultRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getMeta().then(setMeta).catch(() => setMeta(null));
    getCouncils()
      .then((d) => setNames(Object.fromEntries(d.councils.map((c) => [c.gss, c.name]))))
      .catch(() => undefined);
    const shared = location.pathname.match(/^\/b\/([\w-]+)/);
    if (shared) {
      getBriefing(shared[1])
        .then((b) => {
          let st: State = { ...EMPTY, question: b.question, phase: "reading", savedAt: b.at };
          for (const ev of b.events) st = apply(st, ev);
          setS({ ...st, briefingId: b.id });
          setQuestion(b.question);
          setTitle(b.question);
        })
        .catch((e: Error) => setS({ ...EMPTY, phase: "error", error: e.message }));
    }
  }, []);

  async function run(q: string) {
    if (q.trim().length < 3) return;
    abort.current?.abort();
    const ctrl = new AbortController();
    abort.current = ctrl;
    let st: State = { ...EMPTY, question: q, phase: "reading" };
    setS(st);
    setTitle(q);
    if (location.pathname !== "/") history.replaceState(null, "", "/");
    requestAnimationFrame(() => resultRef.current?.focus());
    try {
      await ask({ question: q, mode: detailed ? "comprehensive" : "summary", sources_only: sourcesOnly }, (ev) => {
        st = apply(st, ev);
        setS(st);
      }, ctrl.signal);
    } catch (e) {
      if ((e as Error).name !== "AbortError") setS({ ...st, phase: "error", error: (e as Error).message });
    }
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    run(question);
  }

  const t = meta?.totals;
  const busy = ["reading", "finding", "writing"].includes(s.phase);
  const shareUrl = s.briefingId ? `${location.origin}/b/${s.briefingId}` : null;

  return (
    <>
      <h1>What has your council decided?</h1>
      <p className="lede">
        Ask about anything councils across the UK have discussed, decided or voted on at full council and cabinet.
        Every point in the briefing cites the council's own minutes.
      </p>
      <form className="ask-form" onSubmit={submit}>
        <label htmlFor="question" className="visually-hidden">
          Your question
        </label>
        <textarea id="question" value={question} maxLength={500} onChange={(e) => setQuestion(e.target.value)}
          placeholder="For example: what have councils decided about weekly bin collections?"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              run(question);
            }
          }} />
        <div className="ask-options">
          <button className="button" type="submit" disabled={busy || question.trim().length < 3}>
            {busy ? "Working" : "Ask"}
          </button>
          <label>
            <input type="checkbox" checked={detailed} onChange={(e) => setDetailed(e.target.checked)} /> Detailed briefing
          </label>
          <label>
            <input type="checkbox" checked={sourcesOnly} onChange={(e) => setSourcesOnly(e.target.checked)} /> Sources only
          </label>
        </div>
      </form>
      {t && (
        <p className="coverage">
          {number(t.loaded)} councils · {number(t.meetings)} meetings · {number(t.named_votes)} named votes · since{" "}
          {monthYear(meta?.start)}
          {meta?.last_update && <> · updated {longDate(meta.last_update.finished)}</>}.{" "}
          <a href="/councils">Which councils are covered</a>
        </p>
      )}

      <div ref={resultRef} tabIndex={-1} aria-live="polite" aria-busy={busy}>
        {s.phase === "idle" && meta && (
          <>
            <h2 className="minute-heading">Questions to try</h2>
            <ol className="agenda">
              {meta.examples.map((q) => (
                <li key={q}>
                  <button type="button" onClick={() => { setQuestion(q); run(q); }}>
                    {q}
                  </button>
                </li>
              ))}
            </ol>
          </>
        )}
        {s.phase !== "idle" && (
          <article className="briefing">
            <div className="briefing-head">
              <span>
                <strong>Briefing</strong> · <em>{s.question}</em>
              </span>
              <span>{longDate(s.savedAt || new Date().toISOString())}</span>
            </div>
            {s.plan && <PlanChips plan={s.plan} meta={meta} councilNames={names} />}
            {busy && (
              <p className="progress">
                {s.phase === "reading" ? "Reading the question" : s.phase === "finding" ? "Finding the minutes" : "Writing the briefing"}
              </p>
            )}
            {s.answer ? (
              <BriefingText segments={s.answer.segments} />
            ) : (
              s.text && <BriefingText text={s.text} />
            )}
            {s.note && <p className="notice info">{s.note}</p>}
            {s.error && <p className="notice">{s.error}</p>}
            {s.answer && !s.answer.no_records && (
              <>
                {(s.answer.unsupported_segments || 0) > 0 && (
                  <p className="notice">
                    Text <span className="unsupported">marked like this</span> isn't supported by a cited source. Treat it with
                    care, and check the minutes.
                  </p>
                )}
                {(s.answer.loaded_words || 0) > 0 && (
                  <p className="notice">
                    {s.answer.loaded_words === 1 ? "One word" : `${s.answer.loaded_words} words`} in the briefing's own voice
                    may be loaded rather than neutral. Briefings are meant to report what the minutes record, in neutral words.
                  </p>
                )}
                <p className="small">
                  Minutes are summaries written by council officers, not word-for-word records. Briefings are written by an AI
                  model (Claude) from the minutes shown below, and checked automatically against them; they can still be
                  wrong. <a href="/methodology">How briefings are made</a>.
                </p>
                {shareUrl && (
                  <p className="small">
                    Link to this briefing: <a href={shareUrl}>{shareUrl}</a>
                    {" · "}
                    <a href={`/corrections?page=${encodeURIComponent(shareUrl)}`}>Report a problem with it</a>
                  </p>
                )}
              </>
            )}
          </article>
        )}
        <Sources sources={s.sources} />
      </div>
    </>
  );
}

markNav();
createRoot(document.getElementById("app")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
