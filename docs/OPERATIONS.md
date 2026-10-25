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
   {"finished": "...", "minutes": 41.2, "councils": 213, "changed": 37, "new_meetings": 52, "failed": ["E07000243"],
    "passages_embedded": 2210, "still_to_embed": 0, "needs_attention": false}
   ```

   It exits with status 1 if `needs_attention` is true.

## Built to keep working

| Risk | What happens |
|---|---|
| A council's server is down, slow or refuses a request | A response cached earlier is used instead, and the run carries on. If something it needs isn't cached (a meeting list for today, a new meeting), that council is left exactly as stored and reported under `failed`. It is tried again the next day. |
| A server fails for several days | The council keeps its stored meetings. It stays in `failed` until its server answers. |
| Many councils fail at once | More likely a problem on our side (the network, the disk). The run exits 1 (`needs_attention`). |
| A run is interrupted | Each council is written only when its update is complete, so a council is either as it was or fully updated. The next run carries on. Embedding resumes where it stopped. |
| Minutes are corrected after a meeting | Meetings are fetched again for 120 days, and the change flows through to votes and the index. |
| A council moves to a new committee for full council or cabinet | Picked up from the committee list within a week, if its title follows the usual patterns. Otherwise add it to `data_static/committees.csv`. |
| A council relabels a party | The new label is mapped by the rules in `parse/parties.py`, or listed by `scripts/party_labels.py` for learning or a decision. Run `councils parties` after changing either. |
| The vote parser improves | `councils parse` reads every council's stored minutes again (about two minutes), with no downloads. |

Nothing is ever deleted because a server didn't answer.

## Scheduling

With systemd (the units are in `deploy/`):

```bash
sudo cp deploy/councils-update.service deploy/councils-update.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now councils-update.timer
systemctl list-timers councils-update.timer       # when it runs next
journalctl -u councils-update.service -n 100      # the last run's output
tail -n 5 /opt/wherecouncilsstand/data/updates.jsonl
```

It runs at about 03:17 UTC. Councils publish minutes during the working day, and their servers are quietest at night.

Or with cron:

```cron
17 3 * * *  cd /opt/wherecouncilsstand && .venv/bin/councils update >> data/update.log 2>&1
```

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
