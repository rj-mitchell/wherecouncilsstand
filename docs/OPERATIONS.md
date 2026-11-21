# Operations

How the maintainer runs Where Councils Stand on the server once it is installed: the nightly update, the website
and its spending limits, reports and statements, statistics, deletion, and the state database. Installing the site
and deploying new code are in [`DEPLOY.md`](DEPLOY.md).

Commands are run on the server in `/opt/wherecouncilsstand/deploy`. Any `councils` command runs in a one-off
container: `docker compose run --rm -T app councils <command>`.

## The nightly update

`councils update` brings every council already loaded up to date. `councils-update.timer` runs it every day at
03:17 UTC, when councils' servers are quietest.

### The steps of a run

For every loaded council, 20 at a time and one request at a time to each council's server:

1. The committee list is fetched again if the cached one is more than a week old. A new or renamed full council
   or cabinet is picked up by the rules in `committees.py`.
2. Each committee's meetings since May 2018 are listed again, so new meetings appear.
3. New meetings are fetched, and so are meetings from the last 120 days (`[modgov] refetch_days`), because minutes
   can change or be published late until they are approved at the next meeting. Older meetings come from the cache.
4. Minutes published only as a document are read for meetings older than three weeks, where the council serves
   documents.
5. Named votes and declarations are read again for each council whose stored meetings changed.
6. The search index is updated for each council that changed. Passages whose text is unchanged keep their vectors.
   New and changed passages are embedded for meaning search for up to `--embed-minutes` (60 on the server), and
   the rest on the next run. The new rows are merged into the indices, and index files superseded more than an
   hour ago are deleted. If nothing changed, the index isn't touched.
7. Where MPs Stand's list of current MPs (`https://wherempsstand.com/api/people`) is fetched again, for the MPs
   whose seats overlap each council's page (decision 31), into `data/mps.json`. If that site can't be reached, or
   answers with something that isn't a list of MPs, or with fewer than half as many as the last copy, the last good
   copy is kept (or, before the first good fetch, the one kept with the code, `data_static/mps.json`). The pages
   read the new copy at once; nothing is asked of Where MPs Stand while a page is served.
8. A summary is printed and appended to `data/updates.jsonl`. A run takes about 50 minutes:

   ```json
   {"finished": "2026-10-25T21:05:01", "minutes": 51.7, "councils": 214, "changed": 17, "new_meetings": 23,
    "failed": ["E07000072", "E07000076"], "robots": [], "passages_embedded": 9927, "still_to_embed": 0,
    "index": "merged", "mps": {"mps": 650, "unmatched": []}, "needs_attention": false}
   ```

   `"mps"` gives how many MPs the list had and the seats overlapping a council that no MP on it sits for (a vacant
   seat, or a seat the two records name differently), or, if the list couldn't be had, `"error"` and the date of the
   copy kept (`"kept"`). Neither makes the run need attention.

   It exits with status 1 if `needs_attention` is true: more than a tenth of councils, and more than five, failed.

### Built to keep working

| Risk | What happens |
|---|---|
| A council's server is down, slow or refuses a request | A cached response is used instead. If something needed isn't cached (today's meeting list, a new meeting), that council is left as stored and listed under `failed`, and tried again the next day. |
| A council's meetings keep timing out | After two in a row (`timeouts_in_a_row` in `config/settings.toml`), that council is stopped for the night and nothing is stored for it. |
| Many councils fail at once | More likely a problem on the server (the network, the disk). The run exits 1. |
| A run is interrupted | Each council is written only when its update is complete. The next run carries on, and embedding resumes where it stopped. |
| A council moves full council or cabinet to a new committee | Picked up within a week if its title follows the usual patterns. Otherwise add it to `data_static/committees.csv`. |
| A council relabels a party | Mapped by the rules in `parse/parties.py`, or listed by `scripts/party_labels.py` for a decision. Run `councils parties` after changing either. |
| The vote parser improves | `councils parse` reads every council's stored minutes again (about two minutes), with no downloads. |
| The site is busy while the run rewrites the store, one council at a time | The site keeps what it has made of each council (its page, its named votes and each vote's page) until that council's own files change, or the suppression list does, so a change to one council never makes the others' pages again. The list of councils is built again when any council changes, and while that happens requests are given the list as it was. The sitemaps are kept until the record or what is hidden changes, and so are the home page's latest named votes (or until the suppression list changes), which are made from each council's kept votes. Until 21 November 2026 every change threw away every council's pages, and on 20 November, with a slow rule in `parse/redact.py`, the site stopped answering during the run. |
| Where MPs Stand can't be reached, or answers wrongly | Its list of MPs is kept as last fetched, so the MPs on councils' pages stay as they were; the summary's `"mps"` says why. |

Nothing is ever deleted because a server didn't answer.

### Scheduling and alerts

```bash
systemctl list-timers councils-update.timer       # when it runs next
journalctl -u councils-update.service -n 100      # the last run's output
systemctl start councils-update.service           # run one now
docker compose run --rm -T app tail -n 5 /data/updates.jsonl
```

Every site's update on the shared server takes the same lock (`/var/lock/wheretheystand-update.lock`) and waits
for it, so only one runs at a time. A run can therefore start late; while it waits, `systemctl status
councils-update` shows it as "activating".

`councils index` takes the same lock itself (decision 29), so it never runs beside an update: started while one
runs, it says "Waiting for the server's update lock", and carries on by itself when the update ends (Ctrl-C stops
waiting). The containers see the lock through a read-only mount of the server's `/var/lock` (`docker-compose.yml`).
If the lock file isn't there, as after a restart of the server before any update has run, the command does nothing
and says so; make the file with `touch /var/lock/wheretheystand-update.lock` and run it again.

If the update, the backup or the weekly report fails, the server emails wheretheystanduk@gmail.com with the
result and the last log lines, at most once every six hours (Where MPs Stand's
[`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md), "Email from the
server"). A backup timer that stops running sends no failure of its own, so `councils-backup-check.timer` runs
`councils backup-check` every day at 11:47 UTC. It fails, and so sends the same email, if the last backup or
off-site copy is over two days old or the last off-site copy failed.

### Problems a run reports

- The same councils under `failed`, day after day. Their server is down or refusing requests. `councils list
  --status ok` shows each council's meetings site, to check by hand. A council that has moved to a new address needs
  `data_static/councils.csv` rebuilt (`scripts/build_councils.py`).
- `needs_attention`. Check the network from the server, then the disk (`df -h`), then the log.
- `still_to_embed` keeps growing. Raise `--embed-minutes` in `councils-update.service`, or run `councils embed`
  on its own.
- A council under `robots`. This happens only with `[robots] obey` switched on (it is off, decision 21): the
  council's robots.txt has started to forbid reading it, and nothing was read or changed.
- Seats under `"mps"` `"unmatched"`. A seat is vacant, or Where MPs Stand spells its name differently from the ONS
  lookup: that seat is listed on council pages without a link until it has an MP on the list. A name that differs
  needs a rule in `seat_key` (`src/councils/sisters.py`). After a boundary change, rebuild the seats with
  `scripts/mp_links.py` ([`DATA.md`](DATA.md)).
- A council's meetings suddenly drop to zero. Its committees have probably been renamed. Look at its committee
  list (`zcat /data/raw/modgov/<GSS>/committees.xml.gz`) and add the new titles to `data_static/committees.csv`.

### Adding councils

The update reads only councils already loaded. To add some (a council whose site has started to answer, or new
rows in the registry), load them once by GSS code or name, then run the update so they are indexed:

```bash
flock /var/lock/wheretheystand-update.lock docker compose run --rm -T app \
  councils load E08000025 E10000012 --workers 20 | tee /tmp/load.jsonl
systemctl start councils-update.service
```

Each line of `/tmp/load.jsonl` should have `"error": ""`; run a council that failed again with `councils ingest
<GSS>`. A site that refuses (403, a bot check) is left for a letter ([`outreach/`](../outreach/)), never worked
around. Load strategic authorities after their constituent councils, because their members' parties come from
those councils' records; `--type strategic_authority` loads them all.

### Disk space

The data folder holds the stored meetings (Parquet), the search index, and a cache of every response from councils'
servers, so that each meeting is fetched once. The index cleans up after itself on each update (`councils
optimize` does the same by hand, while the site keeps serving). Cached responses are gzipped, except meeting
documents (PDFs), which barely compress.

Modern.gov responses cached before November 2026 are plain XML, and each is replaced by a gzipped copy when next
fetched. To compress them all at once (it waits for any site's update, and can be stopped and run again):

```bash
flock /var/lock/wheretheystand-update.lock docker compose run --rm -T app sh -c \
  'find /data/raw/modgov -name "*.xml" -print0 | xargs -0 -r -n 200 gzip -6'
```

### Commands

`councils --help` lists every command. The ones used in running the site:

| Command | What it does |
|---|---|
| `councils update [councils]` | The nightly update, for every loaded council or the ones named |
| `councils load` | Load councils not yet in the store (`--resume` carries on a first load) |
| `councils parse` | Read votes and declarations again from stored minutes (after parser changes) |
| `councils parties` | Map stored party labels again (after `parse/parties.py` or `data_static/parties.csv` change) |
| `councils index` | Rebuild the search index for all councils, keeping the vectors of unchanged passages. Waits for the server's update lock |
| `councils embed` | Embed passages not yet embedded (`--again` after a change of embedding model). Waits for the server's update lock, as `councils index` does |
| `councils optimize` | Compact the search index and delete superseded files |
| `councils reports`, `councils withdraw` | Reports and takedown requests, and withdrawn briefings |
| `councils statements` | Statements under the right of reply |
| `councils hide`, `unhide`, `hidden` | Hide a page while a concern about it is decided |
| `councils suppress add`, `suppress list` | Remove a name or phrase the automatic rules missed (the suppression list) |
| `councils waiting`, `would-lapse` | What is waiting for a decision, and what the next tidy would lapse |
| `councils stats`, `weekly-report`, `propose-questions` | How briefings went, and test questions proposed from readers' own |
| `councils tidy` | The nightly deletion, after each backup |
| `councils backup`, `backup-check`, `offsite`, `restore` | The state database's backups |
| `councils evaluate`, `councils eval` | The briefing test set ([`EVALUATION.md`](EVALUATION.md)) |

`list-reports`, `close-report`, `list-statements`, `publish-statement`, `decline-statement`, `update-statement` and
`withdraw-statement` are older names that still work; each first says, on standard error, what it is called now.

## Running the website

The website and its API are one service, `councils serve` (FastAPI, in `src/councils/api/`). It serves the built
pages from `web/dist`, reads the same data folder as the update, and keeps its own small database,
`data/state.db` ("The state database", below). When the update changes the data, the service notices within a
request or two.

On the server it runs in a container behind the charity's shared front door ([`DEPLOY.md`](DEPLOY.md)).
`--behind-proxy` takes each visitor's address from `X-Forwarded-For`, which the front door sets from Cloudflare's
header; the container's port is reachable only over the server's Docker networks. The address is turned at once
into a daily visitor code and never stored, and requests are not logged. The code is kept on that day's spending
rows only, to count a visitor's briefings. After its day, a spending row keeps its day, model, token counts and
cost, and nothing that says who it was for or at what time.

### Share cards of saved briefings

A saved briefing with a written answer has its own link preview, `/b/<id>/card.png` (decision 34): drawn the first
time it is asked for, with no AI, by `src/councils/cards.py`, and kept as `data/cards/<id>.v<card version>.r<rules
version>.png` (about 60 KB each). A card is never drawn for a briefing that is missing, withdrawn, hidden while a
concern is decided, or has no written answer, and an existing card is not served for one. The folder holds nothing
that is not in the saved briefing itself and is not backed up: deleting it (`docker compose exec app rm -rf
/data/cards`) loses nothing, and each card is drawn again when next asked for. A change to what a card shows raises
`CARD_VERSION`, so cards are drawn afresh; the old files can then be deleted the same way.

### Costs and limits

Costs and limits are in `config/settings.toml`, `[usage]`. Each new briefing counts against a visitor's daily
allowance (`per_visitor_daily_questions`) and the site's daily and monthly caps (`daily_spend_cap_usd`,
`monthly_spend_cap_usd`). While a briefing is being written it counts at an estimate (`briefing_estimate_usd`),
and only a few are written at once (`briefings_at_once`, `briefings_at_once_per_visitor`), so a burst of questions
can't all pass the daily cap before any is counted. Over a limit, readers still get the sources, which cost
nothing. A visitor may have 8 briefings written a day. A question the model reading it finds plainly not about
anything councils discuss, decide or vote on (a request for a poem, say) is answered "No records found." without a
search or a briefing, so it costs only that reading. With "Sources only" ticked, no briefing is written, but the model still reads the question (a fraction of
a penny) while the caps allow; after that, built-in rules read it. An identical question is answered from the cache
for up to a week, or until the data changes.

Spending for the last 14 days:

```bash
docker compose run --rm -T app python -c "import sqlite3; [print(*r) for r in sqlite3.connect('/data/state.db').execute(
  'select substr(at, 1, 10) as day, round(sum(cost_usd), 2) from wts_spending group by day order by day desc limit 14')]"
```

Each model the site calls has its own table of prices (`[usage.models."…"]`): the one that writes briefings
(`[answer] model`) and the one that reads questions (`query_parse_model`). The site will not start if either has no
prices, and says which is missing, because a model costed at another's prices would undercount spending.

To try another model on the server without changing the repository, put its name and its prices in
`/data/settings.local.toml`. A table there adds to the repository's, so only the new model's is needed:

```toml
[answer]
model = "the-new-model"

[usage.models."the-new-model"]
price_input_per_mtok = 0.0        # from the provider's price list, US dollars per million tokens
price_output_per_mtok = 0.0
price_cache_read_per_mtok = 0.0
```

Then restart with `docker compose up -d app`. If the table is missing, the site does not start and `docker compose
logs app` says "no price for the-new-model".

### Reports and the corrections log

Reports come in through the site's form on four routes (decision 22): `error` ("Something is wrong"), `unfair`
("You've been characterised unfairly"), `takedown` (from someone who isn't a councillor: deal with these first) and
`other`. Reply within 5 working days and decide within 20, and log the decision and its reasons for the trustees.

```bash
docker compose run --rm -T app councils reports list           # open reports, takedown requests first (--all for every one)
docker compose run --rm -T app councils reports close 12 --note "Checked against the minutes: the party was wrong."   # private note
docker compose run --rm -T app councils reports close 12 --public-note "A councillor's party on the date was wrong. It is put right."
docker compose run --rm -T app councils reports close 13 --outcome dismissed --note "The page matches the minutes."
docker compose run --rm -T app councils withdraw <id> --reason "It named the wrong council."
docker compose run --rm -T app councils waiting                # what is waiting, and for how long
```

Closing a report deletes the reporter's email address. Withdrawing a saved briefing (the `<id>` in its address,
`/b/<id>`) keeps it in the database, but its address then says it has been withdrawn, with the reason. Some
briefings saved before 16 November 2026 have an id that begins with "-", which the command line would read as an
option; write `--` before such an id, after the options:

```bash
docker compose run --rm -T app councils withdraw --reason "It named the wrong council." -- -vPeHLp1u54
```

The corrections log is public, on the corrections page (`/corrections#log`) and at `/api/corrections`: every
withdrawn briefing with its reason, and every report closed with `--public-note`, newest first. So write reasons and
public notes for the public: say what was wrong and what was done, and name neither the reporter nor anyone who
isn't a councillor. The log never shows a withdrawn briefing's question, anything a reporter wrote, or which page a
report was about, so say in the public note which council's page or which vote was put right where readers should
know. A report that needed no change needs no public note.

A report or statement that nobody decides lapses after three months: the report's contact address is deleted, and
the statement is declined with the reason "No decision was made in time; please send it again." `councils waiting`
and the family's nightly check say how long the oldest has waited, and `councils would-lapse` lists what the next
tidy would lapse, without changing anything.

### Statements under the right of reply

Statements (decision 22) arrive as waiting, from the form at `/corrections?kind=statement`. Before publishing one,
confirm who sent it: write to its address, which should be the councillor's or council's own (one the council
publishes) or the party group's. Check it against the rules on `/named` (150 words, about the item, nothing
defamatory or abusive, nothing about a private individual or another person's conduct, no appeals for votes, money
or support, and no campaigning in an election period). Publish it as written or decline it with reasons. Never edit
it, except to take out something the rules don't allow, with the author's agreement.

```bash
docker compose run --rm -T app councils statements list          # waiting and published, newest first (--all for every one)
docker compose run --rm -T app councils statements publish 3 --checked "Reply from the councillor's address on the council's website, 14 November."
docker compose run --rm -T app councils statements publish 4 --checked "..." --council barnsley   # one about a briefing: on Barnsley's page too
docker compose run --rm -T app councils statements decline 5 --reason "It is about another councillor's conduct."
docker compose run --rm -T app councils statements update 3 --text "The author's new wording, as sent."   # or --text-file, --name, --role, --link
docker compose run --rm -T app councils statements withdraw 3    # at the author's request
docker compose run --rm -T app councils statements remove 3 --reason "It breaks the rules: it appeals for votes."
docker compose run --rm -T app councils statements log 3         # everything decided about it, and when
```

`--checked` is a few words on how the sender was confirmed. It is kept in the statement's log, which only the owner
can read. Don't put the sender's email address in it: a note that holds an address is refused. A statement whose
page has gone, or is hidden, can't be published until the page is shown again. Change or withdraw a statement only
on a request confirmed from its author's address. A statement the site takes down for breaking the rules is
removed, and the reason is given to its author; it is not in the corrections log. A reports or statements command
that changes nothing (no such number, or already dealt with) says so and exits 1.

A statement's address is kept while it is waiting or shown, and deleted three months after it is withdrawn,
declined or removed, as the privacy notice says. Statements are never given to the AI model or put in the search
index, and search engines are told not to quote them.

### Hiding a page

Where a concern looks well founded and may take time to decide, the page can be hidden meanwhile, with a note
(impartiality policy, section 7.3):

```bash
docker compose run --rm -T app councils hide /votes/E08000016:5021:71234:0 --note "We are checking a report that the sides of this vote were read the wrong way round."
docker compose run --rm -T app councils hidden                 # what is hidden now, longest first
docker compose run --rm -T app councils unhide /votes/E08000016:5021:71234:0
```

The address is the page's, as a reader would copy it (a full address or a path). Readers see "This page is hidden
while a concern about it is decided." and the note, so write the note for them. Hiding and showing again take
effect at once. Three kinds of page can be hidden:

| What is hidden | What a reader sees | What it is left out of meanwhile |
|---|---|---|
| A named vote (`/votes/…`) | The note in place of its page | Its council's list of named votes and the sitemap. The vote is not given as a source of briefings, though the minutes it comes from still are |
| A council's or strategic authority's page (`/councils/…`) | The note in place of its page and each of its named votes' pages | The list of councils and the sitemap. Its minutes are left out of search, and so of every briefing written meanwhile |
| A saved briefing (`/b/…`) | The note in place of the briefing | The answer cache: someone who asks the same question gets a briefing written afresh |

Statements beside a hidden page are hidden with it. A saved briefing that has a hidden council's minutes or a
hidden vote among its sources shows that page's note in its place until the page is shown again. A hidden council
is still named, with a link that leads to the note, on the pages of strategic authorities it belongs to, and it
still counts in the totals. Hiding is not withdrawal: a withdrawn briefing stays withdrawn. `councils waiting`
counts what is hidden, so nothing is left hidden by oversight.

### Removing a name the rules missed

Names of people who aren't councillors are removed by rules (`src/councils/parse/redact.py`), and the rules miss
some. When a takedown request names one still shown, or you find one, put it on the suppression list:

```bash
docker compose run --rm -T app councils suppress add "North Somerset" "Lucy Byrne" --note "takedown request 41"
docker compose run --rm -T app councils suppress add E07000216 "Steve Dally" --item E07000216:1234:5678   # in one item only
docker compose run --rm -T app councils suppress list
docker compose run --rm -T app councils index E06000024        # then take it out of the search index (that council only)
```

The council is its GSS code or a unique part of its name. Write the name or phrase as the minutes do (case, spacing
and the kind of apostrophe don't matter; only whole words match). `--item` limits the entry to one agenda item, or
to one meeting: `councils search` shows each passage's item id, and a named vote's id without its last part is its
item's. `--note` is for you and is never shown.

The entry applies at once, without a restart, wherever the minutes are shown or given to the model: the sources of
new briefings, the pages of named votes, and saved and cached briefings (each match becomes "[name removed]"). The
search index still holds the words, so the name can still be searched for and can still bring up the passage, until
the council is indexed again with `councils index <council>`, which the command reminds you of. Run it the same day.
If an update is running, it waits for it to finish ("Scheduling and alerts"), so leave it running.

The list is `/data/suppress.csv` on the server, beside `settings.local.toml`. It is never committed: the repository
is public, and the list is a list of people's names. It is not in the nightly backup of the state database either,
so copy it off the server when you add to it (`scp`), or keep the takedown requests' notes so it can be written
again. Edit it by hand only to remove an entry; the columns are `council,item,text,added,note`.

A name in an agenda item's title is removed like one in its minutes. Declarations of interest are cut down to who
declared, the item and the kind of interest wherever the minutes are searched, shown or given to the model; the
reasons stay only in the store (`declarations` table) and in the council's own minutes.

## Briefing statistics

For every question the site keeps one row in the record of briefings: how it ended (a briefing written, replayed
from the cache, no records, sources only, a limit reached, an error), how long each step took, what it cost, what
the checks found, how the sources were spread across groups, and which settings it ran with. No row says who asked,
and each row keeps only the hour it was asked in. The question is kept only where a briefing was written,
replayed, found no records or failed. A failed briefing's question is removed after 90 days, and every row after
13 months.

```bash
docker compose run --rm -T app councils stats --since 7d       # or 24h, 4w, a date; --json for the figures
docker compose run --rm -T app councils stats --themes         # also group readers' questions by meaning (slower)
docker compose run --rm -T app councils stats --check          # only what is over its threshold; exits 1 if anything is
```

Each figure is shown beside the same figure for the four weeks before. Questions are grouped into themes with the
site's own embedding model, so no question leaves the server. `[embedding] theme_similarity` sets how alike two
questions must be to share a theme (0.8, not yet tried on real questions: lower it if themes are too many and
small, raise it if unrelated questions are grouped).

The weekly report is written every Monday at 06:23 UTC (`councils-weekly-report.timer`) to `/data/reports/`, as a
page (`2026-W46.md`) and as JSON:

```bash
docker compose run --rm -T app cat /data/reports/2026-W46.md
docker compose run --rm -T app councils weekly-report --week 2026-W45      # write an earlier week's again
```

Alert thresholds are in `[alerts]` in `config/settings.toml` and start empty, so nothing alerts on a guessed
number. The first weekly reports propose thresholds from their figures. Once there are a few weeks of figures, set
the ones wanted in `[alerts]` (in the repository, or in `/data/settings.local.toml` on the server):
`p95_full_briefing_ms`, `error_rate`, `check_failure_rate` and `daily_cost_usd` (`not_useful_rate` also exists,
but this site has no "useful or not" buttons). The weekly report then saves itself and fails when a figure is over
its threshold, which sends the alert email. An unknown name in `[alerts]` stops the report with a message.

`councils propose-questions --since 7d` writes a file to `/data/proposed-questions/` with questions from the period
that found no records or whose briefings the checks flagged most, in the shape of `eval/questions.toml`. It never
proposes the question of a briefing that was withdrawn, corrected, reported or hidden, or written from a hidden
council or vote. Read the file, take out anything personal, copy what is worth keeping into `eval/questions.toml` by
hand ([`EVALUATION.md`](EVALUATION.md)), and delete the file: it quotes readers' questions. The nightly tidy deletes
it anyway once its oldest question could be 13 months old.

The structured log of briefings, `/data/logs/briefings.jsonl`, has one line for each step a briefing reached and
one for how it ended: the record's id, the step, a time in milliseconds and, for a failure, the kind of error. It
never holds a question, an address or a visitor's code. It is kept for 14 days and about 48 MB at most (`[logs]`).
To follow a failed briefing, find its id in `councils stats --json` and look for it in the log.

## Deletion schedule

`councils tidy` runs every night after the backup (`councils-backup.service`, whether or not the backup worked).
It prints a line for each thing it does, in this order:

1. rows of the record of briefings older than 13 months, and the question of failed briefings older than 90
   days; weekly report files older than 13 months, and any file of proposed test questions that could hold a
   question that old;
2. visitors' codes on spending rows from before today, with the time of day of each row (the spending itself is
   kept, by its day);
3. every secret for visitors' codes but today's, and cached answers older than `[usage] answer_cache_hours` (a
   week);
4. the copy of the database made at the move onto wts-core, once it is 60 days old, and any copy left unfinished
   for more than a day;
5. statements' confirming addresses three months after a statement was withdrawn, declined or removed, and
   reports and statements nobody decided in three months;
6. until 1 February 2027, the same deletions in the tables the site kept before wts-core; on that day it drops those
   tables ("The move onto wts-core, and going back", below);
7. last, it writes the database out afresh, so that nothing deleted is left in the file's unused space, where
   SQLite would otherwise keep it and every backup would copy it.

If the site was using the file at that moment, the last line says the database was not written out afresh, and it
is tried again the next night. On the second night running the command fails, and the alert email is sent. Any
other failure also fails the backup's unit and sends the alert.

`councils backup` does the deletions of steps 2 and 3 before it copies the database, so a night's backup holds
nothing of the day before that the live file doesn't. It does hold the current day's rows so far, but with no
visitors' codes and no visitor secret (wts-core 0.3.2), for as long as that backup is kept.

## The state database

`data/state.db` is the one thing that can't be rebuilt. It is kept by the shared package, wts-core, in tables whose
names start `wts_`: `wts_spending` (each model call's cost), `wts_answer_cache`, `wts_briefings` (saved
briefings), `wts_briefing_log` (the record of each briefing), `wts_reports`, `wts_statements` and
`wts_statement_log`, `wts_hidden`, and `wts_schema` (which changes to the tables have been made).

It is backed up every night ([`DEPLOY.md`](DEPLOY.md), "Backups").

### Putting a backup back

```bash
docker compose stop app
docker compose run --rm -T app councils restore /backups/councils-state-2026-11-20.sqlite.gz
docker compose up -d app
```

A backup no longer in `backups/` can be downloaded from the B2 bucket first. The backup is checked before anything
is replaced (that it opens, is this site's, and has the tables), and the database it replaces is kept beside it.

`councils restore` refuses a backup made before the move onto wts-core, which has only the old tables. Put one back
by hand, and the import ("The move onto wts-core, and going back", below) runs again when the site starts. A
backup from before 12 November 2026 has no statements table; everything else in it comes across.

```bash
docker compose stop app
gunzip -c backups/councils-state-2026-11-10.sqlite.gz > /tmp/state.db
docker compose run --rm -T -v /tmp/state.db:/restore.db app sh -c 'cp /data/state.db /data/state.replaced.db && cp /restore.db /data/state.db'
docker compose up -d app
```

## The move onto wts-core, and going back

Until November 2026 the site kept its state database in tables of its own (`usage`, `questions`, `answer_cache`,
`briefings`, `reports`, `statements`, `kv`). The code that runs on wts-core copied them into the `wts_` tables
once, the first time it opened the database, after copying the database as it stood to
`/data/state.pre-wts-core.<date>.db` (deleted by the nightly tidy after 60 days). The old tables are left in place
so that the move can be undone. Each night `councils tidy` deletes from them whatever the new tables no longer
hold, and on 1 February 2027 it drops them. Nothing else reads them. After that date, this section matters only for
putting back a backup made before the move ("Putting a backup back", above).

### Going back, and coming forward again

Until 1 February 2027 the site can go back to the code from before the move. That code is no longer in this
repository: it is in the private archived repository `rj-mitchell/wherecouncilsstand_old`, at the last commit
before the move, titled "Why use this rather than a chatbot? (wts-core phase 1b) (#50)". Always run the undo
script first, while the new code is still checked out, because the old code doesn't have it:

```bash
cd /opt/wherecouncilsstand/deploy
docker compose stop app
docker compose run --rm --no-deps -T app python -c "import sqlite3, sys; con = sqlite3.connect('/data/state.db'); con.executescript(sys.stdin.read())" < undo-wts-core.sql
git -C /opt/wherecouncilsstand fetch https://github.com/rj-mitchell/wherecouncilsstand_old main:refs/remotes/archive/main
git -C /opt/wherecouncilsstand checkout "$(git -C /opt/wherecouncilsstand log archive/main -1 --format=%H \
  --fixed-strings --grep='Why use this rather than a chatbot? (wts-core phase 1b) (#50)')"
docker compose up -d --build
# the old code has no tidy and no weekly report: install its own backup unit, and stop the weekly report
cp councils-backup.service /etc/systemd/system/ && systemctl daemon-reload
systemctl disable --now councils-weekly-report.timer
```

`deploy/undo-wts-core.sql` writes the old tables again from the new ones, in one transaction, then empties the
new tables' copies of those rows and removes the import's mark. The old code then has everything, and can run for
as long as needed. What it can't hold is folded in or left behind, as the script's header says: a hidden page is
shown again, how a report ended is not kept, and what the new code has deleted stays deleted (spending of earlier
days comes back exact, but with no visitor's code). The script runs only once, and only on a database that has
been moved.

To come forward again, check out the current code and deploy it as usual. The new code makes the move afresh from
the old tables, with whatever the old code took in meanwhile, and counts nothing twice:

```bash
git -C /opt/wherecouncilsstand checkout main
bash /opt/wherecouncilsstand/deploy/update.sh
```

Run no `councils` command by hand until the new site is up: whatever command first opens the database runs the
import, and anything the old site wrote after that would be left behind in the old tables. If the new site does not
start, `docker compose logs app` says why. A row the new tables could not take (`malformed JSON`, or `NOT NULL
constraint failed`) stops the import with nothing half copied. Mend the row, then start the site again, for
example:

```bash
docker compose run --rm -T app python -c "import sqlite3; con = sqlite3.connect('/data/state.db'); con.execute(\"UPDATE statements SET log = '[]' WHERE id = 2\"); con.commit()"
docker compose up -d app
```

If the old code was started without the undo script, what it wrote went to the old tables only. The new code then
refuses to start and changes nothing; `docker compose logs app` shows "the site's old tables hold rows that are
newer than the import that copied them". With the new code checked out and the site stopped, run one of two
scripts the same way as the undo script above, then `docker compose up -d`:

- `deploy/redo-wts-core.sql` if the old code did run after the move. It forgets the move, so the next start brings
  everything in the old tables across, including what the old code wrote. It discards what the new code wrote
  between the move and the day the old code was started.
- `deploy/undo-wts-core.sql` if the old code never ran after the move (a false alarm, such as the server's clock
  being put back). It loses nothing then, but it would discard anything the old code wrote.

The new code cannot notice a row the old code wrote in the same second as the move, a row with no time (the old
`kv` and `questions` tables keep none), or a change to an existing row (a report closed, a statement decided).

From 1 February 2027 the old tables are gone, and both scripts refuse ("no such table") and change nothing. Going
back then means putting back a backup made before the move, while one is still kept (the off-site bucket keeps 60
nightly copies, about two months), with the old code from the archived repository.

## The search index and its embedding model

The index records which embedding model made its vectors (`data/index/wts_index.json`). If the model in
`[embedding]` is changed, the two models' vectors are never mixed: search by meaning is switched off (search by
words carries on), the nightly update says so in its summary (`meaning_search: off … Run councils embed --again`),
and nothing is embedded until this is run:

```bash
docker compose run --rm -T app councils embed --again              # discard every vector and mark everything to embed
docker compose run --rm -T app councils embed --max-minutes 240    # or leave it to the nightly update
```

## The family's nightly check

The charity's repository checks every Where They Stand site each night. For this site it asks `/api/health`,
`/api/status`, one real question, and `/api/check`, which answers only to the family's check token. To set it up,
put the same random value in `COUNCILS_CHECK_TOKEN` in `deploy/.env` and in `FAMILY_CHECK_TOKEN` in the charity
repository's Actions secrets, then run `bash deploy/update.sh`. Until then `/api/check` answers 404.

`/api/check` gives counts and ages only: reports and statements waiting and for how many working days, pages hidden,
the age of the newest backup and off-site copy, how the last day's briefings ended, and the newest weekly report's
totals. A question asked with the token is written afresh, never replayed, and kept apart from readers' in the
statistics.

## A newer wts-core

wts-core is installed as the wheel of a tagged release, named by its address in `pyproject.toml`, and CI calls
wts-core's shared workflows at the same tag (`.github/workflows/ci.yml`). To take a newer release, read its
`CHANGELOG.md` and `docs/UPGRADING.md`, then in one change: put the new version in `pyproject.toml` (twice in the
address), run `uv lock`, and put the same tag after every `rj-mitchell/wts-core/…@` in `ci.yml`.
`tests/test_dependencies.py` fails if the two differ, and the parity tests (`tests/test_parity.py`,
`tests/golden/`) fail if anything a reader sees has changed. Dependabot leaves both alone. A release that changes
what the model is sent, or how evidence is chosen, needs an evaluation run first ([`EVALUATION.md`](EVALUATION.md)).
