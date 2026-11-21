"""Build data_static/council_constituencies.csv and data_static/mps.json: for each council and strategic authority,
the Westminster constituencies (2024 boundaries) that overlap it, and the first copy of Where MPs Stand's list of
MPs, which the nightly update then keeps fresh (decision 31; ``councils.sisters.refresh_mps``).

    uv run python scripts/mp_links.py [--lookup lookup.csv] [--people people.json]

Source: ONS, "Ward to Westminster Parliamentary Constituency to Local Authority District to Upper Tier Local
Authority (July 2024) Lookup in the UK", item 62eb9df29a2f4521b5076a419ff9a47e on the Open Geography Portal
(https://geoportal.statistics.gov.uk/), also served as the feature service WD24_PCON24_LAD24_UTLA24_UK_LU: one row for
each ward, or part of a ward, in a constituency. Source: Office for National Statistics licensed under the Open
Government Licence v.3.0. The ONS's licences page asks lookups to carry that statement only; the Ordnance Survey
notice is for its digital boundaries, which this doesn't use.

A council overlaps a seat when at least one of its wards (or part of one) is in the seat. Each row gives the
council's code (its own code here: Barnsley and Sheffield have the codes ONS gave them in 2019, which the lookup of
July 2024 doesn't yet use), the seat's code and name, and how many of the council's wards (or parts of wards) are in
the seat. A district's seats and its county's both come from the lookup (LAD24 and UTLA24). A strategic authority's
are its constituent councils' (data_static/authority_councils.csv; not its non-constituent councils, which are
outside its area), and the Greater London Authority's are London's boroughs' and the City of London's.

Where MPs Stand's list (https://wherempsstand.com/api/people) gives each sitting MP's seat by name; the two are
matched by name, without accents, case or punctuation, and any seat left without an MP is printed. Run this again
when the ONS publishes a new lookup (after a boundary change, or a change of councils), and commit both files.
"""

from __future__ import annotations

import argparse
import csv
import io
import json
import sys
import time
import urllib.request
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from councils import sisters  # noqa: E402 - after the path is set
from councils.registry import councils, memberships  # noqa: E402

OUT = sisters.CONSTITUENCIES
LOOKUP_ITEM = "62eb9df29a2f4521b5076a419ff9a47e"
LOOKUP_URL = f"https://geoportal.statistics.gov.uk/api/download/v1/items/{LOOKUP_ITEM}/csv?layers=0"
FIELDS = ["gss", "pcon_code", "pcon_name", "wards"]
NEED = {"WD24CD", "PCON24CD", "PCON24NM", "LAD24CD", "UTLA24CD"}
# the lookup's code for a council, where this site uses a later one (scripts/build_councils.py, SUPERSEDED)
OURS = {"E08000016": "E08000038",   # Barnsley
        "E08000019": "E08000039"}   # Sheffield
LONDON = "E12000007"                # the Greater London Authority's key (decision 17)


def download(url: str) -> bytes:
    for attempt in range(6):
        if attempt:
            time.sleep(5 * attempt)
        req = urllib.request.Request(url, headers={"User-Agent": "WhereCouncilsStand"})
        try:
            with urllib.request.urlopen(req, timeout=300) as resp:  # noqa: S310 - fixed https addresses
                if resp.status == 202:      # the portal builds the file on the first request
                    continue
                return resp.read()
        except OSError as exc:
            print(f"  {url}: {exc}; trying again", file=sys.stderr)
    raise SystemExit(f"{url} could not be downloaded after several attempts; try again later")


def overlaps(text: str) -> list[dict[str, str]]:
    rows = list(csv.DictReader(io.StringIO(text.lstrip("\ufeff"))))
    if not rows or not set(rows[0]) >= NEED:
        raise SystemExit(f"the lookup does not have the expected columns ({', '.join(sorted(NEED))})")
    names: dict[str, str] = {}
    wards: dict[tuple[str, str], set[str]] = defaultdict(set)
    for r in rows:
        ward, pcon = r["WD24CD"].strip(), r["PCON24CD"].strip()
        if not (ward and pcon):
            continue
        names[pcon] = r["PCON24NM"].strip()
        for code in {r["LAD24CD"].strip(), r["UTLA24CD"].strip()} - {""}:
            wards[(OURS.get(code, code), pcon)].add(ward)

    # strategic authorities: their constituent councils' seats, and London's boroughs' for the GLA
    every = councils()
    areas: dict[str, set[str]] = defaultdict(set)
    for m in memberships():
        if m.role == "constituent" and m.end is None:
            areas[m.authority].add(m.council)
    areas[LONDON] = {c.gss for c in every.values() if c.region == LONDON and not c.is_authority}
    by_council: dict[str, dict[str, set[str]]] = defaultdict(dict)
    for (code, pcon), ws in wards.items():
        by_council[code][pcon] = ws
    for authority, members in areas.items():
        for member in members:
            for pcon, ws in by_council.get(member, {}).items():
                wards[(authority, pcon)] |= ws

    out = [{"gss": code, "pcon_code": pcon, "pcon_name": names[pcon], "wards": str(len(ws))}
           for (code, pcon), ws in wards.items() if code in every]
    out.sort(key=lambda r: (r["gss"], r["pcon_name"]))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lookup", type=Path, help="the ONS lookup as CSV, already downloaded (otherwise fetched)")
    ap.add_argument("--people", type=Path, help="Where MPs Stand's /api/people, saved (otherwise fetched)")
    args = ap.parse_args()

    text = args.lookup.read_text(encoding="utf-8-sig") if args.lookup else download(LOOKUP_URL).decode("utf-8-sig")
    rows = overlaps(text)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    covered = {r["gss"] for r in rows}
    missing = sorted(c.gss for c in councils().values() if c.gss not in covered)
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(covered)} councils and authorities, "
          f"{len({r['pcon_code'] for r in rows})} constituencies, {len(rows)} overlaps"
          + (f"; no seats for {', '.join(missing)}" if missing else ""))

    raw = args.people.read_bytes() if args.people else download(sisters.MPS_API)
    listing = sisters.mps_listing(json.loads(raw), fetched=datetime.now(UTC).date().isoformat())
    sisters.MPS_SEED.write_text(json.dumps(listing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    sisters._seats.cache_clear()
    left = sisters.unmatched(listing)
    print(f"Wrote {sisters.MPS_SEED.relative_to(ROOT)}: {len(listing['mps'])} MPs; "
          + (f"seats with no MP on Where MPs Stand: {', '.join(left)}" if left else "every seat has its MP"))


if __name__ == "__main__":
    main()
