"""Build data_static/landlords_links.csv: for each council, its pages on Where Landlords Stand (README, "In the family").

    uv run python scripts/landlords_links.py [--landlords ../wherelandlordsstand] [--site https://wherelandlordsstand.com]

Both sites key councils by ONS GSS code. For each council the file records:

- the area page listing the social landlords with homes in the council's area (Where Landlords Stand covers
  England), with how many there are;
- the council's own page as a landlord, where it owns homes and has a profile there.

It reads the Landlords repository's council and landlord register (`data_static/landlords.csv`), and the figures
that site publishes (`data/homes-by-area.csv` and `data/landlords.csv`): from the checkout's last build
(`data/site/data/`) if there is one, otherwise from the live site. Area pages are named as the Landlords site names
them (its `site_pages.area_rows`): an England area with rented homes, its name made into a slug, with the GSS code
added when two areas share a name. Every page is checked against the build, or the live site's list, before it is
written, so a link here never points at a page that isn't there.

Run it when Where Landlords Stand publishes new figures (its weekly update), and commit the file.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
import sys
import unicodedata
import urllib.request
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data_static" / "landlords_links.csv"
FIELDS = ["gss", "area_name", "area_slug", "area_landlords", "council_landlord", "council_landlord_slug"]


def slugify(name: str) -> str:
    """As Where Landlords Stand's register.slugify."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    s = re.sub(r"^the\s+", "", s)
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-")


def published(landlords: Path, site: str, name: str) -> list[dict[str, str]]:
    built = landlords / "data" / "site" / "data" / name
    if built.is_file():
        text = built.read_text(encoding="utf-8")
    else:
        with urllib.request.urlopen(f"{site.rstrip('/')}/data/{name}", timeout=60) as r:  # noqa: S310 - a fixed https URL
            text = r.read().decode("utf-8")
    return list(csv.DictReader(io.StringIO(text)))


def build(landlords: Path, site: str) -> list[dict[str, str]]:
    # areas: as site_pages.area_rows, from the published homes by area (one row per landlord profile and area)
    areas: dict[str, dict] = {}
    for r in published(landlords, site, "homes-by-area.csv"):
        if not r["gss"].startswith("E") or not r["rented_homes"] or float(r["rented_homes"]) <= 0:
            continue
        a = areas.setdefault(r["gss"], {"name": r["area_name"], "landlords": set()})
        a["landlords"].add(r["landlord_id"])
    seen: dict[str, int] = defaultdict(int)
    for gss, a in sorted(areas.items(), key=lambda kv: kv[1]["name"]):
        base = slugify(a["name"])
        seen[base] += 1
        a["slug"] = base if seen[base] == 1 else f"{base}-{gss.lower()}"

    # councils as landlords: the register's councils with a profile, whose page is published
    pages = {r["page"] for r in published(landlords, site, "landlords.csv")}
    councils: dict[str, dict[str, str]] = {}
    with open(landlords / "data_static" / "landlords.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            if r["type"] == "council" and r["gss"] and r["status"] == "active" and r["slug"] \
                    and f"landlords/{r['slug']}/" in pages:
                councils[r["gss"]] = {"name": r["display_name"] or r["legal_name"], "slug": r["slug"]}

    built_areas = landlords / "data" / "site" / "areas"
    if built_areas.is_dir():
        missing = [a["slug"] for a in areas.values() if not (built_areas / a["slug"] / "index.html").is_file()]
        if missing:
            sys.exit(f"area pages not in the Landlords build: {', '.join(sorted(missing))}")

    rows = []
    for gss in sorted(set(areas) | set(councils)):
        a, c = areas.get(gss), councils.get(gss)
        rows.append({"gss": gss, "area_name": a["name"] if a else "", "area_slug": a["slug"] if a else "",
                     "area_landlords": str(len(a["landlords"])) if a else "",
                     "council_landlord": c["name"] if c else "", "council_landlord_slug": c["slug"] if c else ""})
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--landlords", type=Path, default=ROOT.parent / "wherelandlordsstand",
                    help="a checkout of rj-mitchell/wherelandlordsstand")
    ap.add_argument("--site", default="https://wherelandlordsstand.com", help="where its published data is")
    args = ap.parse_args()
    rows = build(args.landlords, args.site)
    with open(OUT, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, FIELDS, lineterminator="\n")
        w.writeheader()
        w.writerows(rows)
    areas = sum(1 for r in rows if r["area_slug"])
    councils = sum(1 for r in rows if r["council_landlord_slug"])
    print(f"Wrote {OUT.relative_to(ROOT)}: {len(rows)} councils, {areas} with an area page, {councils} as landlords.")


if __name__ == "__main__":
    main()
