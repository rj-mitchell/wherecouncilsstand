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
    councils waiting                          # what is waiting for a decision, and for how long
    councils stats --since 7d                 # how briefings went: speed, cost, what the checks found
    councils weekly-report                    # the week's figures saved, and what is over its threshold (scheduled)
    councils tidy                             # the nightly housekeeping (scheduled, after the backup)
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
    OpsWording,
    RepliesCommands,
    RepliesWording,
    RestoreWords,
    ops_commands,
    replies_commands,
    replies_tidy,
    stats_commands,
)
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Replies
from wts_core.state import StateDB
from wts_core.usage import PriceTable

from councils.config import SITE, load_settings
from councils.replies import OWNERS_MESSAGES, open_replies
from councils.state import (
    BACKUP_ALERTS,
    BACKUPS,
    BACKUPS_KEPT_DAYS,
    forget_old_secret,
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
    summary = {"finished": time.strftime("%Y-%m-%dT%H:%M:%S"), "minutes": round((time.time() - started) / 60, 1),
               "councils": len(lines), "changed": len(changed),
               "new_meetings": sum(ln.get("new_meetings", 0) for ln in lines),
               "failed": sorted(ln["gss"] for ln in lines if ln.get("error")),
               # only with [robots] obey on (decision 21): sites whose robots.txt has started to forbid reading
               # (docs/OPERATIONS.md, "When it reports a problem")
               "robots": sorted(ln["gss"] for ln in lines if ln.get("error") == ROBOTS_ERROR), **indexed}
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
             save: bool = typer.Option(True, help="save the results under eval/runs/")) -> None:
    """Score the site against the briefing test set (eval/questions.toml): how each question is read, and the
    evidence found. No briefing is written (docs/EVALUATION.md)."""
    from councils import evaluate as ev

    results = ev.run(load_settings(), with_model, set(only) if only else None)
    for r in results:
        mark = "ok " if r.plan_ok and r.evidence_ok is not False else "-- "
        typer.echo(f"{mark}{r.id:28} {r.records:3} sources  " + "; ".join(r.problems))
    s = ev.summary(results)
    typer.echo(f"\nquestions read right: {s['plans_right']}/{s['questions']} (filters {s['fields_right']}/"
               f"{s['fields']}); evidence right: {s['evidence_right']}/{s['evidence_checked']}")
    for cat, c in s["by_category"].items():
        typer.echo(f"  {cat:10} {c['plans_right']}/{c['questions']}")
    if save:
        typer.echo(f"saved {ev.save(results, with_model)}")


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
    corrections page lists it."""
    from wts_core.observe import SqliteBriefingLog

    db = _state()
    ok = open_archive(db, CLOCK).withdraw(briefing_id, reason)
    if ok:      # what happened next, on that briefing's record: it was corrected
        SqliteBriefingLog(db, clock=CLOCK).mark(briefing_id, corrected=True)
    _done(ok, "withdrawn", "no briefing with that id")


# ---- reports, statements and hidden items: the shared package's commands, with this site's own lines -------------


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
    said = f"{w['reports']} reports and {w['statements']} statements waiting; {w['hidden']} items hidden"
    if w["oldest_working_days"] is None:
        return said
    return said + f"; the oldest has waited {w['oldest_working_days']} working days (we promise a reply within 5)"


def _council(typed: str) -> str:
    """The council a statement is shown for, as the owner typed it (its GSS code or its name)."""
    from councils.registry import get

    try:
        return get(typed).gss
    except KeyError as exc:
        raise ValueError(f"no one council is called {typed}: give its GSS code, or more of its name") from exc


# What each command is called. The names are the family's (`councils statements publish 3`); the names the
# commands had before the shared package (`councils publish-statement 3`) still work for now, and print the same.
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
    published="published", declined="declined", updated="updated", withdrawn="withdrawn", removed="removed",
    closed="closed",
    hid="hidden: {item}",
    unhid="shown again: {item}",
    tidied="right of reply: {emails} confirming addresses deleted, {lapsed} statements lapsed undecided, {contacts} "
           "old reports' contact addresses deleted",
    not_done="error: {message}", refused="error: {message}", errors_to_stderr=True,
)

def _changed(row: Mapping[str, Any]) -> None:
    """After a change a page may show. A report closed with a note for the corrections page, about a saved
    briefing: that briefing's record is marked as corrected (what happened next, for the statistics)."""
    if row.get("public_note") and row.get("briefing_id") and row.get("closed_at"):
        from wts_core.observe import SqliteBriefingLog

        SqliteBriefingLog(_state(), clock=CLOCK).mark(row["briefing_id"], corrected=True)


app.add_typer(replies_commands(_replies, REPLIES_COMMANDS, REPLIES_WORDING, about=_council, changed=_changed))


# ---- backups: the shared package's commands (wts_core.cli), with this site's own lines ----------------------------

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
        folder="/backups",
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

# ---- statistics, the weekly report and the nightly tidy: the shared package's commands ----------------------------


def _embedder() -> Any:
    from councils.index.lance import get_embedder

    return get_embedder(load_settings())      # the site's own, so no question leaves the server to be grouped


def _prices() -> PriceTable:
    settings = load_settings()
    return PriceTable.from_settings(settings.usage, file=settings.config_path)


# `councils stats` (how briefings went, for any period), `councils weekly-report` (the week's figures saved under
# data/reports, with what is over its threshold; run by deploy/councils-weekly-report.timer) and `councils tidy`
# (the nightly housekeeping, after each night's backup: the record of briefings older than it is kept, visitors'
# codes after their day, old weekly reports, the copy of the database made before the one-off import, and the
# right of reply's: confirming addresses three months after a statement ends, and what nobody decided in three).
app.add_typer(stats_commands(
    SITE, _state,
    thresholds=lambda: load_settings().section("alerts"),      # empty until the owner sets them
    folder=lambda: load_settings().reports_dir,
    embedder=_embedder,
    similarity=lambda: float(load_settings().embedding["theme_similarity"]),
    pricing=_prices,
    backup_days=BACKUPS_KEPT_DAYS,
    also_tidy=[replies_tidy(_replies, REPLIES_WORDING), lambda: forget_old_secret(_state(), CLOCK)],
    clock=lambda: CLOCK))


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
    """Build the keyword search index from the stored minutes (names of non-councillors removed)."""
    from councils.index.build import Indexer
    from councils.registry import get

    s = load_settings()
    n = Indexer(s).index_all([get(c).gss for c in council] if council else None)
    typer.echo(f"{n} passages indexed")


@app.command()
def embed(max_minutes: float = typer.Option(None, help="stop after this long; run again to continue"),
          again: bool = typer.Option(False, "--again", help="throw every vector away and embed everything afresh "
                                                            "with the model the settings name: for after the "
                                                            "embedding model has changed")) -> None:
    """Embed indexed passages for meaning search, newest first."""
    from councils.index.build import State, embed_again, embed_pending
    from councils.index.lance import get_embedder, open_index

    s = load_settings()
    embedder = get_embedder(s)
    if again:
        typer.echo(f"{embed_again(s, embedder)} council-years to embed again")
    idx = open_index(s, embedder)
    n = embed_pending(s, idx, State(s.index_dir / "state.json"), embedder,
                      max_seconds=max_minutes * 60 if max_minutes else None)
    if n:
        idx.refresh()
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
        typer.echo(f"\n[{r['date']}] {r['heading']}  (control: {r['control']})\n  {r['url']}\n  "
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
