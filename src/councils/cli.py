"""Command line.

    councils list --status ok                 # councils in scope and their Modern.gov sites
    councils ingest barnsley                  # full council and cabinet meetings since the start date
    councils parse barnsley                   # named votes and declarations of interest, from the minutes
    councils load --workers 20 --resume       # every council whose web service answers
    councils pilot-sample                     # the pilot's councils, chosen by a fixed, published rule
    councils pilot                            # ingest and parse every pilot council
    councils report                           # the pilot's measurements (docs/PILOT.md)
    councils index && councils embed          # keyword index, then meaning search (slow; resumable)
    councils backup --to /backups             # copy the state database (scheduled)
    councils restore /backups/councils-state-2026-11-14.sqlite.gz    # put a backup back (stop the site first)
    councils reports list                     # problems and takedown requests sent through the site
    councils reports close 12                 # mark one dealt with (its contact address is deleted)
    councils withdraw <id> --reason "..."     # withdraw a saved briefing (/b/<id>)
    councils statements list                  # statements under the right of reply, waiting and published
    councils statements publish 3 --checked "..."   # show it, once its author is confirmed (decision 22)
    councils hide /votes/<id> --note "..."    # hide an item while a concern is decided; unhide shows it again
    councils suppress add <council> "<name>"  # remove a name or phrase that slipped through (the suppression list)
    councils waiting                          # what is waiting for a decision, and for how long
    councils would-lapse                      # what the next tidy would decline or delete as undecided (changes nothing)
    councils stats --since 7d                 # how briefings went: speed, cost, what the checks found
    councils weekly-report                    # the week's figures saved, and what is over its threshold (scheduled)
    councils tidy                             # the nightly housekeeping (scheduled, after the backup)
    councils eval run                         # the test questions, each briefing written (costs money; has a limit)
    councils topics list                      # the topic briefings, when each was last written, what the last run did
    councils topics refresh                   # write the topic briefings that are due (weekly, scheduled; costs money)
    councils search "bin collections" --control NOC
    councils ask "What have Labour-run councils decided about bin collections since 2023?"
"""

from __future__ import annotations

import json
import logging
from collections.abc import Mapping
from datetime import date
from typing import Any

import typer
from wts_core.cli import (
    BackupCheckWords,
    BackupWords,
    Change,
    OpsWording,
    RepliesCommands,
    RepliesWording,
    RestoreWords,
    eval_commands,
    ops_commands,
    replies_commands,
    replies_tidy,
    stats_commands,
)
from wts_core.observe import config_id
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Replies
from wts_core.state import StateDB
from wts_core.usage import PriceTable

from councils.config import SITE, load_settings
from councils.replies import OWNERS_MESSAGES, hidden_now, open_replies
from councils.state import (
    BACKUP_ALERTS,
    BACKUPS,
    BACKUPS_FOLDER,
    BACKUPS_KEPT_DAYS,
    forget_replays,
    open_archive,
    open_state,
)

# what the commands read the time from: the system's, unless a test stands another in its place
CLOCK: Clock = SYSTEM_CLOCK

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")


@app.command("list")
def list_(status: str = typer.Option(None, help="ok, blocked, unreachable, robots or none"),
          nation: str = typer.Option(None),
          type_: str = typer.Option(None, "--type", help="a kind of council, or strategic_authority")) -> None:
    """Councils (and strategic authorities) in scope, with their meetings site and whether it answered."""
    from councils.registry import councils

    for c in councils().values():
        if (status and c.modgov_status != status) or (nation and c.nation != nation) or (type_ and c.type != type_):
            continue
        typer.echo(f"{c.gss}\t{c.reference}\t{c.type}\t{c.modgov_status}\t{c.name}\t{c.modgov_url}")


@app.command()
def ingest(council: list[str], start: str = typer.Option(None, "--from", help="YYYY-MM-DD")) -> None:
    """Load councils' full council and cabinet meetings into the store."""
    from councils import ingest as ingest_
    from councils.registry import get

    s = load_settings()
    for key in council:
        try:
            res = ingest_.load(s, get(key), date.fromisoformat(start) if start else None)
        except Exception as exc:  # one council's failure mustn't stop the rest (found on the live server)
            typer.echo(json.dumps({"council": key, "error": f"{type(exc).__name__}: {exc}"[:300]}))
            continue
        typer.echo(json.dumps({"gss": res.gss, "meetings": res.meetings, "failed": len(res.failed),
                               "committees": [f"{t} ({k})" for t, k in res.committees.values()],
                               "error": res.error}))


def _parse_one(gss: str) -> dict:
    from councils import extract

    return extract.run(load_settings(), gss)


@app.command()
def parse(council: list[str] = typer.Argument(None, help="GSS codes or names; all loaded councils if none"),
          workers: int = typer.Option(8, help="councils parsed at once")) -> None:
    """Read named votes and declarations of interest from councils' stored minutes."""
    from concurrent.futures import ProcessPoolExecutor

    from councils.registry import get

    s = load_settings()
    codes = [get(k).gss for k in council] if council else \
        sorted(p.stem for p in (s.parquet_dir / "items").glob("*.parquet"))
    with ProcessPoolExecutor(workers) as ex:
        for line in ex.map(_parse_one, codes):
            typer.echo(json.dumps(line))


@app.command()
def parties(council: list[str] = typer.Argument(None, help="GSS codes or names; all loaded councils if none")) -> None:
    """Map stored attendance's party labels to codes again, after parse/parties.py or data_static/parties.csv change."""
    from councils import store
    from councils.parse.parties import normalise
    from councils.registry import get

    s = load_settings()
    stored = sorted(p.stem for p in (s.parquet_dir / "attendance").glob("*.parquet"))
    codes = [get(k).gss for k in council] if council else stored
    for gss in codes:
        rows = store.parquet.read(s.parquet_dir, "attendance", gss)
        for r in rows:
            r["party"] = normalise(r["party_label"], gss)
        store.parquet.write(s.parquet_dir, "attendance", gss, rows)
        typer.echo(json.dumps({"gss": gss, "records": len(rows),
                               "unrecognised": sum(1 for r in rows if not r["party"] and r["party_label"])}))


@app.command()
def load(council: list[str] = typer.Argument(None, help="GSS codes or names: only these (of those in scope)"),
         status: str = typer.Option("ok", help="councils whose web service had this status"),
         nation: str = typer.Option(None), workers: int = typer.Option(20, help="councils loaded at once"),
         type_: str = typer.Option(None, "--type", help="only this kind: strategic_authority for the authorities"),
         resume: bool = typer.Option(False, help="only parse councils already loaded")) -> None:
    """Load and parse every council in scope, printing one line per council as it finishes."""
    from councils import load as load_
    from councils.registry import councils, get

    only = {get(k).gss for k in council or []}
    chosen = [c for c in councils().values() if c.modgov_status == status and (not nation or c.nation == nation)
              and (not type_ or c.type == type_) and (not only or c.gss in only)]
    for line in load_.many(load_settings(), chosen, workers=workers, resume=resume):
        typer.echo(json.dumps(line), nl=True)


@app.command()
def update(council: list[str] = typer.Argument(None, help="GSS codes or names; all loaded councils if none"),
           workers: int = typer.Option(20, help="councils updated at once"),
           embed_minutes: float = typer.Option(60, help="stop embedding after this long; the next run continues"),
           log_file: str = typer.Option("updates.jsonl", help="appended to, in the data folder")) -> None:
    """The daily update: new and recently changed meetings for every loaded council, their votes, the search index
    and meaning search. Prints a line per council and a summary, and appends the summary to the log. Exits 1 if it
    needs attention: more than a tenth of councils (and more than five) failed."""
    import time

    from councils import load as load_
    from councils import sisters
    from councils.index.build import update_index
    from councils.index.lance import get_embedder
    from councils.registry import councils, get
    from councils.sources.modgov import ROBOTS_ERROR

    s = load_settings()
    started = time.time()
    chosen = [get(k) for k in council] if council else list(councils().values())
    lines = []
    for line in load_.update(s, chosen, workers=workers):
        lines.append(line)
        typer.echo(json.dumps(line))
    changed = [ln["gss"] for ln in lines if ln.get("changed")]
    indexed = update_index(s, changed, get_embedder(s), max_seconds=embed_minutes * 60)
    # Where MPs Stand's list of MPs, for the MPs on councils' pages (decision 31): fetched again, or the last good
    # copy kept, never asked for while a page is served
    mps = sisters.refresh_mps(s)
    summary = {"finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "minutes": round((time.time() - started) / 60, 1),
               "councils": len(lines), "changed": len(changed),
               "new_meetings": sum(ln.get("new_meetings", 0) for ln in lines),
               "failed": sorted(ln["gss"] for ln in lines if ln.get("error")),
               # only with [robots] obey on (decision 21): sites whose robots.txt has started to forbid reading
               # (docs/OPERATIONS.md, "Problems a run reports")
               "robots": sorted(ln["gss"] for ln in lines if ln.get("error") == ROBOTS_ERROR), **indexed,
               "mps": mps}
    # needs attention: many councils failing at once means something on our side, not one council's server
    summary["needs_attention"] = not lines or len(summary["failed"]) > max(5, len(lines) // 10)
    # the site's own retention: confirming addresses of statements that ended three months ago (decision 22)
    summary["statement_emails_deleted"] = _replies().forget_old_emails()
    with open(s.data_dir / log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")
    typer.echo(json.dumps(summary))
    if summary["needs_attention"]:
        raise typer.Exit(1)


@app.command()
def evaluate(with_model: bool = typer.Option(False, help="have the model read each question (needs an API key; a "
                                                         "fraction of a penny each)"),
             only: list[str] = typer.Option(None, help="question ids"),
             save: bool = typer.Option(True, help="save the results under the data folder (eval/runs/ "
                                                  "there)")) -> None:
    """Score the site against the briefing test set (eval/questions.toml): how each question is read, and the
    evidence found. No briefing is written (docs/EVALUATION.md)."""
    from councils import evaluate as ev

    settings = load_settings()
    results = ev.run(settings, with_model, set(only) if only else None)
    for r in results:
        mark = "ok " if r.plan_ok and r.evidence_ok is not False else "-- "
        typer.echo(f"{mark}{r.id:28} {r.records:3} sources  " + "; ".join(r.problems))
    s = ev.summary(results)
    typer.echo(f"\nquestions read right: {s['plans_right']}/{s['questions']} (filters {s['fields_right']}/"
               f"{s['fields']}); evidence right: {s['evidence_right']}/{s['evidence_checked']}")
    for cat, c in s["by_category"].items():
        typer.echo(f"  {cat:10} {c['plans_right']}/{c['questions']}")
    if save:
        typer.echo(f"saved {ev.save(results, with_model, ev.runs_dir(settings))}")


def _state() -> StateDB:
    return open_state(load_settings(), CLOCK)


def _replies() -> Replies:
    """Reports and statements, as the owner's commands work on them: with the commands' own words for a name or a
    role the owner types."""
    from councils.api.data import Data

    settings, db = load_settings(), _state()
    record = Data(settings)
    return open_replies(db, lambda: record, open_archive(db, CLOCK), CLOCK, messages=OWNERS_MESSAGES)


def _done(ok: bool, done: str, failed: str) -> None:
    """Say what a command did. One that changed nothing exits 1 (as the sister sites), so the owner, or a script,
    can tell it from one that worked."""
    typer.echo(done if ok else failed)
    if not ok:
        raise typer.Exit(1)


@app.command()
def withdraw(briefing_id: str, reason: str = typer.Option(..., help="shown at its address, e.g. 'It misattributed a "
                                                                   "decision to the wrong council.'")) -> None:
    """Withdraw a saved briefing (/b/<id>): its address then says it has been withdrawn, and why, and the
    corrections page lists it. It is not replayed to the next reader who asks the same question."""
    from wts_core.observe import SqliteBriefingLog

    db = _state()
    ok = open_archive(db, CLOCK).withdraw(briefing_id, reason)
    if ok:
        # its copies in the answer cache go with it: a withdrawn briefing was replayed, for up to a week, to
        # anyone who asked the same question
        forget_replays(db, briefing_id, CLOCK)
        # and what happened next, on that briefing's record: it was corrected
        SqliteBriefingLog(db, clock=CLOCK).mark(briefing_id, corrected=True)
    _done(ok, "withdrawn", "no briefing with that id")


# Reports, statements and hidden items: the shared package's commands, with this site's own lines


def _shown_from(st: Mapping[str, Any]) -> str:
    """The date the words now shown were first shown: a published statement is dated afresh when it is updated."""
    return max(st["published_at"] or "", st["updated_at"] or "")[:10]


def _statement_lines(st: Mapping[str, Any]) -> list[str]:
    lines = [f"#{st['id']}  {st['at']}  {st['status']}  {st['item']}"
             + (f"  (on {st['about']}'s page)" if st["about"] else "  (on no council's page: --council)"),
             f"    from: {st['name']}, {st['role']}"]
    if st["email"]:
        lines.append(f"    confirm with: {st['email']}")
    if st["link"]:
        lines.append(f"    record: {st['link']}")
    lines += [f"    {para}" for para in st["text"].splitlines() if para.strip()]
    lines.append(f"    ({st['words']} words"
                 + (f"; shown from {_shown_from(st)}" if st["status"] == "published" else "")
                 + (f"; {st['status']}: {st['reason']}" if st["reason"] else "") + ")")
    return lines


def _report_lines(r: Mapping[str, Any]) -> list[str]:
    lines = [f"#{r['id']}  {r['at']}  {r['kind']}  {r['page'] or '-'}{'  (closed)' if r['closed_at'] else ''}",
             f"    {r['message']}"]
    if r["contact"]:
        lines.append(f"    reply to: {r['contact']}")
    if r["public_note"]:
        lines.append(f"    on the corrections page: {r['public_note']}")
    return lines


def _waiting(w: Mapping[str, Any]) -> str:
    """Said when something waits (``nothing_waiting``, below, is said when nothing does)."""
    return (f"{w['reports']} reports and {w['statements']} statements waiting; {w['hidden']} items hidden; the "
            f"oldest has waited {w['oldest_working_days']} working days (we promise a reply within 5)")


def _council(typed: str) -> str:
    """The council a statement is shown for, as the owner typed it (its GSS code or its name)."""
    from councils.registry import get

    try:
        return get(typed).gss
    except KeyError as exc:
        raise ValueError(f"no one council is called {typed}: give its GSS code, or more of its name") from exc


def _lapsing(w: Mapping[str, Any]) -> str:
    """What `councils would-lapse` says: each statement and report the next tidy would reach, by its number, the
    day it was sent and its age. Never an address, a name or a word of what was sent."""
    if not w["entries"]:
        return ("Nothing would lapse: no statement has waited, and no report with a contact address has been open, "
                "for more than three months.")
    said = [f"Statement {e['id']}, sent {e['at'][:10]} ({e['days']} days ago), would be declined as undecided."
            if e["what"] == "statement" else
            f"Report {e['id']}, sent {e['at'][:10]} ({e['days']} days ago), would lose its contact address."
            for e in w["entries"]]
    return "\n".join([*said, "They lapse at the next tidy: tonight's, or sooner, when a report or a statement is "
                              "next sent or a reports or statements command is next run."])


# What each command is called. The names are the family's (`councils statements publish 3`); the names the
# commands had before the shared package (`councils publish-statement 3`) still work for now, and print the same
# on standard output. From wts-core 0.3.0 each also says, on standard error, that it is an older name and what
# the command is called now (the package's own sentence; nothing of the site's reads those commands' standard
# error).
REPLIES_COMMANDS = RepliesCommands(
    listed=("pending", "published"),
    about_option="--council",
    withdraw_note="Withdrawn by its author.",
    outcome="resolved",
    tidy=None,              # `councils tidy` does the right of reply's housekeeping with the rest
    also={"list-reports": "reports_list", "close-report": "reports_close", "list-statements": "statements_list",
          "publish-statement": "statements_publish", "decline-statement": "statements_decline",
          "update-statement": "statements_update", "withdraw-statement": "statements_withdraw"},
    help={
        "reports": "Problems and takedown requests sent through the site's form.",
        "reports_list": "Problems and takedown requests sent through the site's form, takedown requests first, "
                        "then the newest first.",
        "reports_close": "Mark a report dealt with. Its contact address is deleted, as the privacy notice says. "
                         "With --public-note, what was put right is listed on the corrections page.",
        "reports_close.public_note": "what the corrections page says was put right; it must name no one who "
                                     "reported",
        "statements": "Statements under the right of reply: list, publish, decline, update, withdraw and remove "
                      "them.",
        "statements_list": "Statements under the right of reply sent through the site, newest first: those "
                           "waiting for a decision and those shown. Confirm who sent one (reply to its address, "
                           "ideally a council address) before publishing it.",
        "statements_list.all": "include declined, withdrawn and removed statements",
        "statements_publish": "Show a waiting statement beside its item and on its council's page, dated today, "
                              "as written (never edited), once you have confirmed who sent it: --checked says how.",
        "statements_publish.checked": "how you confirmed who sent it, for the log (never shown on the site), e.g. "
                                      "'Reply from the councillor's address on the council's website, 14 "
                                      "November.' Do not put the sender's email address in it: the privacy notice "
                                      "promises that address is deleted",
        "statements_publish.about": "also show it on this council's page (GSS code or name): for a statement about "
                                    "a briefing",
        "statements_decline": "Decline a waiting statement, with the reason (tell its author). Its address is "
                              "deleted three months later.",
        "statements_decline.reason": "for the author and the log, e.g. 'It is about another councillor's conduct.'",
        "statements_update": "Change a statement at its author's request (confirmed from their address). A "
                             "published one is dated afresh.",
        "statements_update.text": "the author's new wording, as sent",
        "statements_update.text_file": "the new wording, from a file",
        "statements_update.link": "the link to the record ('' for none)",
        "statements_withdraw": "Take a statement down, or stop one waiting, at its author's request. Its address "
                               "is deleted three months later.",
        "statements_remove": "Take a published statement down because it breaks the rules (policy 7.2: say why). "
                             "Its address is deleted three months later.",
        "hide": "Hide a council's page, a named vote or a saved briefing while a concern about it is decided: its "
                "address (/councils/E08000016, /votes/…, /b/…) then shows the note in its place.",
        "hide.note": "what is shown in the item's place, e.g. 'Hidden while we look into a concern about it.'",
    },
)

REPLIES_WORDING = RepliesWording(
    report=_report_lines,
    statement=_statement_lines,
    log_entry=lambda e: [f"    {e['at']}  {e['action']}" + (f": {e['note']}" if e["note"] else "")],
    hidden_item=lambda h: [f"{h['item']}  hidden since {h['at'][:10]}", f"    {h['note']}"],
    waiting=_waiting,
    nothing_waiting="nothing is waiting; {hidden} items hidden",
    published="published", declined="declined", updated="updated", withdrawn="withdrawn", removed="removed",
    closed="closed",
    hid="hidden: {item}",
    unhid="shown again: {item}",
    lapsing=_lapsing,
    tidied="right of reply: {emails} confirming addresses deleted, {lapsed} statements lapsed undecided, {contacts} "
           "old reports' contact addresses deleted",
    not_done="error: {message}", refused="error: {message}", errors_to_stderr=True,
)

def _changed(row: Mapping[str, Any], kind: Change) -> None:
    """After a change a page may show (``kind`` says which: one of ``wts_core.cli.CHANGES``). A report closed
    with a note for the corrections page, about a saved briefing: that briefing's record is marked as corrected
    (what happened next, for the statistics). A saved briefing hidden: it is no longer replayed from the answer
    cache."""
    if kind == "report_closed" and row.get("public_note") and row.get("briefing_id"):
        from wts_core.observe import SqliteBriefingLog

        SqliteBriefingLog(_state(), clock=CLOCK).mark(row["briefing_id"], corrected=True)
    # A saved briefing just hidden (the row is what is hidden: its address and the note): its copies in the
    # answer cache go, so that it is not replayed to the next reader who asks the same question.
    if kind == "hidden" and str(row.get("item") or "").startswith("/b/"):
        forget_replays(_state(), row["item"].split("/")[2], CLOCK)


app.add_typer(replies_commands(_replies, REPLIES_COMMANDS, REPLIES_WORDING, about=_council, changed=_changed))


# Backups: the shared package's commands (wts_core.cli), with this site's own lines

OPS_WORDING = OpsWording(
    backup=BackupWords(
        folder=None,                                  # --to must be given
        keep=BACKUPS.keep,
        nothing_to_back_up="nothing to back up yet (no state database)",
        backed_up="backup: {archive}",
        failed=None,                                  # a copy that fails its check is an error, shown as it is
        offsite_stored="Off-site copy: stored in {bucket} ({stored} kept there)",
        offsite_not_set_up="Off-site copy: not set up",
        offsite_failed="The off-site copy failed: {error}",
        help="Copy the state database (spending, saved briefings, reports, statements): the one thing that cannot "
             "be rebuilt. The copy also goes to a Backblaze B2 bucket when one is set up (COUNCILS_B2_* in "
             "deploy/.env).",
        to_help="folder for the backups", keep_help="how many to keep"),
    restore=RestoreWords(
        archive_must_exist=False, says_aborted=False,
        confirm="Replace {state_db} with {archive}? Stop the site first.",
        restored="restored {state_db} from {archive}",
        replaced="; the database it replaced is {kept}",
        not_restored="Not restored: {error}",
        help="Put a backup of the state database back. Stop the site first (docker compose stop app). The backup "
             "is checked before anything is replaced, and the database it replaces is kept beside it.",
        archive_help="a backup: /backups/councils-state-YYYY-MM-DD.sqlite.gz", yes_help="don't ask first"),
    backup_check=BackupCheckWords(
        folder=BACKUPS_FOLDER,
        no_folder="error: there is no backup folder at {folder}",
        alert="{level}: {text}",
        up_to_date="Backups are up to date.",
        alerts=BACKUP_ALERTS,
        help="Whether the nightly backup and its off-site copy are up to date. Prints any problem, and exits 1 if "
             "the last backup or off-site copy is over two days old or failed: run daily by "
             "councils-backup-check.timer, so a backup timer that has stopped running is noticed (its own failure "
             "alert never fires).",
        folder_help="the folder the backups are written to"),
    errors_to_stderr=True,
    offsite_help="Check the off-site backup bucket: whether the key works, and how many of this site's backups are "
                 "there.",
)
app.add_typer(ops_commands(SITE, load_settings, BACKUPS, OPS_WORDING, clock=lambda: CLOCK))

# Statistics, the weekly report and the nightly tidy: the shared package's commands


def _embedder() -> Any:
    from councils.index.lance import get_embedder

    return get_embedder(load_settings())      # the site's own, so no question leaves the server to be grouped


def _prices() -> PriceTable:
    settings = load_settings()
    return PriceTable.from_settings(settings.usage, file=settings.files)      # an error names the local file too


def _never_proposed(briefing: str) -> bool:
    """Whether a saved briefing's question is never to be proposed as a test question (`councils
    propose-questions`): what its own page asks, and more. A briefing that is no longer there or has been
    withdrawn; one hidden while a concern about it is decided, by its own address or because a council or a named
    vote it was written from is hidden (``Hidden.instead_of_briefing``, as /api/briefings/<id> asks); and one a
    report that is still open names. (The record's own marks leave out a briefing withdrawn, corrected or ever
    reported in any case; this does not lean on them.)"""
    db = _state()
    saved = open_archive(db, CLOCK).get(briefing)
    if saved is None or saved.withdrawn_at:
        return True
    replies = _replies()
    if hidden_now(replies).instead_of_briefing(saved.id, saved.events) is not None:
        return True
    return any(report.get("briefing_id") == briefing for report in replies.reports(open_only=True))


# `councils stats` (how briefings went, for any period), `councils weekly-report` (the week's figures saved under
# data/reports, with what is over its threshold; run by deploy/councils-weekly-report.timer), `councils
# propose-questions` (test questions proposed from readers' real ones, in a file for the owner to approve) and
# `councils tidy` (the nightly housekeeping, after each night's backup: the record of briefings older than it is
# kept, visitors' codes and the time of day on spending rows after their day, earlier days' visitor secrets,
# cached answers past their week, old weekly reports, the copy of the database made before the one-off import,
# and the right of reply's: confirming addresses three months after a statement ends, and what nobody decided in
# three; then the site's old tables, and last the file written out afresh).
app.add_typer(stats_commands(
    SITE, _state,
    thresholds=lambda: load_settings().section("alerts"),      # empty until the owner sets them
    folder=lambda: load_settings().reports_dir,
    embedder=_embedder,
    similarity=lambda: float(load_settings().embedding["theme_similarity"]),
    pricing=_prices,
    backup_days=BACKUPS_KEPT_DAYS,
    # the right of reply's deletions. The command itself then sees to the site's old tables, after these (so an
    # address deleted tonight is gone from the old row tonight), and last writes the file out afresh, so that
    # nothing deleted is left in its unused space (wts-core 0.3.0; the site had steps of its own for both)
    also_tidy=[replies_tidy(_replies, REPLIES_WORDING)],
    # how long a cached answer is kept: the tidy deletes the older ones on a night when no new answer is stored
    cache_hours=lambda: float(load_settings().usage["answer_cache_hours"]),
    # the briefings whose questions `councils propose-questions` never proposes
    proposals_leave_out=_never_proposed,
    clock=lambda: CLOCK))


# The briefing test set with each briefing written: the shared package's commands


def _eval_site() -> Any:
    from councils.evaluate import CouncilsEval

    return CouncilsEval(load_settings())


def _configuration() -> Mapping[str, Any]:
    """What an evaluation run is a run of: the configuration the settings give as they stand, with the same id
    the record of briefings gives it. Nothing is kept by asking (a run is not a reader's briefing)."""
    from councils.rag.pipeline import configuration

    return configuration(load_settings()).settings


def _checks(name: str) -> Any:
    from councils.rag import checks

    return getattr(checks, name)


def _runs() -> Any:
    """Where runs are saved: under the data folder, which can be written to on the server (the code's own folder
    cannot: a run would spend its money and then fail to save)."""
    from councils.evaluate import runs_dir

    return runs_dir(load_settings())


# `councils eval run` asks every question in eval/questions.toml of the real pipeline, each briefing written (it
# spends money: no more than [eval] max_cost_usd unless --max-cost says otherwise), saves the run under the data
# folder (eval/runs/ there) and holds it to [eval.thresholds]; `councils eval compare` sets two saved runs side by side; `councils eval
# replay` runs the checks again over briefings a run recorded (--record-fixtures), free and with no model.
# `councils evaluate`, above, stays: it scores how questions are read and what evidence is found, with no briefing.
app.add_typer(eval_commands(
    lambda: _eval_site(),        # looked up when a command runs, so a test can stand another in its place
    config=_configuration, config_id=config_id,      # the id the record of briefings gives the same parts
    pricing=_prices,
    thresholds=lambda: load_settings().section("eval")["thresholds"],
    runs=_runs,
    max_cost_usd=lambda: float(load_settings().section("eval")["max_cost_usd"]),   # no run starts without a limit
    verifier=lambda: _checks("VERIFIER"), loaded_words=lambda: _checks("LOADED_WORDS"),
    clock=lambda: CLOCK))


# Topic briefings (decision 35; src/councils/topics.py): `councils topics refresh` runs weekly
# (deploy/councils-topics.timer). It writes saved briefings and the topics' own table in the state database, which the
# site writes to at any time, and only reads the search index, so it takes no update lock.

topics_app = typer.Typer(no_args_is_help=True, help="Topic briefings (config/topics.toml): /topics and each topic's page.")
app.add_typer(topics_app, name="topics")


@topics_app.command("list")
def topics_list() -> None:
    """Each topic, when its current briefing was written, how many stand, and what the last run did with it."""
    from councils import topics

    settings = load_settings()
    db = open_state(settings, CLOCK)
    for row in topics.listing(settings, db, open_archive(db, CLOCK)):
        cur, check = row["current"], row["last_check"]
        written = f"written {cur['prepared_at'][:10]} ({cur['briefing_id']})" if cur else "not written yet"
        typer.echo(f"{row['topic'].slug:50} {written:36} {len(row['versions'])} standing"
                   + (f"  last run {check['checked_at'][:10]}: {check['outcome']}" if check else ""))


@topics_app.command("refresh")
def topics_refresh(only: list[str] = typer.Option(None, "--only", help="just this topic (its slug); repeat for more"),
                   force: bool = typer.Option(False, help="write it again even if it is not due, or its evidence is "
                                                          "unchanged")) -> None:
    """Write the topic briefings that are due, each through the same pipeline and checks as a reader's, counted
    against the site's spending caps. A failure keeps the last good briefing. Each costs about 7 cents. Exits 1 when a
    topic failed or the run stopped early (a spending cap, or the run's own limit, max_run_usd in the settings' topics
    section), so the timer's alert is sent."""
    from councils import topics
    from councils.api.app import build
    from councils.rag.pipeline import Pipeline
    from councils.replies import hidden_now

    settings = load_settings()
    site = build(settings, clock=CLOCK)        # the same parts as the site's: spending, caps, saved briefings
    now = hidden_now(site.replies)
    try:
        run = topics.refresh(settings, site.db, Pipeline(settings), site.parts, without_councils=sorted(now.councils),
                             without_votes=sorted(now.votes), only=only or None, force=force, clock=CLOCK,
                             say=typer.echo)
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(2) from None
    typer.echo(f"{len(run.written)} written, ${run.spent_usd:.2f} spent"
               + (f"; stopped: {run.stopped}" if run.stopped else ""))
    if run.needs_attention:
        raise typer.Exit(1)


suppress_app = typer.Typer(no_args_is_help=True, help="Names and phrases removed by hand: the suppression list "
                                                    "(src/councils/suppress.py; docs/OPERATIONS.md).")
app.add_typer(suppress_app, name="suppress")


@suppress_app.command("add")
def suppress_add(council: str = typer.Argument(..., help="the council: GSS code or a unique part of its name"),
                 text: str = typer.Argument(..., help="the name or phrase to remove, as the minutes write it"),
                 item: str = typer.Option("", help="only in this agenda item, or meeting (its id: a named vote's id "
                                                   "without its last part is its item's)"),
                 note: str = typer.Option("", help="why, for you (a report's number, say); never shown")) -> None:
    """Remove a name or phrase from a council's minutes wherever the site shows them or gives them to the model."""
    from councils import suppress
    from councils.registry import get

    try:
        c = get(council)
    except KeyError as exc:
        typer.echo(f"error: {exc.args[0]}")
        raise typer.Exit(1) from None
    s = load_settings()
    try:
        entry = suppress.add(s.data_dir, c.gss, text, item, note, today=CLOCK.now().date())
    except ValueError as exc:
        typer.echo(f"error: {exc}")
        raise typer.Exit(1) from None
    where = f" in {entry.item}" if entry.item else ""
    typer.echo(f'added: "{entry.text}" at {c.name}{where}. Pages, the sources of new briefings, and saved and cached '
               f"briefings leave it out from now on. To take it out of the search index too, run: councils index "
               f"{c.gss}")


@suppress_app.command("list")
def suppress_list() -> None:
    """Every entry on the suppression list."""
    from councils import suppress
    from councils.registry import councils

    for e in suppress.load(load_settings().data_dir).entries:
        name = councils()[e.council].name if e.council in councils() else e.council
        typer.echo("\t".join([e.added, name, e.item or "(whole council)", e.text] + ([e.note] if e.note else [])))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000,
          behind_proxy: bool = typer.Option(False, help="trust the proxy's forwarded client address")) -> None:
    """Run the website and its API (build the pages first: cd web && npm run build)."""
    import uvicorn

    from councils.api.app import create_app, start_logging

    s = load_settings()
    start_logging(s)      # the structured log of briefings, under the data folder (config/settings.toml, [logs])
    # Behind the front door (Where MPs Stand's web server, in another container), the visitor's address comes in
    # X-Forwarded-For, set by the front door from Cloudflare's header. The container's port is reachable only over the
    # server's Docker networks, never from outside, so any sender of the header can be trusted.
    uvicorn.run(create_app(s), host=host, port=port, proxy_headers=behind_proxy,
                forwarded_allow_ips="*" if behind_proxy else None, access_log=False)


@app.command("pilot-sample")
def pilot_sample() -> None:
    """The pilot's councils (docs/PILOT.md)."""
    from councils import pilot

    for c in pilot.sample():
        typer.echo(f"{c.gss}\t{c.nation}\t{c.type}\t{c.name}")


@app.command("pilot")
def pilot_run(workers: int = typer.Option(4, help="councils loaded at once")) -> None:
    """Ingest and parse every pilot council."""
    from councils import pilot

    for line in pilot.run(load_settings(), workers=workers):
        typer.echo(json.dumps(line))


@app.command("pilot-check")
def pilot_check(n: int = 15, seed: int = typer.Option(None, help="a different sample"),
                all_councils: bool = typer.Option(False, "--all", help="every council loaded, not just the pilot")) -> None:
    """A random sample of named votes and declarations, with their passages, for checking by hand."""
    from councils import pilot

    typer.echo(pilot.check_sample(load_settings(), n, seed if seed is not None else pilot.SEED, all_councils))


@app.command()
def report(all_councils: bool = typer.Option(False, "--all", help="every council loaded, not just the pilot")) -> None:
    """The pilot's measurements, as Markdown."""
    from councils import pilot

    typer.echo(pilot.report(load_settings(), all_councils))


@app.command()
def index(council: list[str] = typer.Argument(None, help="GSS codes or names; all loaded councils if none")) -> None:
    """Build the keyword search index from the stored minutes (names of non-councillors removed). Takes the server's
    update lock first, as the nightly update does, and waits for it while another job holds it (decision 29)."""
    from councils.index.build import Indexer
    from councils.lock import LockUnavailable, update_lock
    from councils.registry import get

    s = load_settings()
    codes = [get(c).gss for c in council] if council else None
    try:
        with update_lock(lambda words: typer.echo(words, err=True)):
            n = Indexer(s).index_all(codes)
    except LockUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{n} passages indexed")


@app.command()
def embed(max_minutes: float = typer.Option(None, help="stop after this long; run again to continue"),
          again: bool = typer.Option(False, "--again", help="throw every vector away and embed everything afresh "
                                                            "with the model the settings name: for after the "
                                                            "embedding model has changed")) -> None:
    """Embed indexed passages for meaning search, newest first. It writes the index's state file, as the update and
    ``index`` do, so it takes the server's update lock first and waits for it (decision 29)."""
    from councils.index.build import State, embed_again, embed_pending
    from councils.index.lance import get_embedder, open_index
    from councils.lock import LockUnavailable, update_lock

    s = load_settings()
    try:
        with update_lock(lambda words: typer.echo(words, err=True)):
            embedder = get_embedder(s)
            if again:
                typer.echo(f"{embed_again(s, embedder)} council-years to embed again")
            idx = open_index(s, embedder)
            n = embed_pending(s, idx, State(s.index_dir / "state.json"), embedder,
                              max_seconds=max_minutes * 60 if max_minutes else None)
            if n:
                idx.refresh()
    except LockUnavailable as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(1) from None
    typer.echo(f"{n} passages embedded")


@app.command()
def optimize() -> None:
    """Merge rows waiting to join the search indices, compact the index files and delete versions over an hour old.
    The daily update does this itself; this is for a one-off clean-up. The site keeps serving meanwhile."""
    from councils.index.lance import open_index

    open_index(load_settings()).tidy()
    typer.echo("search index optimised")


def _filters(start, end, council, control, party, kind):
    from councils.engine import Filters
    from councils.registry import get

    return Filters(date_from=date.fromisoformat(start) if start else None,
                   date_to=date.fromisoformat(end) if end else None,
                   councils=[get(c).gss for c in council or []], control=list(control or []),
                   parties=list(party or []), kinds=list(kind or []))


@app.command()
def search(query: str, start: str = typer.Option(None, "--from"), end: str = typer.Option(None, "--to"),
           council: list[str] = typer.Option(None), control: list[str] = typer.Option(None),
           party: list[str] = typer.Option(None), kind: list[str] = typer.Option(None),
           group_by: str = "control", limit: int = 12) -> None:
    """Search the minutes and show the balanced evidence a briefing would use (no model call)."""
    from councils.engine import Engine

    res = Engine(load_settings()).search(query, _filters(start, end, council, control, party, kind),
                                         limit=limit, group_by=group_by)
    for r in res.records:
        typer.echo(f"\n[{r['date']}] {r['heading']}  (control: {r['control']}; item {r['record_id']})\n  {r['url']}\n  "
                   + r["text"][:300].replace("\n", " "))
    typer.echo(f"\n{len(res.records)} items from {res.candidates} candidates; " + json.dumps(res.evidence, default=str))


@app.command()
def ask(question: str, comprehensive: bool = False, show_plan: bool = True) -> None:
    """Answer a question with a sourced briefing (needs an Anthropic API key; without one, shows the evidence)."""
    from councils.rag.pipeline import AskRequest, Pipeline, answer_once

    out = answer_once(Pipeline(load_settings()), AskRequest(question, "comprehensive" if comprehensive else "summary"))
    if show_plan:
        typer.echo(json.dumps(out["plan"]["plan"], indent=1, default=str))
    for src in out["sources"]["sources"]:
        typer.echo(f"[Source {src['n']}] {src['title']}\n    {src['url']}")
    final = out.get("final") or {}   # no final when the model declined to answer: the error says so
    typer.echo("\n" + ((final.get("answer") or {}).get("markdown") or final.get("note")
                       or (out.get("error") or {}).get("message") or ""))
