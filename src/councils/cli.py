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
    councils search "bin collections" --control NOC
    councils ask "What have Labour-run councils decided about bin collections since 2023?"
"""

from __future__ import annotations

import json
import logging
from datetime import date

import typer

from councils.config import load_settings

app = typer.Typer(add_completion=False, no_args_is_help=True)


@app.callback()
def main(verbose: bool = typer.Option(False, "--verbose", "-v")) -> None:
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")


@app.command("list")
def list_(status: str = typer.Option(None, help="ok, blocked, unreachable or none"),
          nation: str = typer.Option(None)) -> None:
    """Councils in scope, with their Modern.gov site and whether it answered."""
    from councils.registry import councils

    for c in councils().values():
        if (status and c.modgov_status != status) or (nation and c.nation != nation):
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
def load(status: str = typer.Option("ok", help="councils whose web service had this status"),
         nation: str = typer.Option(None), workers: int = typer.Option(20, help="councils loaded at once"),
         resume: bool = typer.Option(False, help="only parse councils already loaded")) -> None:
    """Load and parse every council in scope, printing one line per council as it finishes."""
    from councils import load as load_
    from councils.registry import councils

    chosen = [c for c in councils().values() if c.modgov_status == status and (not nation or c.nation == nation)]
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
    from councils.embed.base import get_embedder
    from councils.index.build import update_index
    from councils.registry import councils, get

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
               "failed": sorted(ln["gss"] for ln in lines if ln.get("error")), **indexed}
    # needs attention: many councils failing at once means something on our side, not one council's server
    summary["needs_attention"] = not lines or len(summary["failed"]) > max(5, len(lines) // 10)
    with open(s.data_dir / log_file, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary) + "\n")
    typer.echo(json.dumps(summary))
    if summary["needs_attention"]:
        raise typer.Exit(1)


@app.command()
def backup(to: str = typer.Option(..., help="folder for the backups"),
           keep: int = typer.Option(14, help="how many to keep")) -> None:
    """Copy the state database (spending, saved briefings, reports): the one thing that cannot be rebuilt. The copy
    also goes to a Backblaze B2 bucket when one is set up (COUNCILS_B2_* in deploy/.env)."""
    from pathlib import Path

    from councils.backup import make_backup
    from councils.offsite import OffsiteError, send

    out = make_backup(load_settings().data_dir / "state.db", Path(to), keep)
    if not out:
        typer.echo("nothing to back up yet (no state database)")
        return
    typer.echo(f"backup: {out}")
    try:
        sent = send(out)
    except OffsiteError as exc:
        typer.echo(f"The off-site copy failed: {exc}", err=True)
        raise typer.Exit(1) from exc
    typer.echo("Off-site copy: " + (f"stored in {sent['bucket']} ({sent['stored']} kept there)"
                                    if sent.get("ok") else sent["offsite"]))


@app.command()
def offsite() -> None:
    """Check the off-site backup bucket: whether the key works, and how many of this site's backups are there."""
    from councils.offsite import check

    typer.echo(json.dumps(check(), indent=2))


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000,
          behind_proxy: bool = typer.Option(False, help="trust the proxy's forwarded client address")) -> None:
    """Run the website and its API (build the pages first: cd web && npm run build)."""
    import uvicorn

    from councils.api.app import create_app

    s = load_settings()
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
def embed(max_minutes: float = typer.Option(None, help="stop after this long; run again to continue")) -> None:
    """Embed indexed passages for meaning search, newest first (needs the 'embed' extra)."""
    from councils.embed.base import get_embedder
    from councils.index.build import State, embed_pending
    from councils.index.lance import SearchIndex

    s = load_settings()
    idx = SearchIndex(s.index_dir, int(s.embedding.get("dim", 384)))
    n = embed_pending(s, idx, State(s.index_dir / "state.json"), get_embedder(s),
                      max_seconds=max_minutes * 60 if max_minutes else None)
    if n:
        idx.refresh()
    typer.echo(f"{n} passages embedded")


@app.command()
def optimize() -> None:
    """Merge rows waiting to join the search indices, compact the index files and delete versions over an hour old.
    The daily update does this itself; this is for a one-off clean-up. The site keeps serving meanwhile."""
    from councils.index.lance import SearchIndex

    s = load_settings()
    SearchIndex(s.index_dir, int(s.embedding.get("dim", 384))).optimize()
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
    final = out["final"]
    typer.echo("\n" + ((final.get("answer") or {}).get("markdown") or final.get("note") or ""))
