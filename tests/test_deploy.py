"""The server's files (deploy/): the script that updates the site, run here with stand-ins for git, docker and
systemctl that note what they were asked; and the timers' units. Also the import from the old database, and
`councils would-lapse`, on the database as the code before the move left it.

The independent review's fourth finding and the first review's tenth: the one-off import runs on whichever command
first opens the database on the new code, and the timers run commands in the image as it is at that moment. So
nothing is deployed while one of the site's jobs runs, the timers are held meanwhile, and their units are
installed only once the new site is up."""

import os
import shutil
import sqlite3
import stat
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "golden"))
import shared  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
DEPLOY = ROOT / "deploy"
JOBS = ("councils-update", "councils-backup", "councils-backup-check", "councils-weekly-report", "councils-topics")

STAND_IN = """#!/usr/bin/env bash
# a stand-in for {name}: notes what it was asked, and answers as the test says
echo "{name} $*" >> "$CALLS"
case "{name} $*" in
  "systemctl is-active --quiet "*) grep -qx "$3" "$STATE/active-timers" 2>/dev/null; exit $? ;;
  "systemctl is-active "*) if grep -qx "$2" "$STATE/running" 2>/dev/null; then echo activating; else echo inactive; fi; exit 3 ;;
  "docker compose build") [[ -e "$STATE/build-fails" ]] && exit 1; exit 0 ;;
  "docker compose run "*"find /data /backups ! -user 10001 -print -quit"*) exit 1 ;;
  "docker compose exec "*) [[ -e "$STATE/never-answers" ]] && exit 1; exit 0 ;;
esac
exit 0
"""


@pytest.fixture
def server(tmp_path):
    """A stand-in for the server: the repository's deploy folder at its place, a folder for systemd's units, and
    git, docker, systemctl and sleep that only note what they were asked. Gives a function that runs the update
    script and returns how it ended and what was called, in order."""
    site, units, bins, state = (tmp_path / name for name in ("site", "units", "bin", "state"))
    shutil.copytree(DEPLOY, site / "deploy", ignore=shutil.ignore_patterns("backups", ".env"))
    (site / "deploy" / ".env").write_text("COUNCILS_ANTHROPIC_API_KEY=\n")
    for folder in (units, bins, state):
        folder.mkdir()
    for name in ("git", "docker", "systemctl", "sleep"):
        (bins / name).write_text(STAND_IN.replace("{name}", name))
        (bins / name).chmod(0o755)

    def run(active_timers=(), running=(), build_fails=False, never_answers=False):
        (state / "active-timers").write_text("".join(f"{t}\n" for t in active_timers))
        (state / "running").write_text("".join(f"{s}\n" for s in running))
        for flag, on in (("build-fails", build_fails), ("never-answers", never_answers)):
            (state / flag).unlink(missing_ok=True)
            if on:
                (state / flag).touch()
        calls = tmp_path / "calls"
        calls.write_text("")
        env = {**os.environ, "PATH": f"{bins}:{os.environ['PATH']}", "DIR": str(site), "UNITS_DIR": str(units),
               "CALLS": str(calls), "STATE": str(state)}
        done = subprocess.run(["bash", str(site / "deploy" / "update.sh")], env=env, capture_output=True, text=True,
                              check=False)
        return done, calls.read_text().splitlines(), sorted(p.name for p in units.iterdir())

    return run


def place(calls: list[str], starts: str) -> int:
    return next(n for n, call in enumerate(calls) if call.startswith(starts))


TIMERS = tuple(f"{job}.timer" for job in JOBS)


def test_the_timers_are_held_and_their_units_installed_only_once_the_new_site_is_up(server):
    done, calls, units = server(active_timers=TIMERS[:3])            # the weekly report's and topics' timers are new
    assert done.returncode == 0, done.stdout + done.stderr
    assert "✓ Where Councils Stand is running." in done.stdout
    order = [place(calls, what) for what in (
        "systemctl stop councils-update.timer", "docker compose build", "docker compose up -d",
        "docker compose exec", "systemctl daemon-reload", "systemctl enable --now")]
    assert order == sorted(order)
    assert [c for c in calls if c.startswith("systemctl stop")] == [f"systemctl stop {t}" for t in TIMERS[:3]]
    assert calls[place(calls, "systemctl enable --now")] == "systemctl enable --now " + " ".join(TIMERS)
    assert not any(c.startswith("systemctl start") for c in calls)   # enabled anew, not started again as they were
    assert units == sorted(f"{job}.{kind}" for job in JOBS for kind in ("service", "timer"))
    # every unit the repository has is one the script installs
    assert {p.name for p in DEPLOY.glob("councils-*.service")} | {p.name for p in DEPLOY.glob("councils-*.timer")} \
        == set(units)


def test_a_first_install_has_no_timers_to_hold(server):
    done, calls, units = server()
    assert done.returncode == 0 and len(units) == 10
    assert not any(c.startswith(("systemctl stop", "systemctl start")) for c in calls)


def test_nothing_is_deployed_while_one_of_the_sites_jobs_is_running(server):
    done, calls, units = server(active_timers=TIMERS, running=["councils-update.service"])
    assert done.returncode == 1 and "councils-update.service is running" in done.stdout
    assert not any(c.startswith(("docker", "systemctl stop", "systemctl enable")) for c in calls) and units == []


def test_a_build_that_fails_installs_no_units_and_starts_the_timers_again(server):
    done, calls, units = server(active_timers=TIMERS[:3], build_fails=True)
    assert done.returncode != 0 and units == []
    assert not any(c.startswith(("docker compose up", "systemctl enable", "systemctl daemon-reload")) for c in calls)
    assert calls[-1] == "systemctl start " + " ".join(TIMERS[:3])


def test_a_site_that_does_not_answer_installs_no_units_and_starts_the_timers_again(server):
    done, calls, units = server(active_timers=TIMERS[:3], never_answers=True)
    assert done.returncode == 1 and "did not answer" in done.stdout and units == []
    assert calls[-1] == "systemctl start " + " ".join(TIMERS[:3])
    assert not any(c.startswith("systemctl enable") for c in calls)


def test_the_tidy_after_the_backup_has_time_to_finish():
    """It runs as the backup's unit stops (ExecStopPost), so it is the stop timeout that bounds it: systemd's
    default is a minute and a half (the review's sixth finding)."""
    unit = (DEPLOY / "councils-backup.service").read_text()
    assert "ExecStopPost=/usr/bin/docker compose run --rm --no-deps -T app councils tidy" in unit
    assert "TimeoutStopSec=30min" in unit and "TimeoutStartSec=30min" in unit
    assert stat.S_IMODE((DEPLOY / "update.sh").stat().st_mode) & 0o111


def test_the_site_is_limited_to_two_processors_and_four_gigabytes():
    """The server is shared with the charity's other sites: neither a flood of requests nor the nightly update (in
    one-off containers of the same service) may take more than two processors (the audit of November 2026)."""
    compose = (DEPLOY / "docker-compose.yml").read_text()
    assert '    mem_limit: 4g\n    cpus: "2"\n' in compose


# The database as the code before the move left it


def old_database(folder: Path) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(folder / "state.db")
    con.executescript((shared.GOLDEN / "old-state.sql").read_text())
    con.close()
    return folder / "state.db"


def test_a_row_that_would_stop_the_import_does_stop_it_until_it_is_mended(tmp_path):
    """A malformed old row stops the site from starting until it is mended. The import, met with it, copies
    nothing, keeps the copy of the file it made first, and runs once the row is mended."""
    from test_parity import site_settings

    from councils.state import open_state

    path = old_database(tmp_path / "old")
    con = sqlite3.connect(path)
    con.execute("UPDATE statements SET log = 'not json' WHERE id = 2")
    con.commit()
    con.close()
    settings, clock = site_settings(tmp_path / "old"), shared.Clock()
    with pytest.raises(sqlite3.OperationalError, match="malformed JSON"):
        open_state(settings, clock)
    con = sqlite3.connect(path)
    assert con.execute("SELECT count(*) FROM wts_spending").fetchone() == (0,)                   # nothing half copied
    assert con.execute("SELECT count(*) FROM wts_schema WHERE name LIKE 'import:%'").fetchone() == (0,)
    assert con.execute("SELECT count(*) FROM usage").fetchone() == (12,)                         # the old rows as they were
    assert (tmp_path / "old" / "state.pre-wts-core.2026-11-13.db").exists()
    con.execute("UPDATE statements SET log = '[]' WHERE id = 2")                                 # mended
    con.commit()
    con.close()
    db = open_state(settings, clock)
    with db.connect() as con:
        assert con.execute("SELECT count(*) FROM wts_spending").fetchone()[0] == 12
        assert con.execute("SELECT count(*) FROM wts_statements").fetchone()[0] == 7
    # an entry of a log with no time stops it too
    path = old_database(tmp_path / "other")
    con = sqlite3.connect(path)
    con.execute("""UPDATE statements SET log = '[{"action": "received"}]' WHERE id = 6""")
    con.commit()
    con.close()
    with pytest.raises(sqlite3.IntegrityError):
        open_state(site_settings(tmp_path / "other"), clock)


def test_would_lapse_says_what_the_next_tidy_would_reach_and_changes_nothing(tmp_path, monkeypatch):
    """wts-core gives the owner `councils would-lapse`, in this site's words (`cli._lapsing`): each statement and
    report the next tidy would reach. It only reads: what it names is still waiting afterwards."""
    from test_parity import environment
    from typer.testing import CliRunner

    from councils import cli

    path = old_database(tmp_path / "old")
    con = sqlite3.connect(path)
    con.execute("UPDATE statements SET at = '2026-08-13T11:59:59+00:00' WHERE id = 6")
    con.execute("UPDATE reports SET at = '2026-08-01T09:00:00+00:00' WHERE id = 4")
    con.commit()
    con.close()

    environment(monkeypatch, tmp_path / "old")
    monkeypatch.setattr(cli, "CLOCK", shared.Clock())
    said = CliRunner().invoke(cli.app, ["would-lapse"])
    assert (said.exit_code, said.stderr) == (0, ""), said.output
    assert said.stdout.splitlines() == [
        "Statement 6, sent 2026-08-13 (92 days ago), would be declined as undecided.",
        "Report 4, sent 2026-08-01 (104 days ago), would lose its contact address.",
        "They lapse at the next tidy: tonight's, or sooner, when a report or a statement is next sent or a reports "
        "or statements command is next run."]
    con = sqlite3.connect(path)
    assert con.execute("SELECT status FROM wts_statements WHERE id = 6").fetchone() == ("pending",)
    assert con.execute("SELECT contact FROM wts_reports WHERE id = 4").fetchone()[0]
    con.close()
    # asked on the day the statement was sent, twelve days after the report: nothing
    monkeypatch.setattr(cli, "CLOCK", shared.Clock("2026-08-13T11:59:59+00:00"))
    assert CliRunner().invoke(cli.app, ["would-lapse"]).stdout == (
        "Nothing would lapse: no statement has waited, and no report with a contact address has been open, for "
        "more than three months.\n")
