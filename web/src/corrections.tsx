/** Report a problem, or ask for something to be taken down (docs/DECISIONS.md, 9). */
import { StrictMode, useState, type FormEvent } from "react";
import { createRoot } from "react-dom/client";
import "./styles.css";
import { sendReport } from "./api";
import { markNav } from "./format";

function Form() {
  const params = new URLSearchParams(location.search);
  const [kind, setKind] = useState(params.get("kind") || "error");
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
      <p className="notice info">
        Thank you. Your report has been received (reference {sent}). Takedown requests are dealt with first.
      </p>
    );
  return (
    <form className="form-grid" onSubmit={submit}>
      <div className="field">
        <label htmlFor="kind">What is it about?</label>
        <select id="kind" value={kind} onChange={(e) => setKind(e.target.value)}>
          <option value="error">Something is wrong: a vote, a party, a briefing or a page</option>
          <option value="takedown">I'm named and want something removed</option>
          <option value="other">Something else</option>
        </select>
      </div>
      <div className="field">
        <label htmlFor="page">Address of the page or briefing (if there is one)</label>
        <input id="page" value={page} onChange={(e) => setPage(e.target.value)} maxLength={500} />
      </div>
      <div className="field">
        <label htmlFor="message">What's the problem?</label>
        <textarea id="message" required minLength={5} maxLength={5000} rows={6} value={message}
          onChange={(e) => setMessage(e.target.value)} />
      </div>
      <div className="field">
        <label htmlFor="contact">Your email address, if you'd like a reply (optional)</label>
        <input id="contact" type="email" value={contact} onChange={(e) => setContact(e.target.value)} maxLength={300} />
        <span className="muted">Used only to reply, and deleted when the report is dealt with.</span>
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

markNav();
createRoot(document.getElementById("report")!).render(
  <StrictMode>
    <Form />
  </StrictMode>,
);
