-- Going back to the site's code as it was before the shared package (wts-core), without losing what was sent,
-- saved or spent since. docs/OPERATIONS.md, "The state database", says when and how to run this.
--
-- Since the move, everything in the state database is kept in the package's tables (wts_spending, wts_briefings,
-- wts_answer_cache, wts_reports, wts_statements, wts_statement_log, wts_kv). The site's old tables (kv, usage,
-- questions, answer_cache, briefings, reports, statements) were left exactly as they were on the day of the move,
-- and the old code reads only those. This writes the old tables again from the package's, in one transaction, so
-- the old code finds everything: what it had, and what has come in since.
--
--   docker compose stop app
--   docker compose run --rm -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < undo-wts-core.sql
--
-- What the old tables can't hold is folded into what they can, or left behind: a statement the site removed for
-- breaking the rules is "withdrawn" there (with its reason); a statement that lapsed is "declined"; how a report
-- ended and any note for the corrections page are not kept; an item hidden while a concern is decided is shown
-- again (the old code can hide nothing); the record of each briefing stays in the package's tables, unread. A
-- visitor's code is on the day's spending rows only, as the package forgets it after its day; the old code looks
-- at no other day's. The package's tables are not changed, so the move can be made again later: delete the row
-- 'import:councils-state' from wts_schema first, and empty the wts_ tables named above, or the old rows would be
-- imported twice.
BEGIN IMMEDIATE;

DELETE FROM kv WHERE key LIKE 'visitor_salt:%';
INSERT INTO kv (key, value) SELECT key, value FROM wts_kv WHERE key LIKE 'visitor_salt:%';

DELETE FROM usage;
INSERT INTO usage (at, day, visitor, kind, model, input_tokens, output_tokens, cache_read_tokens, cache_write_tokens,
                   cost_usd)
SELECT at, substr(at, 1, 10), visitor, kind, model, input_tokens, output_tokens, cache_read_tokens,
       cache_write_tokens, cost_usd
FROM wts_spending ORDER BY id;

DELETE FROM questions;
INSERT INTO questions (day, visitor, n)
SELECT substr(at, 1, 10), visitor, count(*) FROM wts_spending
WHERE kind = 'answer' AND visitor IS NOT NULL GROUP BY 1, 2;

DELETE FROM answer_cache;
INSERT INTO answer_cache (key, at, events) SELECT key, created_at, events FROM wts_answer_cache;

DELETE FROM briefings;
INSERT INTO briefings (id, at, question, options, events, withdrawn_at, withdrawn_reason)
SELECT id, created_at, question, options, events, withdrawn_at, withdrawn_reason FROM wts_briefings;

DELETE FROM reports;
INSERT INTO reports (id, at, kind, page, message, contact, closed_at)
SELECT id, at, coalesce(kind, 'other'), coalesce(page, ''), message, coalesce(contact, ''), closed_at
FROM wts_reports;

DELETE FROM statements;
INSERT INTO statements (id, at, page, council, name, role, text, link, email, status, shown_on, ended_at, reason, log)
SELECT s.id, s.at, s.item, s.about, s.name, s.role, s.text, coalesce(s.link, ''), coalesce(s.email, ''),
       CASE s.status WHEN 'removed' THEN 'withdrawn' ELSE s.status END,
       -- the old code shows the date of the words now shown: the later of publishing and the last update
       CASE WHEN s.published_at IS NOT NULL
            THEN substr(max(s.published_at, coalesce(s.updated_at, s.published_at)), 1, 10) END,
       s.closed_at, s.reason,
       coalesce((SELECT json_group_array(json(entry)) FROM (
           SELECT CASE WHEN l.note IS NULL
                       THEN json_object('at', l.at, 'action', CASE l.action WHEN 'removed' THEN 'withdrawn'
                                                                           WHEN 'lapsed' THEN 'declined'
                                                                           ELSE l.action END)
                       ELSE json_object('at', l.at, 'action', CASE l.action WHEN 'removed' THEN 'withdrawn'
                                                                           WHEN 'lapsed' THEN 'declined'
                                                                           ELSE l.action END, 'note', l.note) END
                  AS entry
           FROM wts_statement_log l WHERE l.statement = s.id ORDER BY l.id)), '[]')
FROM wts_statements s;

COMMIT;
