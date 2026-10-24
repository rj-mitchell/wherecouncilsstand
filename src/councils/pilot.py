"""The pilot: 20 councils chosen by a fixed rule, loaded from May 2018, and measured (docs/PILOT.md).

The rule: from councils whose Modern.gov web service answers, draw 17 English councils in proportion to the number of
English councils of each type (9 districts, 3 unitaries, 2 metropolitan boroughs, 2 London boroughs, 1 county) and 3
Welsh councils, at random with a published seed. Party control plays no part.
"""

from __future__ import annotations

import random
from collections import Counter, defaultdict
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

import duckdb

from councils import extract, ingest, store
from councils.config import Settings
from councils.registry import Council, councils

SEED = 20261024
QUOTAS = {("england", "district"): 9, ("england", "unitary"): 3, ("england", "metropolitan"): 2,
          ("england", "london_borough"): 2, ("england", "county"): 1, ("wales", "unitary"): 3}


def sample() -> list[Council]:
    rng = random.Random(SEED)
    pool: dict[tuple[str, str], list[Council]] = defaultdict(list)
    for c in sorted(councils().values(), key=lambda c: c.gss):
        if c.modgov_status == "ok":
            pool[(c.nation, c.type)].append(c)
    out = []
    for stratum, n in QUOTAS.items():
        out += rng.sample(pool[stratum], n)
    return out


def run(settings: Settings, workers: int = 10) -> Iterator[dict]:
    """Load and parse each pilot council. Each council is a different server, so they run side by side; requests to
    any one council stay one at a time."""

    def one(c: Council) -> dict:
        res = ingest.load(settings, c)
        line = {"gss": c.gss, "name": c.name, "meetings": res.meetings, "failed": len(res.failed),
                "committees": sorted({f"{t} ({k})" for t, k in res.committees.values()}), "error": res.error}
        if res.meetings:
            line |= extract.run(settings, c.gss)
        return line

    with ThreadPoolExecutor(workers) as ex:
        futures = [ex.submit(one, c) for c in sample()]
        for f in as_completed(futures):
            yield f.result()


def _pct(a: float, b: float) -> str:
    return f"{100 * a / b:.0f}%" if b else "–"


def report(settings: Settings) -> str:
    con = duckdb.connect()
    made = store.parquet.attach(con, settings.parquet_dir)
    if "meetings" not in made:
        return "No pilot data loaded."
    pilot = {c.gss: c for c in sample()}
    ids = ", ".join(f"'{g}'" for g in pilot)
    q = lambda sql: con.execute(sql).fetchall()  # noqa: E731

    lines = ["| Council | Type | Meetings (council / cabinet / policy) | From | Minutes text | Named votes | "
             "Names matched | Declarations | Matched |", "|---|---|---|---|---|---|---|---|---|"]
    rows = q(f"""
        select gss, any_value(council),
               count(*) filter (where kind = 'council'), count(*) filter (where kind = 'cabinet'),
               count(*) filter (where kind = 'policy'), min(date),
               count(*) filter (where items_with_minutes > 0), count(*)
        from meetings where gss in ({ids}) group by gss order by 2""")
    vote = {g: (b, n, m) for g, b, n, m in q(f"""
        select gss, count(distinct vote_id), count(*), count(*) filter (where member_id <> '')
        from votes where gss in ({ids}) group by gss""")} if "votes" in made else {}
    decl = {g: (n, m) for g, n, m in q(f"""
        select gss, count(*), count(*) filter (where member_id <> '')
        from declarations where gss in ({ids}) group by gss""")} if "declarations" in made else {}
    totals = Counter()
    for gss, name, nc, ncab, npol, first, with_text, n in rows:
        b, vn, vm = vote.get(gss, (0, 0, 0))
        dn, dm = decl.get(gss, (0, 0))
        totals.update(meetings=n, with_text=with_text, blocks=b, vote_names=vn, vote_matched=vm, decl=dn,
                      decl_matched=dm)
        lines.append(f"| {name} | {pilot[gss].type.replace('_', ' ')} | {nc} / {ncab} / {npol} | {first:%b %Y} | "
                     f"{_pct(with_text, n)} | {b} | {_pct(vm, vn)} | {dn} | {_pct(dm, dn)} |")
    missing = [c.name for g, c in pilot.items() if g not in {r[0] for r in rows}]
    lines.append(f"| **All** | | {totals['meetings']} | | {_pct(totals['with_text'], totals['meetings'])} | "
                 f"{totals['blocks']} | {_pct(totals['vote_matched'], totals['vote_names'])} | {totals['decl']} | "
                 f"{_pct(totals['decl_matched'], totals['decl'])} |")
    out = ["## Councils", "", *lines, ""]
    if missing:
        out += [f"Not loaded: {', '.join(missing)}.", ""]

    out += ["## Minutes by year", "", "| Year | Meetings | With minutes text | Minutes only as a document | "
            "No minutes yet |", "|---|---|---|---|---|"]
    for y, n, t, pdf in q(f"""
        select year, count(*), count(*) filter (where items_with_minutes > 0),
               count(*) filter (where items_with_minutes = 0 and minutes_pdf_url <> '')
        from meetings where gss in ({ids}) group by year order by year"""):
        out.append(f"| {y} | {n} | {_pct(t, n)} | {_pct(pdf, n)} | {_pct(n - t - pdf, n)} |")

    out += ["", "## Party labels", ""]
    labels = q(f"""select party_label, party, count(*) from attendance where gss in ({ids})
                   and member_type in ('', 'U') group by 1, 2 order by 3 desc""")
    total = sum(n for *_, n in labels)
    known = sum(n for _, p, n in labels if p)
    out.append(f"{known:,} of {total:,} attendance records ({_pct(known, total)}) have a recognised party. "
               f"{len({lab for lab, *_ in labels})} different labels were seen.")
    unknown = [(lab, n) for lab, p, n in labels if not p]
    if unknown:
        out += ["", "Labels not recognised:", "",
                *(f"- `{lab}` ({n:,})" for lab, n in unknown[:40])]

    size = q(f"select sum(length(minutes_text)), count(*) filter (where minutes_text <> '') from items "
             f"where gss in ({ids})")[0]
    out += ["", "## Size", "", f"{size[1]:,} agenda items with minutes text, {size[0] or 0:,} characters "
            f"(about {(size[0] or 0) // 4:,} tokens)."]
    return "\n".join(out)


def check_sample(settings: Settings, n: int = 15, seed: int = SEED) -> str:
    """A random sample (fixed seed) of named votes and declarations, each with the passage it was read from, for
    checking by hand against the minutes."""
    con = duckdb.connect()
    store.parquet.attach(con, settings.parquet_dir)
    ids = ", ".join(f"'{g}'" for g in (c.gss for c in sample()))
    rng = random.Random(seed)
    blocks = [r[0] for r in con.execute(f"select distinct vote_id from votes where gss in ({ids}) order by 1").fetchall()]
    out = ["# Named votes"]
    for vid in sorted(rng.sample(blocks, min(n, len(blocks)))):
        rows = con.execute("select vote, name, member_id, outcome, question, excerpt, i.url from votes v "
                           "join items i using (item_id) where vote_id = ? order by vote, name", [vid]).fetchall()
        sides = defaultdict(list)
        for vote, name, member_id, *_ in rows:
            sides[vote].append(name + ("" if member_id else " [unmatched]"))
        out += ["", f"## {vid}  outcome={rows[0][3] or '?'}  question={rows[0][4] or '?'}", rows[0][6],
                *(f"- {side} ({len(names)}): {', '.join(names)}" for side, names in sides.items()),
                f"> {rows[0][5]}"]
    decls = con.execute(f"select d.name, d.member_id, d.interest, d.excerpt, i.url from declarations d join items i "
                        f"using (item_id) where d.gss in ({ids}) order by d.item_id, d.name").fetchall()
    out += ["", "# Declarations"]
    for name, member_id, interest, excerpt, url in rng.sample(decls, min(n, len(decls))):
        out += ["", f"- {name}{'' if member_id else ' [unmatched]'} — {interest or '?'} — {url}", f"> {excerpt}"]
    return "\n".join(out)
