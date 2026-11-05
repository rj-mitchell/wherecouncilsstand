# Keeping the data current

`councils update` brings everything up to date in one run. It is meant to run once a day, on a schedule. This page
explains what it does, how it keeps working when councils' servers misbehave, how to schedule it, and what to do when
it reports a problem.

## What a run does

For every council already loaded, 20 at a time and one request at a time to each council's server:

1. **The committee list** is fetched again if the cached one is more than a week old. A new or renamed full council
   or cabinet is picked up by the rules in `committees.py`.
2. **Each committee's meetings** since May 2018 are listed again, once a day, so new meetings appear.
3. **New meetings are fetched**, and so are **meetings from the last 120 days** (`[modgov] refetch_days`), because
   their minutes can change or be published late until they are approved at the next meeting. Everything older
   comes from the cache, so it costs nothing.
4. **Minutes published only as a document** are read for meetings older than three weeks, where the council serves
   documents.
5. **Named votes and declarations** are read again for each council whose stored meetings changed.
6. **The search index** is rebuilt for each council that changed. Passages whose text is unchanged keep their vectors
   and only have their tags updated (party in control, parties named). New and changed passages are then embedded
   for meaning search, for up to `--embed-minutes`. Anything left is embedded on the next run.
7. **A summary** is printed and appended to `data/updates.jsonl`:

   ```json
   {"finished": "2026-10-25T21:05:01", "minutes": 51.7, "councils": 214, "changed": 17, "new_meetings": 23,
    "failed": ["E07000072", "E07000076"], "passages_embedded": 9927, "still_to_embed": 0, "needs_attention": false}
   ```

   That is the first run, on 25 October 2026. It fetched every meeting from the last 120 days again, so later runs
   take about as long. The two failures were new meetings that timed out on slow servers. Both councils kept what was
   stored and were tried again the next day.

   It exits with status 1 if `needs_attention` is true.

## Built to keep working

| Risk | What happens |
|---|---|
| A council's server is down, slow or refuses a request | A response cached earlier is used instead, and the run carries on. If something it needs isn't cached (a meeting list for today, a new meeting), that council is left exactly as stored and reported under `failed`. It is tried again the next day. |
| A council's meetings keep timing out | After two meetings in a row time out (`timeouts_in_a_row` in `config/settings.toml`), that council is stopped rather than waiting about two minutes on each of its meetings (Epping Forest, November 2026). Nothing is stored for it, and it is tried again the next day; meetings already fetched come from the cache. |
| A server fails for several days | The council keeps its stored meetings. It stays in `failed` until its server answers. |
| Many councils fail at once | More likely a problem on our side (the network, the disk). The run exits 1 (`needs_attention`). |
| A run is interrupted | Each council is written only when its update is complete, so a council is either as it was or fully updated. The next run carries on. Embedding resumes where it stopped. |
| Minutes are corrected after a meeting | Meetings are fetched again for 120 days, and the change flows through to votes and the index. |
| A council moves to a new committee for full council or cabinet | Picked up from the committee list within a week, if its title follows the usual patterns. Otherwise add it to `data_static/committees.csv`. |
| A council relabels a party | The new label is mapped by the rules in `parse/parties.py`, or listed by `scripts/party_labels.py` for learning or a decision. Run `councils parties` after changing either. |
| The vote parser improves | `councils parse` reads every council's stored minutes again (about two minutes), with no downloads. |

Nothing is ever deleted because a server didn't answer.

## Scheduling

On the server (`docs/DEPLOY.md`), `councils-update.timer` runs it once a day, in a one-off container;
`deploy/update.sh` installs it. Commands are run in `/opt/wherecouncilsstand/deploy`:

```bash
systemctl list-timers councils-update.timer       # when it runs next
journalctl -u councils-update.service -n 100      # the last run's output
systemctl start councils-update.service           # run one now
docker compose run --rm -T app tail -n 5 /data/updates.jsonl
```

If a run, or the nightly backup, fails (exits 1 when something needs attention, or stops with an error), the server
emails wheretheystanduk@gmail.com with the result and the run's last log lines, at most once every six hours. That is
set up once for every site on the server (Where They Stand's `docs/HOSTING.md`, "Email from the server").

It runs at about 03:17 UTC. Councils publish minutes during the working day, and their servers are quietest at night.
It is also clear of the other sites' updates on the shared server.

## When it reports a problem

- **One or a few councils under `failed`, day after day.** Their server is down or refusing requests. Check by hand:
  `councils list --status ok` shows the site's address. A council that has moved to a new Modern.gov address needs
  `data_static/councils.csv` updated (`scripts/build_councils.py`).
- **`needs_attention`.** Check the network from the server, then the disk (`df -h`), then the log.
- **`still_to_embed` keeps growing.** Raise `--embed-minutes`, or run `councils embed` on its own.
- **A council's meetings suddenly drop to zero.** Its committees have probably been renamed. Look at its committee
  list (`data/raw/modgov/<GSS>/committees.xml`) and add the new titles to `data_static/committees.csv`.

## Commands

| Command | What it does |
|---|---|
| `councils update` | The daily update, as above |
| `councils update E07000209 barnsley` | The same, for some councils only |
| `councils load --resume` | Load councils not yet in the store (a first load; hours) |
| `councils parse` | Read votes and declarations again from stored minutes (after parser changes) |
| `councils parties` | Map stored party labels again (after `parse/parties.py` or `data_static/parties.csv` change) |
| `councils index` | Rebuild the search index for all councils (keeps vectors of unchanged passages) |
| `councils embed` | Embed passages not yet embedded |

# Running the website

The website and its API are one service, `councils serve` (FastAPI, in `src/councils/api/`). It serves the built pages
from `web/dist`, reads the same data folder as the update, and keeps its own small database in `data/state.db`:
spending, the answer cache, saved briefings and problem reports.

```bash
cd web && npm ci && npm run build && cd ..          # the pages (Vite, TypeScript, React)
uv sync --extra embed                               # the service, with the local model for meaning search
COUNCILS_ANTHROPIC_API_KEY=... uv run councils serve   # http://127.0.0.1:8000
```

On the server it runs in a container behind the charity's shared front door (`docs/DEPLOY.md`). `--behind-proxy`
takes each visitor's address from `X-Forwarded-For`, which the front door sets from Cloudflare's header; the
container's port is reachable only over the server's Docker networks, never from outside. The address is turned into
a daily visitor code at once and never stored, and requests are not logged (privacy notice).

**Costs and limits** are in `config/settings.toml`, `[usage]`. Each new briefing is counted against a visitor's daily
allowance (`per_visitor_daily_questions`) and the site's daily and monthly caps (`daily_spend_cap_usd`,
`monthly_spend_cap_usd`). Over a limit, readers still get the sources, which cost nothing. An identical question is
answered from the cache until the data changes. Spending so far:

```bash
docker compose run --rm -T app python -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/state.db').execute(
  'select day, round(sum(cost_usd), 2) from usage group by day order by day desc limit 14')]"
```

**Reports and takedown requests** are in the same database:

```bash
docker compose run --rm -T app python -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/state.db').execute(
  'select id, at, kind, page, message from reports where closed_at is null')]"
```

Closing a report deletes the reporter's email address (privacy notice). A saved briefing can be withdrawn with
`StateDB.withdraw_briefing`; its address then says it has been withdrawn.

When the update has changed the data, the service notices within a request or two: the councils' directory is rebuilt
when the stored meetings change. The search index is opened afresh for each search.
