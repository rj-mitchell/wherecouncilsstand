# Deployment

How the maintainer installs Where Councils Stand on the charity's shared server and deploys new code. Running it
day to day is in [`OPERATIONS.md`](OPERATIONS.md).

The site runs on the charity's shared server in London, beside the charity's other sites, in its own folder
(`/opt/wherecouncilsstand`) with its own container, data, settings and spending caps. What the sites on the server
share is described once, in Where MPs Stand's
[`docs/HOSTING.md`](https://github.com/rj-mitchell/wherempsstand/blob/main/docs/HOSTING.md):

| Shared part | Where it is described |
|---|---|
| The front door (Caddy, in Where MPs Stand's checkout at `/opt/hansardgpt`), which answers every domain through Cloudflare and passes visitors to each site's container over the `sites` network | HOSTING.md, "Other sites on this server" |
| Cloudflare: DNS, the proxy, Full (strict) and the origin certificate, the `www` redirect | HOSTING.md, "Cloudflare protection" |
| Email from the server, and the failure alerts the timers send | HOSTING.md, "Email from the server" |
| The charity's Backblaze B2 bucket for off-site backups | HOSTING.md, "Backups" |
| The server-wide update lock, and each site's update time | HOSTING.md, "Other sites on this server" |
| Disk space across the sites | HOSTING.md, "Disk space" |

## Requirements

About 2 GB of memory while serving (the container is limited to 4 GB and two processors, so a runaway update stops
itself, and a flood of requests or the nightly embedding is held back, rather than slowing the other sites), and roughly 10 to 12 GB of disk for the full record (when 213 councils were loaded in
October 2026: 3.3 GB of cached responses, 180 MB of stored meetings and 3.5 GB of search index). An Anthropic API key
for written briefings; without one, the site shows the sources only.

## Installing

1. In Cloudflare, set up wherecouncilsstand.com as for any site on the server (HOSTING.md, "Cloudflare
   protection"): the domain proxied to the server, `www` redirected to it, and an origin certificate.
2. On the server, as root, get the code and fill in the settings:
   ```bash
   git clone https://github.com/rj-mitchell/wherecouncilsstand /opt/wherecouncilsstand
   cd /opt/wherecouncilsstand/deploy
   cp .env.example .env && nano .env    # COUNCILS_ANTHROPIC_API_KEY
   ```
   Spending caps are in `config/settings.toml`, `[usage]`.
3. Start it:
   ```bash
   bash /opt/wherecouncilsstand/deploy/update.sh
   ```
   This builds and starts the site, and installs its timers: the nightly update, the nightly backup (with the
   deletion after it), the daily check of the backups, the weekly report, and the weekly topic briefings (once the
   record is loaded, write the first with `councils topics refresh`: OPERATIONS.md, "Topic briefings").
4. Add the site to the front door: `wherecouncilsstand.com=wherecouncilsstand` in `SITES` in
   `/opt/hansardgpt/deploy/.env`, then paste the origin certificate with
   `bash /opt/hansardgpt/deploy/cloudflare.sh site wherecouncilsstand.com` (HOSTING.md, "Other sites on this
   server").
5. Load the record, in the background, overnight: every council since May 2018, then the keyword index, then four
   hours of meaning search (the nightly update carries on with whatever is left):
   ```bash
   cd /opt/wherecouncilsstand/deploy
   nohup docker compose run --rm -T app sh -c \
     'councils load --workers 20 && councils index && councils embed --max-minutes 240' \
     > /var/log/councils-load.log 2>&1 &
   tail -f /var/log/councils-load.log     # Ctrl-C stops watching, not the load
   ```
   It takes hours, because councils' servers are slow and each is asked one thing at a time. If it stops, run
   `councils load --workers 20 --resume` the same way; councils already loaded are kept.
6. Set up the off-site backups ("Backups", below) and the family's nightly check
   ([`OPERATIONS.md`](OPERATIONS.md), "The family's nightly check").
7. Check: visit the site, ask a question, and run `bash /opt/hansardgpt/deploy/check.sh`, which lists every site
   on the server.

## New code

Merge it into `main` on GitHub, then on the server run:

```bash
bash /opt/wherecouncilsstand/deploy/update.sh
```

It pulls the latest code, holds the site's timers, rebuilds and restarts the site (a few seconds of downtime), checks
that it answers, and only then installs the timers' new units, so that no timer runs a command the running image
doesn't have. It refuses to start while one of the site's jobs is running, and says which: the nightly update (from
03:17 UTC, for some hours), the backup (04:30), the check of the backups (11:47) and the weekly report (Mondays at
06:23).

## Backups

Everything but the state database can be rebuilt from councils' sites. That database (spending, saved briefings,
reports, statements, the record of each briefing) is copied every night by `councils-backup.timer` to
`/opt/wherecouncilsstand/deploy/backups`, where the last 7 are kept, and to the charity's B2 bucket as
`councils-state-….sqlite.gz`, where the last 60 are kept (each site deletes only its own old copies).

To set up the off-site copy, once, copy the bucket and key from Where MPs Stand's settings (its `HANSARD_B2_*`
variables) and check them:

```bash
cd /opt/wherecouncilsstand/deploy
for k in BUCKET KEY_ID APPLICATION_KEY; do v=$(grep "^HANSARD_B2_$k=" /opt/hansardgpt/deploy/.env | cut -d= -f2-); \
  sed -i "/^COUNCILS_B2_$k=/d" .env; echo "COUNCILS_B2_$k=$v" >> .env; done
docker compose run --rm -T app councils offsite                  # "ok": true
docker compose run --rm -T app councils backup --to /backups     # ends "Off-site copy: stored in ..."
```

Putting a backup back is in [`OPERATIONS.md`](OPERATIONS.md), "The state database".

## Measurement

Measurement for Google Ad Grants ([decision 36](DECISIONS.md#36-measurement-for-google-ad-grants-built-and-switched-off);
the charity's `family/MEASUREMENT.md`) is built and off: `[ads] measurement = false` and `tag = ""` in
`config/settings.toml`. Off, the site sends its pages exactly as built, with nothing from Google. Turn it on only once
the charity is registered and its Google Ads account has the conversions set up (`briefing_read`, `source_opened`,
`donate_click`, `report_sent`: this site has no downloads), following the charity's checklist,
`plans/2026-11-21-ad-grants-checklist.md` ("On the day the charity is registered"), in this order:

1. Finish `web/privacy-measurement.html`: the charity number in place of `NNNNNNN`, the date in its last line in place
   of "21 November 2026 (draft, for when measurement is turned on)", and the Google entity the Google Ads account's
   terms name if it is not simply "Google". Read it against the checklist, and merge it. Until it is finished the site
   will not start with measurement on.
2. The front door. On this server Where MPs Stand's Caddy front door sends its own content security policy in place
   of any site's, and it would block the Google tag; this app sends none of its own. Once Where MPs Stand carries
   `MEASURED_SITES` support (its own measurement work, or the charity's `family/front-door-measurement.patch` applied
   to `wherempsstand` and merged, then `cd /opt/hansardgpt/deploy && bash update.sh`), add this site's domain to
   `MEASURED_SITES` in `/opt/hansardgpt/deploy/.env` (space-separated, beside any other site already there, for
   example `MEASURED_SITES="wherelandlordsstand.com wherecouncilsstand.com"`) and run
   `cd /opt/hansardgpt/deploy && bash update.sh` again. Until `MEASURED_SITES` names this site, the front door sends
   what it sends today.
3. Add `COUNCILS_ADS_MEASUREMENT=true` and `COUNCILS_ADS_TAG=AW-…` (the tag's ID from the Google Ads account) to
   `/opt/wherecouncilsstand/deploy/.env`, and run `bash /opt/wherecouncilsstand/deploy/update.sh`, which builds the
   image with the finished notice and starts the site with the switch on.
4. Check in a private window: the banner shows at the top of the page; "Reject" leaves no request to Google (the
   browser's network panel); "Accept" loads the tag, and Google Ads' tag diagnostics see a conversion; "Measurement
   choices" at the foot of a page opens the banner again; `/privacy` is the measurement notice; and
   `curl -sI https://wherecouncilsstand.com/ | grep -i content-security-policy` names
   `https://www.googletagmanager.com`.

To turn it off, remove the two lines from `.env` and run `update.sh`, then take the site out of `MEASURED_SITES` and
run Where MPs Stand's `update.sh`. The pages are again as they were, and readers' stored choices do nothing.

## Privacy on the server

The privacy notice (`web/privacy.html`) names Cloudflare, which carries the site's visits, and says requests are
not logged: `councils serve` turns its access log off, and the front door keeps none. Keep both true when changing
either. While measurement is on, `/privacy` is `web/privacy-measurement.html` instead ("Measurement",
above), which says the same: change the two together.
