/** Statements under the right of reply (decision 22; the impartiality policy, section 7.2), shown beside the item
 * they are about and on the council's page. Each is headed "Statement from [name], [date]", set apart from the
 * site's own text, and followed by the words that say it is its author's, not the site's. Never part of the record. */
import { useEffect, useState } from "react";
import { getStatements, type Statement } from "../api";
import { longDate } from "../format";

export const NOT_ENDORSED = "In their own words. Not checked or endorsed by Where Councils Stand.";

/** A statement's link as it may be shown: an http or https address and nothing else (as Where MPs Stand). The
 * service checks it when the statement is sent; it is checked again here, where it becomes a link. */
export const safeLink = (link: string | null | undefined) =>
  link && /^https?:\/\/[^\s"'<>]+$/i.test(link) ? link : null;

export function StatementCard({ s, level = 2, here }: { s: Statement; level?: 2 | 3; here?: string }) {
  const H = level === 2 ? "h2" : "h3";
  const id = `statement-${s.id}`;
  const link = safeLink(s.link);
  return (
    <article className="statement" aria-labelledby={id}>
      <H id={id} className="statement-head">
        Statement from {s.name}, {longDate(s.shown_on)}
      </H>
      <p className="statement-role">{s.role}</p>
      {here !== undefined && s.page !== here && (
        <p className="statement-about">
          About: <a href={s.page}>{s.about || s.page}</a>
        </p>
      )}
      <div className="statement-text">
        {s.text
          .split(/\n\s*\n/)
          .filter((p) => p.trim())
          .map((p, i) => (
            <p key={i}>{p.trim()}</p>
          ))}
      </div>
      {link && (
        <p className="statement-link">
          <a href={link} rel="nofollow ugc">
            The record they point to
          </a>
        </p>
      )}
      <p className="statement-note">{NOT_ENDORSED}</p>
    </article>
  );
}

/** The statements beside one item (``page``, its path), or on one council's page (``council``), gathered under
 * their own heading there. Nothing is shown while they load or if there are none. */
export function Statements(props: { page: string } | { council: string; here: string }) {
  const [rows, setRows] = useState<Statement[]>([]);
  const key = "page" in props ? props.page : props.council;
  useEffect(() => {
    getStatements("page" in props ? { page: props.page } : { council: props.council })
      .then((d) => setRows(d.statements))
      .catch(() => setRows([]));
  }, [key]);
  if (!rows.length) return null;
  if ("page" in props) return <>{rows.map((s) => <StatementCard key={s.id} s={s} />)}</>;
  return (
    <section className="statements" aria-labelledby="statements-heading">
      <h2 id="statements-heading" className="minute-heading">
        Statements in their own words
      </h2>
      <p className="small">
        From councillors, or people acting for them or the council, about this page or an item on the site.{" "}
        <a href="/named">If you're named on this site</a>.
      </p>
      {rows.map((s) => (
        <StatementCard key={s.id} s={s} level={3} here={props.here} />
      ))}
    </section>
  );
}
