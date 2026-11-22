#!/usr/bin/env bash
# Install or update Where Councils Stand on the charity's shared server (whatever has been merged into `main` on
# GitHub). Run on the server, as root:
#   bash /opt/wherecouncilsstand/deploy/update.sh
# It fetches the new code, rebuilds and restarts the site (a few seconds of downtime), refreshes its timers and clears
# out old build files. Where MPs Stand's web server is the front door (docs/DEPLOY.md).
#
# The timers run `councils` commands in whatever image is current, so nothing is deployed while one of the site's
# jobs is running, the timers are held until the new site is up, and their units are installed only after that.
# If anything fails, the held timers are started again.
set -euo pipefail
DIR="${DIR:-/opt/wherecouncilsstand}"
UNITS_DIR="${UNITS_DIR:-/etc/systemd/system}"
JOBS="councils-update councils-backup councils-backup-check councils-weekly-report councils-topics"

echo "==> Fetching the latest version"
self_before=$(sha1sum "$DIR/deploy/update.sh" | cut -d' ' -f1)
git -C "$DIR" pull --ff-only
# bash goes on reading the copy of this script it started with, so a new version only takes effect if run afresh
if [[ -z "${UPDATE_RESTARTED:-}" && "$(sha1sum "$DIR/deploy/update.sh" | cut -d' ' -f1)" != "$self_before" ]]; then
  echo "==> This update script has changed: running the new version"
  UPDATE_RESTARTED=1 exec bash "$DIR/deploy/update.sh"
fi

cd "$DIR/deploy"
[[ -f .env ]] || { echo "No settings yet: cp .env.example .env, fill it in, and run this again (docs/DEPLOY.md)."; exit 1; }

for job in $JOBS; do
  case "$(systemctl is-active "$job.service" 2>/dev/null || true)" in
    active|activating)
      echo "✗ $job.service is running: wait for it to finish and run this again (docs/DEPLOY.md, \"New code\")."
      exit 1 ;;
  esac
done
echo "==> Holding the site's timers until the new site is up"
held=""
for job in $JOBS; do
  if systemctl is-active --quiet "$job.timer" 2>/dev/null; then
    systemctl stop "$job.timer"
    held="$held $job.timer"
  fi
done
release() {
  # whatever went wrong, the timers that were running are running again, on the units already installed
  if [[ -n "$held" ]]; then
    # shellcheck disable=SC2086
    systemctl start $held || true
  fi
}
trap release EXIT

echo "==> Rebuilding the site"
mkdir -p backups
docker network create sites >/dev/null 2>&1 || true  # shared with the charity's other sites on this server
docker compose build
# The site runs as its own user (10001), not root: anything in its data or backups not owned by it is handed over
if docker compose run --rm --no-deps -T --user root --entrypoint sh app -c \
     'find /data /backups ! -user 10001 -print -quit | grep -q .'; then
  echo "==> Handing the site's data to its own user"
  docker compose stop app
  docker compose run --rm --no-deps -T --user root --entrypoint sh app -c \
    'find /data /backups ! -user 10001 -print0 | xargs -0r chown -h 10001:10001'
fi

echo "==> Restarting the site"
docker compose up -d --remove-orphans

echo "==> Clearing out old build files"
docker image prune -f >/dev/null
docker builder prune -f --filter until=72h >/dev/null || true

echo "==> Checking it answers"
answered=""
for _ in $(seq 1 30); do
  if docker compose exec -T app python -c \
       "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health')" >/dev/null 2>&1; then
    answered=yes
    break
  fi
  sleep 3
done
if [[ -z "$answered" ]]; then
  echo "✗ The site did not answer within a minute and a half: see docker compose -f $DIR/deploy/docker-compose.yml logs app"
  echo "  Its timers are as they were. If it says a row of the state database could not be brought across, or that"
  echo "  the old tables hold rows newer than the import, see docs/OPERATIONS.md, \"Going back, and coming forward again\"."
  exit 1
fi

# only now, with the new site up: the timers' units as this version has them
echo "==> Refreshing the update, backup, backup check, weekly report and topic briefing timers"
for job in $JOBS; do
  cp "$job.service" "$job.timer" "$UNITS_DIR/"
done
systemctl daemon-reload
# shellcheck disable=SC2046
systemctl enable --now $(for job in $JOBS; do echo "$job.timer"; done) >/dev/null
held=""

echo "✓ Where Councils Stand is running."
echo "  Next update: $(systemctl show councils-update.timer -p NextElapseUSecRealtime --value)"
