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
| `councils embed --again` | Start meaning search afresh after the embedding model has changed ("The search index and its embedding model", below) |
| `councils reports list`, `reports show`, `reports close`, `withdraw` | Reports and takedown requests, and withdrawn briefings ("Running the website", below). The names these had before still work: `list-reports`, `close-report` |
| `councils statements list`, `show`, `publish`, `decline`, `update`, `withdraw`, `remove`, `log` | Statements under the right of reply (decision 22; "Running the website", below). The names these had before still work: `list-statements`, `publish-statement`, `decline-statement`, `update-statement`, `withdraw-statement` |
| `councils hide`, `unhide`, `hidden` | Hide a page, with a note in its place, while a concern about it is decided ("Hiding a page", below) |
| `councils waiting` | How many reports and statements are waiting for a decision, how many pages are hidden, and how long the oldest has waited |
| `councils stats`, `weekly-report` | How briefings went: speed, cost, what the checks found ("How briefings went", below) |
| `councils tidy` | The nightly housekeeping, after each backup ("What is deleted, and when", below) |
| `councils backup`, `backup-check`, `offsite`, `restore` | The state database's backups ([`DEPLOY.md`](DEPLOY.md), "Backups"; "The state database", below) |
| `councils evaluate`, `councils eval run`, `eval compare`, `eval replay` | The briefing test set ([`EVALUATION.md`](EVALUATION.md)) |
| `councils optimize` | Compact the search index and delete superseded versions (the update does this itself) |

## Running the website

The website and its API are one service, `councils serve` (FastAPI, in `src/councils/api/`). It serves the built pages
from `web/dist`, reads the same data folder as the update, and keeps its own small database in `data/state.db`:
spending, the answer cache, saved briefings, the record of each briefing, problem reports and statements under the
right of reply. The tables are those of the Where They Stand sites' shared package, wts-core (their names start
`wts_`; "The state database", below).

```bash
cd web && npm ci && npm run build && cd ..          # the pages (Vite, TypeScript, React)
uv sync                            # the service, with the local model for meaning search
COUNCILS_ANTHROPIC_API_KEY=... uv run councils serve   # http://127.0.0.1:8000
```

On the server it runs in a container behind the charity's shared front door (`docs/DEPLOY.md`). `--behind-proxy`
takes each visitor's address from `X-Forwarded-For`, which the front door sets from Cloudflare's header; the
container's port is reachable only over the server's Docker networks, never from outside. The address is turned into
a daily visitor code at once and never stored, and requests are not logged (privacy notice). The code is kept on
the day's spending rows only, to count a visitor's briefings, and is forgotten from them after its day.

**Costs and limits** are in `config/settings.toml`, `[usage]`. Each new briefing is counted against a visitor's daily
allowance (`per_visitor_daily_questions`) and the site's daily and monthly caps (`daily_spend_cap_usd`,
`monthly_spend_cap_usd`). A briefing's cost is known only when it finishes, so while one is being written it counts against the caps at an estimate (`briefing_estimate_usd`), and only a few are written at once (`briefings_at_once`, `briefings_at_once_per_visitor`). Many questions at once therefore can't all pass the daily cap before any is counted. Over a limit, readers still get the sources, which cost nothing. With "Sources only" ticked no briefing is written, but the model still reads the question (a fraction of a penny) while the daily and monthly caps allow it; once a cap is reached the built-in rules read it, which costs nothing. An identical question is
answered from the cache until the data changes. Spending so far:

```bash
docker compose run --rm -T app python -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/state.db').execute(
  'select substr(at, 1, 10) as day, round(sum(cost_usd), 2) from wts_spending group by day order by day desc limit 14')]"
```

**The models' prices** are in the same section, one table for each model (`[usage.models."…"]`). The site will not
start if the model that writes briefings (`[answer] model`) or the one that reads questions (`query_parse_model`)
has no prices of its own there: it says which is missing. So when a model is changed, in `config/settings.toml`
or in the server's `data/settings.local.toml`, add its prices in the same change.

**Reports and takedown requests** are in the same database. Commands are run in `/opt/wherecouncilsstand/deploy`:

```bash
docker compose run --rm -T app councils reports list           # open reports, takedown requests first (--all for every one)
docker compose run --rm -T app councils reports close 12 --note "Checked against the minutes: the party was wrong."   # dealt with; the note is private
docker compose run --rm -T app councils reports close 12 --public-note "A councillor's party on the date was wrong. It is put right."
docker compose run --rm -T app councils reports close 13 --outcome dismissed --note "The page matches the minutes."
docker compose run --rm -T app councils withdraw <id> --reason "It named the wrong council."
docker compose run --rm -T app councils waiting                # what is waiting, and for how long
```

Closing a report deletes the reporter's email address (privacy notice). Withdrawing a saved briefing (the `<id>` in
its address, `/b/<id>`) keeps it in the database, but its address then says it has been withdrawn, with the reason.

**The corrections log** is public, on the corrections page (`/corrections#log`) and at `/api/corrections`: every
withdrawn briefing, with the reason given, and every report closed with `--public-note`, newest first (the
impartiality policy, 7.1: "a public note saying what changed and when"). So write a reason or a public note for
the public: say what was wrong and what was done, and name nobody who reported it, and no one who is not a
councillor. `--note` is private. The log never shows a withdrawn briefing's question, or anything a reporter wrote.
A correction links to the page it was reported on when that is a council's page, a named vote or a briefing still
on the site. A report that needed no change needs no public note.

A report or a statement that nobody decides is not kept for ever: after three months of waiting, a report's contact
address is deleted and a statement is declined with the reason "No decision was made in time; please send it
again." (`councils waiting`, and the family's nightly check, say how long the oldest has waited).

### Hiding a page

Where a concern looks well founded and may take time to decide, the page can be hidden meanwhile, with a note (the
impartiality policy, 7.3; the "If you're named" page promises it):

```bash
docker compose run --rm -T app councils hide /votes/E08000016:5021:71234:0 --note "We are checking a report that the sides of this vote were read the wrong way round."
docker compose run --rm -T app councils hidden                 # what is hidden now, longest first
docker compose run --rm -T app councils unhide /votes/E08000016:5021:71234:0
```

The address is the page's, as a reader would copy it (a full address or a path). The note is shown to readers in
the page's place, after "This page is hidden while a concern about it is decided.", so write it for them. Three
kinds of page can be hidden, and nothing else:

| What is hidden | What a reader sees | What it is left out of meanwhile |
|---|---|---|
| A named vote (`/votes/…`) | The note in place of its page | Its council's list of named votes and the sitemap. It is not given with its agenda item's minutes as a source of a briefing: the minutes themselves, which are the council's words, still are |
| A council's or strategic authority's page (`/councils/…`) | The note in place of its page, and of each of its named votes' pages | The list of councils and the sitemap. Its minutes are left out of search, so of every briefing written meanwhile |
| A saved briefing (`/b/…`) | The note in place of the briefing | It is not replayed to someone who asks the same question: a new one is written |

Statements beside a hidden page are hidden with it. Hiding takes effect at once, and so does showing again. An
answer written before something was hidden is not replayed from the answer cache while anything is hidden.

What hiding does not do: **a briefing saved before the page was hidden still shows the sources it was written
from.** If such a briefing repeats the thing complained of, hide or withdraw it too. A hidden council is still
named, with a link that leads to the note, on the page of a strategic authority it belongs to (and the other way
round), and it still counts in the totals. Hiding is not withdrawal: a withdrawn briefing stays withdrawn.
`councils waiting` counts what is hidden, so nothing is left hidden by oversight.

Reports come in on the policy's routes (decision 22): `error` ("Something is wrong"), `unfair` ("You've been
characterised unfairly"), `takedown` (someone who isn't a councillor: deal with these first) and `other`. Reply within
5 working days, and decide within 20 working days; log the decision and its reasons for the trustees.

**Statements under the right of reply** (decision 22; the impartiality policy, section 7.2) arrive as waiting, from
the form at `/corrections?kind=statement`. Before publishing one, confirm who sent it: write to its address, which
should be the councillor's or council's own (one the council publishes) or the party group's. Check it against the
rules on `/named` (150 words, about the item, nothing defamatory, abusive, about a private individual or another
person's conduct, no appeals for votes, money or support, nothing that campaigns in an election period). Publish it as
written or decline it with reasons; never edit it, except to take out something the rules don't allow, with the
author's agreement.

```bash
docker compose run --rm -T app councils statements list          # waiting and published, newest first (--all for every one)
docker compose run --rm -T app councils statements publish 3 --checked "Reply from the councillor's address on the council's website, 14 November."   # show it, dated today, beside its item and on its council's page
docker compose run --rm -T app councils statements publish 4 --checked "..." --council barnsley   # one about a briefing: on Barnsley's page too
docker compose run --rm -T app councils statements decline 5 --reason "It is about another councillor's conduct."
docker compose run --rm -T app councils statements update 3 --text "The author's new wording, as sent."   # or --text-file, --name, --role, --link
docker compose run --rm -T app councils statements withdraw 3    # at the author's request
docker compose run --rm -T app councils statements remove 3 --reason "It breaks the rules: it appeals for votes."   # the site takes it down, and says why
docker compose run --rm -T app councils statements log 3         # everything decided about it, and when
```

The names these commands had before still work (`list-statements`, `publish-statement`, `decline-statement`,
`update-statement`, `withdraw-statement`). A reports or statements command that changes nothing (no report,
briefing or statement with that number, or one already dealt with) says so and exits 1.

`statements publish` needs `--checked`: a few words on how the sender was confirmed. It is kept in the statement's
log, which only the owner can read, and is never shown on the site. Don't put the sender's email address in it: the
privacy notice promises that address is deleted, and the log is kept. A note that holds an address is refused. A
statement whose page has gone, or is hidden, since it was sent can't be published until the page is shown again.

Change or withdraw a statement only on a request confirmed from its author's address. A statement the site takes
down for breaking the rules is **removed**, with the reason, which is said to its author (it is not in the
corrections log); one its author takes back is withdrawn. A statement's address is kept while it is waiting or
shown, and deleted three months after it is withdrawn, declined or removed (the privacy notice): every statement
command, each new statement, the nightly update and the nightly `councils tidy` do this. Statements are never given to the AI model or
put in the search index, and a search engine is told never to quote one as the site's own words.

When the update has changed the data, the service notices within a request or two: the councils' directory is rebuilt
when the stored meetings change. The search index is opened afresh for each search.

## How briefings went

For every question the site keeps one row in **the record of briefings** (the shared package's; its decision
record 0012): how the question ended (a briefing written, replayed from the cache, no records, sources only, a
limit or a cap reached, an error), how long each step took, what it cost, what the checks found, how the sources
were spread across the groups, and which settings it ran with (a short id; the settings behind each id are kept
once). No row says who asked. The question is kept with it, as the privacy notice says; a failed briefing's
question is removed after 90 days and the whole row after 13 months.

```bash
docker compose run --rm -T app councils stats --since 7d       # or 24h, 4w, a date; --json for the figures
docker compose run --rm -T app councils stats --themes         # also group readers' questions by meaning (slower)
docker compose run --rm -T app councils stats --check          # only what is over its threshold; exits 1 if anything is
```

Each figure is given beside the same figure for the four weeks before. Questions are grouped into themes with the
site's own embedding model, so no question leaves the server; how alike two questions must be to count as one
theme is `[embedding] theme_similarity` in `config/settings.toml` (0.8: a first figure, not yet tried on real
questions. If the weekly report's themes are too many and too small, lower it; if unrelated questions are grouped,
raise it).

**The weekly report** is written every Monday at 06:23 UTC (`councils-weekly-report.timer`, installed by
`deploy/update.sh`) to `/data/reports/` as a page (`2026-W46.md`) and as JSON:

```bash
docker compose run --rm -T app cat /data/reports/2026-W46.md
docker compose run --rm -T app councils weekly-report --week 2026-W45      # write an earlier week's again
```

**Alerts.** The thresholds are in `[alerts]` in `config/settings.toml`, and start empty: nothing alerts on a
guessed number. The first weekly reports print proposed thresholds from that week's figures. Once there are a few
weeks of figures, write the ones you want into `[alerts]` (in the repository, or in the server's
`/data/settings.local.toml`); the names are `p95_full_briefing_ms`, `error_rate`, `check_failure_rate`,
`not_useful_rate` (this site has no "useful or not" buttons, so leave it out) and `daily_cost_usd`. From then on
the weekly report fails when a figure is over its threshold, after saving the report, and the usual alert email is
sent (`OnFailure=alert@…`, as for the update and the backup). A name in `[alerts]` that isn't one of these stops
the report with a message, rather than being ignored.

**The structured log** of briefings is `/data/logs/briefings.jsonl`: one line for each step a briefing reached and
one for how it ended, with the record's id, the step's name, a time in milliseconds and, for a failure, the kind of
error. Never a question, an address or a visitor's code, so the privacy notice's "requests aren't logged" stays
true. It is kept for 14 days and about 48 MB at most (`[logs]`). To follow one failed briefing, find its id in
`councils stats --json` or the record, and look for it in the log.

## What is deleted, and when

`councils tidy` runs every night after the backup (`councils-backup.service`, whether or not the backup worked).
It prints a line for each thing it did:

- rows of the record of briefings older than 13 months, and the question of failed briefings older than 90 days;
- weekly report files older than 13 months;
- visitors' codes on spending rows from before today (the spending itself is kept; the first briefing of each
  day does this too);
- the copy of the database made before the one-off import ("The state database", below), once it is older than
  any backup (60 days);
- statements' confirming addresses three months after a statement was withdrawn, declined or removed, and
  reports and statements nobody decided in three months (above);
- from the table the site kept before the shared package, any earlier day's secret for visitors' codes.

If it fails, the backup's unit fails and the usual alert email is sent.

## The state database

`data/state.db` is the one thing that can't be rebuilt. It is kept by the shared package (wts-core), in tables
whose names start `wts_`: `wts_spending` (each model call's cost), `wts_answer_cache`, `wts_briefings` (saved
briefings), `wts_briefing_log` (the record of each briefing), `wts_reports`, `wts_statements` and
`wts_statement_log`, `wts_hidden`, and `wts_schema` (which changes to the tables have been made).

**The one-off import.** Until November 2026 the site kept its own tables (`usage`, `questions`, `answer_cache`,
`briefings`, `reports`, `statements`, `kv`). The first time the new code starts (the web service, or any command
that opens the database), it:

1. copies the database as it stands to `/data/state.pre-wts-core.<date>.db`;
2. copies every row of the old tables into the new ones, in one transaction: spending (with the daily counts of
   questions the old `questions` table held), the answer cache, saved and withdrawn briefings, reports (a closed
   one becomes "resolved"), statements with their logs;
3. notes that it has done so, and never does it again.

The old tables are left exactly as they were, unread. Nothing needs running by hand. Check afterwards that
`councils reports list --all`, `councils statements list --all` and the spending query above show what they
showed before. Before deploying the move, look at `councils list-statements` and `councils list-reports` on the
old code: a statement that has waited more than three months is declined the first night ("No decision was made
in time; please send it again."), and the contact address of a report open that long is deleted then.

**Going back** to the code as it was before the move, without losing what has come in since: stop the site, write
the old tables again from the new ones, then deploy the old code.

```bash
cd /opt/wherecouncilsstand/deploy
docker compose stop app
docker compose run --rm -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < undo-wts-core.sql
```

`deploy/undo-wts-core.sql` says at its top what the old tables can't hold (a hidden page is shown again; how a
report ended is not kept). The copy made in step 1 is the other way back, to the day of the move exactly.

**Putting a backup back.** With the site stopped:

```bash
docker compose stop app
docker compose run --rm -T app councils restore /backups/councils-state-2026-11-20.sqlite.gz
docker compose up -d app
```

The backup is checked before anything is replaced (that it opens, is this site's, and has the tables), and the
database it replaces is kept beside it. **A backup made before the move** (it has the old tables only) is refused
by `councils restore`. Put it back by hand, and the import runs again when the site starts:

```bash
docker compose stop app
gunzip -c backups/councils-state-2026-11-10.sqlite.gz > /tmp/state.db
docker compose run --rm -T -v /tmp/state.db:/restore.db app sh -c 'cp /data/state.db /data/state.replaced.db && cp /restore.db /data/state.db'
docker compose up -d app
```

## The search index and its embedding model

The index notes which embedding model its vectors were made with (`data/index/wts_index.json`). An index built
before the shared package has no note: it takes one the first time it is opened with the model in the settings,
and carries on. If the model in `[embedding]` is ever changed, vectors of two models are never mixed: search by
meaning is switched off (search by words carries on), the nightly update says so in its summary
(`meaning_search: off … Run councils embed --again`), and nothing is embedded until this has been run:

```bash
docker compose run --rm -T app councils embed --again          # throw every vector away and mark everything to embed
docker compose run --rm -T app councils embed --max-minutes 240     # or leave it to the nightly update
```

## The family's nightly check

The charity's repository checks every site each night (wts-core's decision record 0010). For this site it asks
`/api/health`, `/api/status`, one real question, and `/api/check`, which answers only to the family's check
token: set the same random value as `COUNCILS_CHECK_TOKEN` in `deploy/.env` here and as `FAMILY_CHECK_TOKEN` in
the charity repository's Actions secrets, then `bash deploy/update.sh`. Until it is set, `/api/check` is not
there (404). It gives counts and ages only: reports and statements waiting and for how many working days, pages
hidden, the age of the newest backup and off-site copy, and how the last day's briefings ended. A question asked
with the token is written afresh, not replayed, and is kept apart from readers' in the statistics.

## A newer wts-core

The shared package is installed as the wheel of a tagged release, named by its address in `pyproject.toml`, and
CI's shared workflows are called at the same tag (`.github/workflows/ci.yml`). To take a newer release, read its
`CHANGELOG.md` and `docs/UPGRADING.md`, then in one change: put the new version in `pyproject.toml` (twice in the
address), run `uv lock`, and put the same tag after every `rj-mitchell/wts-core/…@` in `ci.yml`.
`tests/test_dependencies.py` fails if the two differ, and the parity tests (`tests/test_parity.py`,
`tests/golden/`) fail if anything a reader sees has changed. Dependabot leaves both alone. A release that changes
what the model is sent, or how evidence is chosen, needs an evaluation run first ([`EVALUATION.md`](EVALUATION.md)).
