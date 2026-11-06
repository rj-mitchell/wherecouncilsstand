# Putting the site on a server

Where Councils Stand runs on the charity's shared server, beside Where MPs Stand and Where Countries Stand, in its
own folder (`/opt/wherecouncilsstand`) with its own container, data, settings and spending caps. Where MPs Stand's web
server (Caddy) is the front door for every site on the server: it answers wherecouncilsstand.com through Cloudflare,
with the same protections as its own site, and passes the visitors to this site's container over a shared Docker
network (`sites`). Updates and backups run on timers, each in a one-off container, as on the other sites. See "Other
sites on this server" in Where MPs Stand's `docs/HOSTING.md`.

## What it needs

About 2 GB of memory while serving (the container is limited to 4 GB, so a runaway update stops itself rather than
slowing the other sites), and roughly 8–10 GB of disk for all 318 councils, judging by the pilot (20 councils: 339 MB
of cached responses and 18 MB of stored meetings), plus the search index. An Anthropic API key for written briefings
(without one, the site shows the sources only).

## Steps

1. **Cloudflare**, for wherecouncilsstand.com (as for wherempsstand.com in Where MPs Stand's `docs/HOSTING.md`,
   "Cloudflare protection"):
   * the holding page is a Cloudflare Worker, `wherecouncilsstand-holding` (in the cio repo, `holding/wherecouncilsstand/`):
     remove its custom domain first (Workers & Pages > wherecouncilsstand-holding > Settings > Domains & Routes);
   * an **A** record for `@` pointing at the server, **Proxied**, and `www` redirected to it by a redirect rule;
   * SSL/TLS **Full (strict)**, and an **origin certificate** for wherecouncilsstand.com (leave its page open).
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
4. **The front door:** make sure `wherecouncilsstand.com=wherecouncilsstand` is in `SITES` in
   `/opt/hansardgpt/deploy/.env`, then paste the origin certificate:
   ```bash
   bash /opt/hansardgpt/deploy/cloudflare.sh site wherecouncilsstand.com
   ```
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

## Running it

Commands are run in `/opt/wherecouncilsstand/deploy`. Any `councils` command runs in a one-off container:
`docker compose run --rm -T app councils <command>`.

* **Updates** run once a day (`councils-update.timer`, 03:17 UTC; `docs/OPERATIONS.md`).
* **New code:** merge it into `main` on GitHub, then `bash /opt/wherecouncilsstand/deploy/update.sh`.
* **Backups:** everything but the state database can be rebuilt. That database (spending, saved briefings,
  reports) is copied every night (`councils-backup.timer`) to `/opt/wherecouncilsstand/deploy/backups`, the last 7 kept,
  and to the charity's Backblaze B2 bucket, the last 60 kept there, beside Where MPs Stand's backups (each site's
  have their own names, and each site deletes only its own old copies). To set up the off-site copy, once, copy the
  bucket and key from Where MPs Stand's settings and check them:
  ```bash
  cd /opt/wherecouncilsstand/deploy
  for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
    sed -i "/^COUNCILS_B2_$k=/d" .env; echo "COUNCILS_B2_$k=$v" >> .env; done
  docker compose run --rm -T app councils offsite                  # "ok": true
  docker compose run --rm -T app councils backup --to /backups     # ends "Off-site copy: stored in ..."
  ```
  To get a backup back from B2: download the newest `councils-state-….sqlite.gz` from the bucket, unzip it, and copy it
  into the data volume as `/data/state.db` with the site stopped.
* **The privacy notice** (`web/privacy.html`) names Cloudflare, which carries the site's visits, and says requests
  are not logged (`councils serve` turns the access log off, and the front door keeps none). Keep it true when
  changing either.

## On your own computer

```bash
cd web && npm ci && npm run build && cd ..
uv sync --extra embed
COUNCILS_ANTHROPIC_API_KEY=... uv run councils serve   # http://127.0.0.1:8000
```
