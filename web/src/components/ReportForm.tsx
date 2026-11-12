/** The report form, and the form for a statement in your own words (docs/DECISIONS.md, 9 and 22). The routes are the
 * impartiality policy's (section 7.1), named as on every Where They Stand site; the option values are what the service
 * stores, and links such as ?kind=takedown rely on them. */
import { useState, type FormEvent } from "react";
import { sendReport, sendStatement } from "../api";

const MAX_WORDS = 150;
const KINDS = ["error", "unfair", "statement", "takedown", "other"];
const TIMES = "We reply within 5 working days, and decide within 20 working days.";

const HINT: Record<string, string> = {
  error:
    "A fact, a date, a vote, a party, a council's control, a coverage label, a connection between councils or a briefing that is incorrect, or that misstates the minutes.",
  unfair:
    "The record is right, but the site's own words, labels or groupings are unfair: a loaded word, a connection without published evidence, or a grouping that suggests something the minutes don't show.",
  statement:
    "For a councillor, a council or someone acting for them: a short statement, shown beside the item, when the record is right but you see it differently.",
  takedown: "For someone named on the site who isn't a councillor, and wants something removed. Dealt with first.",
  other: "Anything else about the site, such as something hard to use.",
};

const QUESTION: Record<string, string> = {
  error: "What's wrong?",
  unfair: "What's unfair, and why?",
  takedown: "What would you like removed, and why?",
  other: "What's the problem?",
};

export const words = (text: string) => text.split(/\s+/).filter(Boolean).length;

function StatementFields({ page, setPage }: { page: string; setPage: (p: string) => void }) {
  const [name, setName] = useState("");
  const [role, setRole] = useState("");
  const [text, setText] = useState("");
  const [link, setLink] = useState("");
  const [email, setEmail] = useState("");
  const [acting, setActing] = useState(false);
  const [sent, setSent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const n = words(text);
  const over = n > MAX_WORDS;
  const ready = page.trim() && name.trim().length >= 2 && role.trim().length >= 2 && n > 0 && !over && email.trim() && acting;

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await sendStatement({ page, name, role, text, link, email, acting });
      setSent(r.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (sent !== null)
    return (
      <p className="notice info" role="status">
        Thank you. Your statement has been received (reference {sent}). We'll write to you at the address you gave to
        confirm it's you, then publish it as you wrote it or tell you why not. {TIMES}
      </p>
    );
  return (
    <form className="form-grid" onSubmit={submit} aria-describedby="statement-rules">
      <p className="small" id="statement-rules">
        Up to {MAX_WORDS} words, in your own name, about one item on the site. No defamatory or abusive content, nothing
        about a private individual or another person's conduct, and no appeals for votes, money or support.{" "}
        <a href="/named">The rules in full</a>.
      </p>
      <div className="field">
        <label htmlFor="st-page">Address of the page it's about</label>
        <input id="st-page" value={page} onChange={(e) => setPage(e.target.value)} maxLength={500} required
          aria-describedby="st-page-hint" />
        <span className="muted" id="st-page-hint">
          A named vote, a council's page or a briefing on this site: copy it from your browser's address bar.
        </span>
      </div>
      <div className="field">
        <label htmlFor="st-name">Your name, as it should be shown</label>
        <input id="st-name" value={name} onChange={(e) => setName(e.target.value)} minLength={2} maxLength={200} required
          autoComplete="name" />
      </div>
      <div className="field">
        <label htmlFor="st-role">Your role</label>
        <input id="st-role" value={role} onChange={(e) => setRole(e.target.value)} minLength={2} maxLength={200} required
          aria-describedby="st-role-hint" autoComplete="organization-title" />
        <span className="muted" id="st-role-hint">
          Shown under your name: "Councillor, Barnsley Metropolitan Borough Council", say, or "For the council's
          Labour group".
        </span>
      </div>
      <div className="field">
        <label htmlFor="st-text">Your statement</label>
        <textarea id="st-text" required rows={8} value={text} onChange={(e) => setText(e.target.value)}
          aria-describedby="st-text-count" aria-invalid={over || undefined} />
        <span className="muted word-count" id="st-text-count" data-over={over || undefined}>
          {n} of {MAX_WORDS} words{over ? `: ${n - MAX_WORDS} too many` : ""}
        </span>
      </div>
      <div className="field">
        <label htmlFor="st-link">A link to the record it points to (optional)</label>
        <input id="st-link" type="url" value={link} onChange={(e) => setLink(e.target.value)} maxLength={500}
          aria-describedby="st-link-hint" />
        <span className="muted" id="st-link-hint">The council's minutes or a published statement, starting https://</span>
      </div>
      <div className="field">
        <label htmlFor="st-email">Your email address, to confirm it's you</label>
        <input id="st-email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} maxLength={300}
          required autoComplete="email" aria-describedby="st-email-hint" />
        <span className="muted" id="st-email-hint">
          An address at your council is quickest. Never shown. Used only to confirm who you are and to let you update or
          withdraw the statement; deleted three months after it is withdrawn or declined.
        </span>
      </div>
      <div className="ask-options">
        <label>
          <input type="checkbox" checked={acting} onChange={(e) => setActing(e.target.checked)} required /> I'm the
          councillor or council this is about, or I act for them
        </label>
      </div>
      {error && <p className="notice" role="alert">The statement couldn't be sent: {error}</p>}
      <p className="small">{TIMES}</p>
      <p>
        <button className="button" type="submit" disabled={busy || !ready}>
          Send the statement
        </button>
      </p>
    </form>
  );
}

export function ReportForm({ search }: { search: string }) {
  const params = new URLSearchParams(search);
  const asked = params.get("kind") || "error";
  const [kind, setKind] = useState(KINDS.includes(asked) ? asked : "error");
  const [page, setPage] = useState(params.get("page") || "");
  const [message, setMessage] = useState("");
  const [contact, setContact] = useState("");
  const [sent, setSent] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const r = await sendReport({ kind, page, message, contact });
      setSent(r.id);
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (sent !== null)
    return (
      <p className="notice info" role="status">
        Thank you. Your report has been received (reference {sent}). Takedown requests are dealt with first. {TIMES}
      </p>
    );
  const choose = (
    <div className="field">
      <label htmlFor="kind">What is it about?</label>
      {/* the options kept short enough to show whole in the closed box on a phone; the detail is in the hint */}
      <select id="kind" value={kind} onChange={(e) => setKind(e.target.value)} aria-describedby="kind-hint">
        <option value="error">Something is wrong</option>
        <option value="unfair">You've been characterised unfairly</option>
        <option value="statement">Add a statement in your own words</option>
        <option value="takedown">A takedown request</option>
        <option value="other">Something else</option>
      </select>
      <span className="muted" id="kind-hint">
        {HINT[kind]}
      </span>
    </div>
  );
  if (kind === "statement")
    return (
      <div className="form-grid">
        {choose}
        <StatementFields page={page} setPage={setPage} />
      </div>
    );
  return (
    <form className="form-grid" onSubmit={submit}>
      {choose}
      <div className="field">
        <label htmlFor="page">Address of the page or briefing (if there is one)</label>
        <input id="page" value={page} onChange={(e) => setPage(e.target.value)} maxLength={500} />
      </div>
      <div className="field">
        <label htmlFor="message">{QUESTION[kind]}</label>
        <textarea id="message" required minLength={5} maxLength={5000} rows={6} value={message}
          onChange={(e) => setMessage(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="contact">Your email address, if you'd like a reply (optional)</label>
        <input id="contact" type="email" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={300}
          aria-describedby="contact-hint" />
        <span className="muted" id="contact-hint">Used only to reply, and deleted when the report is dealt with.</span>
      </div>
      {error && <p className="notice">The report couldn't be sent: {error}</p>}
      <p>
        <button className="button" type="submit" disabled={busy || message.trim().length < 5}>
          Send
        </button>
      </p>
    </form>
  );
}
