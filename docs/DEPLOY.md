# Putting the site on the server

Where Councils Stand runs on the charity's shared server in London, beside the charity's other sites, in its own
folder (`/opt/wherecouncilsstand`) with its own container, data, settings and spending caps. Everything the sites on
the server share is described once, in Where MPs Stand's
[`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md), the manual for the
server until the family has an operations document of its own:

| Shared part | Where it is described |
|---|---|
| The front door (Caddy, in Where MPs Stand's checkout at `/opt/hansardgpt`, its original name), which answers every domain through Cloudflare and passes visitors to each site's container over the `sites` network | HOSTING.md, "Other sites on this server" |
| Cloudflare: DNS, the proxy, Full (strict) and the origin certificate, the `www` redirect | HOSTING.md, "Cloudflare protection" |
| Email from the server, and the failure alerts the update and backup timers send | HOSTING.md, "Email from the server" |
| The charity's Backblaze B2 bucket for off-site backups | HOSTING.md, "Backups" |
| The server-wide update lock, and each site's update time | HOSTING.md, "Other sites on this server" |
| Disk space across the sites | HOSTING.md, "Disk space" |

This page has only this site's own steps.

## What it needs

About 2 GB of memory while serving (the container is limited to 4 GB, so a runaway update stops itself rather than
slowing the other sites), and roughly 10–12 GB of disk for all 383 councils, judging by the pilot (20 councils:
339 MB of cached responses and 18 MB of stored meetings), plus the search index. An Anthropic API key for written
briefings (without one, the site shows the sources only).

## Steps

1. **Cloudflare**, for wherecouncilsstand.com, as for any site on the server (HOSTING.md, "Cloudflare protection"):
   the domain proxied to the server, `www` redirected to it, and an origin certificate.
2. **Code and settings**, on the server, as root:
   ```bash
   git clone https://github.com/rj-mitchell/wherecouncilsstand /opt/wherecouncilsstand
   cd /opt/wherecouncilsstand/deploy
   cp .env.example .env && nano .env    # COUNCILS_ANTHROPIC_API_KEY
   ```
   Spending caps are in `config/settings.toml`, `[usage]`.
3. **Start it:**
   ```bash
   bash /opt/wherecouncilsstand/deploy/update.sh
   ```
   It builds and starts the site, and installs its update and backup timers. With no data yet, it finds nothing.
4. **The front door:** `wherecouncilsstand.com=wherecouncilsstand` in `SITES` in `/opt/hansardgpt/deploy/.env`, and
   the origin certificate pasted with `bash /opt/hansardgpt/deploy/cloudflare.sh site wherecouncilsstand.com`
   (HOSTING.md, "Other sites on this server").
5. **First load**, in the background, at a quiet time (overnight): every council since May 2018, then the keyword
   index, then four hours of meaning search (the daily update carries on with whatever is left):
   ```bash
   cd /opt/wherecouncilsstand/deploy
   nohup docker compose run --rm -T app sh -c \
     'councils load --workers 20 && councils index && councils embed --max-minutes 240' \
     > /var/log/councils-load.log 2>&1 &
   tail -f /var/log/councils-load.log     # Ctrl-C stops watching, not the load
   ```
   It takes hours: councils' servers are slow, and each is asked one thing at a time. If it stops, run
   `councils load --workers 20 --resume` the same way; councils already loaded are kept.
6. **Check:** visit the site, ask a question, and run `bash /opt/hansardgpt/deploy/check.sh`, which lists every site
   on the server.

The site went live this way in November 2026, replacing a holding page that ran as a Cloudflare Worker.

## Running it

Commands are run in `/opt/wherecouncilsstand/deploy`. Any `councils` command runs in a one-off container:
`docker compose run --rm -T app councils <command>`.

* **Updates** run once a day (`councils-update.timer`, 03:17 UTC; [`OPERATIONS.md`](OPERATIONS.md)).
* **New code:** merge it into `main` on GitHub, then `bash /opt/wherecouncilsstand/deploy/update.sh`.
* **Backups:** everything but the state database can be rebuilt. That database (spending, saved briefings,
  reports) is copied every night (`councils-backup.timer`) to `/opt/wherecouncilsstand/deploy/backups`, the last 7
  kept, and to the charity's B2 bucket as `councils-state-….sqlite.gz`, the last 60 kept there (each site deletes
  only its own old copies). To set up the off-site copy, once, copy the bucket and key from Where MPs Stand's
  settings (its `HANSARD_B2_*` variables) and check them:
  ```bash
  cd /opt/wherecouncilsstand/deploy
  for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
    sed -i "/^COUNCILS_B2_$k=/d" .env; echo "COUNCILS_B2_$k=$v" >> .env; done
  docker compose run --rm -T app councils offsite                  # "ok": true
  docker compose run --rm -T app councils backup --to /backups     # ends "Off-site copy: stored in ..."
  ```
  Every day `councils-backup-check.timer` checks the backups are up to date, and fails (sending the usual alert)
  if the last backup or off-site copy is over two days old ([`OPERATIONS.md`](OPERATIONS.md)).
  To get a backup back: download the newest `councils-state-….sqlite.gz` from the bucket, unzip it, and copy it into
  the data volume as `/data/state.db` with the site stopped.
* **The privacy notice** (`web/privacy.html`) names Cloudflare, which carries the site's visits, and says requests
  are not logged (`councils serve` turns the access log off, and the front door keeps none). Keep it true when
  changing either.

## On your own computer

```bash
cd web && npm ci && npm run build && cd ..
uv sync --extra embed
COUNCILS_ANTHROPIC_API_KEY=... uv run councils serve   # http://127.0.0.1:8000
```
