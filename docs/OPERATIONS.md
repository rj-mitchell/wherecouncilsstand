# Operations

Two things run on the server: the nightly update, which keeps the data current, and the website. This page covers
both. Putting the site on the server is in [`DEPLOY.md`](DEPLOY.md).

## Keeping the data current

`councils update` brings everything up to date in one run. It is meant to run once a day, on a schedule. This section
explains what it does, how it keeps working when councils' servers misbehave, how to schedule it, and what to do when
it reports a problem.

### What a run does

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
6. **The search index** is rewritten for each council that changed. Passages whose text is unchanged keep their
   vectors and only have their tags updated (party in control, parties named). New and changed passages are then
   embedded for meaning search, for up to `--embed-minutes`. Anything left is embedded on the next run. The new
   rows are merged into the keyword and meaning-search indices, and superseded versions of the index files older
   than an hour are deleted (`SearchIndex.refresh`). The indices are built from scratch only the first time, and
   meaning search's again once it has a fifth more vectors than it was trained on. If no council changed and
   nothing was embedded, the index isn't touched. Building from scratch every night, as the site first did, left a
   copy of the old indices on disk each time.
7. **A summary** is printed and appended to `data/updates.jsonl`:

   ```json
   {"finished": "2026-10-25T21:05:01", "minutes": 51.7, "councils": 214, "changed": 17, "new_meetings": 23,
    "failed": ["E07000072", "E07000076"], "passages_embedded": 9927, "still_to_embed": 0, "needs_attention": false}
   ```

   Runs since 6 November 2026 also say what happened to the index: `"index": "merged"`, `"built"` or
   `"unchanged"`.

   That is the first run, on 25 October 2026. It fetched every meeting from the last 120 days again, so later runs
   take about as long. The two failures were new meetings that timed out on slow servers. Both councils kept what was
   stored and were tried again the next day.

   It exits with status 1 if `needs_attention` is true.

### Built to keep working

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

### Scheduling

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
set up once for every site on the server (Where MPs Stand's `docs/HOSTING.md`, "Email from the server").

A backup timer that stops running sends no failure of its own, so every day at 11:47 UTC `councils backup-check`
(`councils-backup-check.timer`) looks at the backups folder, as Where MPs Stand's admin page does. It fails, and so
sends the same email, if the last backup or off-site copy is over two days old or the last off-site copy failed. To
run it by hand: `docker compose run --rm --no-deps -T app councils backup-check --in /backups`.

It runs at about 03:17 UTC. Councils publish minutes during the working day, and their servers are quietest at night.
It is also clear of the other sites' updates on the shared server. In case a job runs long, every site's update takes
the same lock (`/var/lock/wheretheystand-update.lock`) and waits for it, so only one runs at a time. A run can
therefore start late: while it waits, `systemctl status councils-update` shows it as "activating".

### When it reports a problem

- **One or a few councils under `failed`, day after day.** Their server is down or refusing requests. Check by hand:
  `councils list --status ok` shows the site's address. A council that has moved to a new Modern.gov address needs
  `data_static/councils.csv` updated (`scripts/build_councils.py`).
- **`needs_attention`.** Check the network from the server, then the disk (`df -h`), then the log.
- **`still_to_embed` keeps growing.** Raise `--embed-minutes`, or run `councils embed` on its own.
- **A council under `robots` in the summary.** Only with `[robots] obey` switched on (it is off, decision 21): its
  site's robots.txt has started to forbid reading it. Nothing was read or changed.
- **A council's meetings suddenly drop to zero.** Its committees have probably been renamed. Look at its committee
  list (`zcat data/raw/modgov/<GSS>/committees.xml.gz`) and add the new titles to `data_static/committees.csv`.

### Loading the strategic authorities (once)

All 20 strategic authorities (decision 17) are in the registry with status `ok`: the 16 on Modern.gov, and the four
read from their own websites (Tees Valley, Hull and East Yorkshire, Cumbria, and Hampshire and the Solent,
`system=docsite`). Nothing of theirs is stored until they are loaded once. If the 16 are already loaded, load just the four in
step 2: `councils load E47000006 E47000016 SA-CUMBRIA SA-HAMPSHIRE-SOLENT --workers 4` in place of
`--type strategic_authority`. Run on the server, after this change is deployed, in
`/opt/wherecouncilsstand/deploy`. Each command takes the same lock as the nightly update, so they never overlap; if
the nightly run is under way, they wait for it.

```bash
cd /opt/wherecouncilsstand/deploy
# 1. what will be loaded: the 20, each with its meetings site (Lancashire's, Sussex and Brighton's and Cheshire
#    and Warrington's are their councils'; the four on their own websites show their meetings pages)
docker compose run --rm -T app councils list --type strategic_authority --status ok
# 2. the backfill: board, scrutiny and any mayor's decisions since May 2018, members' roles and parties, named votes
flock /var/lock/wheretheystand-update.lock docker compose run --rm -T app \
  councils load --type strategic_authority --workers 20 | tee /tmp/authorities-load.jsonl
# 3. index them now, rather than waiting for 03:17
systemctl start councils-update.service && journalctl -u councils-update.service -n 30
```

- **Time:** about an hour. Each authority is read one request at a time, at least a second apart, all 20 side by
  side, so the longest record sets the pace: Greater Manchester's (nine committees in scope, three of them expired
  scrutiny committees, about 300 meetings, and minutes mostly as documents) at 2 to 25 seconds a meeting on a slow
  server. The four created in 2024–25 take a few minutes each. The four on their own websites take about 5 minutes
  in all (about 150 requests: Tees Valley's 4 pages and about 75 minutes documents, Hull and East Yorkshire's about 30
  pages and 13 documents, Cumbria's 10 and 7, Hampshire and the Solent's 2 and 3; about 20 MB of cache under
  `/data/raw/docsite`). Step 3 is an ordinary nightly run (about 50 minutes).
- **Requests and disk:** about 2,100 meetings and 2,500 requests (the GLA's about 500 of them) in all, with up to a few hundred minutes documents.
  Each meeting's response is 250–350 KB of XML, about 80 KB gzipped: about **150 MB for the cache, 100 MB for
  documents**, and a few MB of Parquet and index. Check with `docker compose run --rm -T app du -sh /data/raw/modgov`
  before and after.
- **What to check:** each line of `/tmp/authorities-load.jsonl` has `"error": ""` and the committees expected
  (`data_static/committees.csv`). For the four on their own websites, expect about 81 meetings for Tees Valley (from
  April 2019), 23 for Hull and East Yorkshire, 7 for Cumbria and 3 for Hampshire and the Solent (6 November 2026; more
  as meetings are held). Their members' councils and parties come from the constituent councils' stored records, so
  load them after the councils (as here, once the councils are loaded); a member matched to no council shows as a
  non-constituent member with no party until the next update reads them again. One that failed is simply run again: `councils ingest E47000001`. Cheshire and Warrington's line should list committees named for it ("Cheshire and Warrington Combined Authority ..."); if it lists none, send its line on: its committees' titles differ from the rule. Then
  the councils page lists them under "Strategic authorities", and `/councils/E47000003` shows West Yorkshire's.
- **After that,** the nightly update reads them like any council. Members' parties come from their home councils'
  stored records, so they are read again each night as the councils' are.

### Loading the 26 CMIS councils (once)

Left out under the earlier robots.txt rule and read again at the owner's request (decision 21, 6 November 2026):
Birmingham, Braintree, Cambridgeshire, Castle Point, Colchester, Derby, Dudley, East Suffolk, Essex, Fylde, Great
Yarmouth, Harborough, Hull, Norfolk, South Derbyshire, South Staffordshire, Walsall, Warrington, Mid Ulster,
Midlothian, North Ayrshire, North Lanarkshire, Perth and Kinross, Renfrewshire, South Lanarkshire and West
Dunbartonshire. Run on the server after this change is deployed:

```bash
cd /opt/wherecouncilsstand/deploy
flock /var/lock/wheretheystand-update.lock docker compose run --rm -T app councils load --workers 26 \
  E08000025 E07000067 E10000003 E07000069 E07000071 E06000015 E08000027 E07000244 E10000012 E07000119 \
  E07000145 E07000131 E06000010 E10000020 E07000039 E07000196 E08000030 E06000007 N09000009 S12000019 \
  S12000021 S12000050 S12000048 S12000038 S12000029 S12000039 | tee /tmp/cmis-load.jsonl
systemctl start councils-update.service && journalctl -u councils-update.service -n 30
```

- **Time:** two to three hours. A CMIS site is read page by page, as a browser would, at least a second apart; a
  trial on 6 November 2026 (Birmingham, Essex and South Lanarkshire, four months each) took 25 to 40 seconds a
  meeting with its minutes. Birmingham's full record, about 175 meetings, sets the pace; all 26 run side by side.
- **What to check:** each line of `/tmp/cmis-load.jsonl` has `"error": ""`. A site that refuses (403, a bot check)
  says so and is left for a letter, not worked around. One that failed is run again on its own:
  `councils ingest E08000025`.

### Disk space

The data folder holds the stored meetings (Parquet), the search index and a cache of every response from councils'
servers, so that each meeting is fetched once. Two things keep it from growing for no reason:

- **The search index cleans up after itself.** Each update merges its new rows into the indices and deletes
  superseded versions of the index files over an hour old. `councils optimize` does the same clean-up by hand,
  while the site keeps serving.
- **The cache is gzipped.** Responses from CMIS and CoINS sites always were. Modern.gov responses have been since
  November 2026, which saves about three quarters of their size. Older Modern.gov responses are plain XML and are
  still read; each is replaced by a gzipped copy when next fetched. Meeting documents (PDFs) are stored as they
  come, because they barely compress.

To compress every older Modern.gov response at once, run this on the server once. It waits for any site's update
to finish, through the same lock the updates take, and `gzip` keeps each file's modification time, which decides
when a response is fetched again:

```bash
cd /opt/wherecouncilsstand/deploy
docker compose run --rm -T app du -sh /data/raw/modgov          # before
flock /var/lock/wheretheystand-update.lock docker compose run --rm -T app sh -c \
  'find /data/raw/modgov -name "*.xml" -print0 | xargs -0 -r -n 200 gzip -6'
docker compose run --rm -T app du -sh /data/raw/modgov          # after
```

It can be stopped and run again: files already compressed are skipped.

### Commands

| Command | What it does |
|---|---|
| `councils update` | The daily update, as above |
| `councils update E07000209 barnsley` | The same, for some councils only |
| `councils load --resume` | Load councils not yet in the store (a first load; hours) |
| `councils parse` | Read votes and declarations again from stored minutes (after parser changes) |
| `councils parties` | Map stored party labels again (after `parse/parties.py` or `data_static/parties.csv` change) |
| `councils index` | Rebuild the search index for all councils (keeps vectors of unchanged passages), then delete the superseded files |
| `councils embed` | Embed passages not yet embedded |
| `councils list-reports`, `close-report`, `withdraw` | Reports and takedown requests, and withdrawn briefings ("Running the website", below) |
| `councils optimize` | Compact the search index and delete superseded versions (the update does this itself) |

## Running the website

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
`monthly_spend_cap_usd`). A briefing's cost is known only when it finishes, so while one is being written it counts against the caps at an estimate (`briefing_estimate_usd`), and only a few are written at once (`briefings_at_once`, `briefings_at_once_per_visitor`). Many questions at once therefore can't all pass the daily cap before any is counted. Over a limit, readers still get the sources, which cost nothing. An identical question is
answered from the cache until the data changes. Spending so far:

```bash
docker compose run --rm -T app python -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/state.db').execute(
  'select day, round(sum(cost_usd), 2) from usage group by day order by day desc limit 14')]"
```

**Reports and takedown requests** are in the same database. Commands are run in `/opt/wherecouncilsstand/deploy`:

```bash
docker compose run --rm -T app councils list-reports           # open reports, newest first (--all for every one)
docker compose run --rm -T app councils close-report 12        # mark report 12 dealt with
docker compose run --rm -T app councils withdraw <id> --reason "It named the wrong council."
```

Closing a report deletes the reporter's email address (privacy notice). Withdrawing a saved briefing (the `<id>` in
its address, `/b/<id>`) keeps it in the database, but its address then says it has been withdrawn, with the reason.

When the update has changed the data, the service notices within a request or two: the councils' directory is rebuilt
when the stored meetings change. The search index is opened afresh for each search.
