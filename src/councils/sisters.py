"""Links to the charity's sister sites where their records meet this one's (README, "The Where They Stand
family").

Where Landlords Stand covers social landlords in England, councils among them. Both sites key councils by ONS GSS
code, so a council's page here links to the council's own page there, where it owns homes, and to the area page
listing the landlords with homes in its area. The pages are listed in data_static/landlords_links.csv, built from
that site's published data by scripts/landlords_links.py, so a link never depends on the other site being up.

Where MPs Stand covers the UK Parliament. A council's page lists the MPs whose seats overlap it (decision 31): the
Westminster constituencies with at least part of a ward in the council's area, from the ONS lookup of wards to
constituencies and councils (July 2024), kept in data_static/council_constituencies.csv by scripts/mp_links.py, and
each seat's MP from Where MPs Stand's own public list of current members (/api/people). The first copy of that list
is kept with the code (data_static/mps.json); the nightly update fetches it again (``refresh_mps``) and keeps the
last good copy in the data folder if the site can't be reached or answers with something that isn't a list of MPs.
Nothing is asked of another site while a page is served, and an MP is linked only if Where MPs Stand lists them.
"""

from __future__ import annotations

import csv
import http.client
import json
import logging
import os
import re
import unicodedata
import urllib.request
from collections.abc import Callable
from datetime import UTC, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any

from councils.config import REPO_ROOT, STATIC_DIR

log = logging.getLogger(__name__)

LANDLORDS_URL = "https://wherelandlordsstand.com"
MPS_NAME = "Where MPs Stand"
MPS_URL = "https://wherempsstand.com"
MPS_API = f"{MPS_URL}/api/people"
CONSTITUENCIES = STATIC_DIR / "council_constituencies.csv"
MPS_SEED = STATIC_DIR / "mps.json"
# fewer than this is not Where MPs Stand's list of the House of Commons (650 seats)
MIN_MPS = 400
# the family kit's footer shelf, as built and as synced (web/public/family, which the build copies)
SHELF = (REPO_ROOT / "web" / "dist" / "family" / "shelf.html", REPO_ROOT / "web" / "public" / "family" / "shelf.html")


@lru_cache(maxsize=1)
def _landlords() -> dict[str, dict[str, str]]:
    path = STATIC_DIR / "landlords_links.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {r["gss"]: r for r in csv.DictReader(fh)}


def landlords(gss: str) -> dict[str, Any] | None:
    """The council's pages on Where Landlords Stand, or None where it has none."""
    r = _landlords().get(gss)
    if r is None:
        return None
    out: dict[str, Any] = {"council": None, "area": None}
    if r["council_landlord_slug"]:
        out["council"] = {"name": r["council_landlord"],
                          "url": f"{LANDLORDS_URL}/landlords/{r['council_landlord_slug']}/"}
    if r["area_slug"]:
        out["area"] = {"name": r["area_name"], "landlords": int(r["area_landlords"]),
                       "url": f"{LANDLORDS_URL}/areas/{r['area_slug']}/"}
    return out


# Where MPs Stand's list of MPs

def seat_key(name: str) -> str:
    """A constituency's name as the two records are matched on: without accents, case, "&" or punctuation
    ("Ynys Môn" and "ynys mon", "Brighton Kemptown & Peacehaven" and "Brighton Kemptown and Peacehaven")."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower().replace("&", " and ")
    return " ".join(re.sub(r"[^a-z0-9]+", " ", s).split())


def mp_url(number: int | str, slug: str) -> str:
    return f"{MPS_URL}/people/{number}/{slug}"


def mps_listing(raw: Any, fetched: str) -> dict[str, Any]:
    """The parts of Where MPs Stand's /api/people this site uses: each sitting MP's number, name, address, party and
    seat. Peers are left out. Raises ValueError if ``raw`` is not that list."""
    rows = raw.get("people") if isinstance(raw, dict) else None
    if not isinstance(rows, list):
        raise ValueError("the answer has no list of people")
    mps = []
    for p in rows:
        if not isinstance(p, dict) or p.get("house") != "commons" or p.get("current") is False:
            continue
        number, name, slug, seat = p.get("number"), p.get("name"), p.get("slug"), p.get("constituency")
        if isinstance(number, int) and isinstance(name, str) and name.strip() and isinstance(seat, str) \
                and seat.strip() and isinstance(slug, str) and re.fullmatch(r"[a-z0-9-]+", slug):
            mps.append({"number": number, "name": name.strip(), "slug": slug, "constituency": seat.strip(),
                        "party": str(p.get("party") or "").strip()})
    if len(mps) < MIN_MPS:
        raise ValueError(f"the list has {len(mps)} MPs, fewer than {MIN_MPS}")
    return {"source": MPS_API, "fetched": fetched, "mps": sorted(mps, key=lambda m: m["constituency"])}


def mps_path(settings: Any) -> Path:
    """The copy the nightly update keeps fresh, in the data folder."""
    return Path(settings.data_dir) / "mps.json"


def _read(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and isinstance(data.get("mps"), list) else None


def _get(url: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": "WhereCouncilsStand", "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 - a fixed https address
        return json.loads(resp.read())


def refresh_mps(settings: Any, fetch: Callable[[str], Any] | None = None) -> dict[str, Any]:
    """Fetch Where MPs Stand's list again, for the nightly update. If the site can't be reached, or its answer isn't
    the list, or is less than half as long as the last good copy, the last good copy is kept and the reason given.
    Gives what the update's summary records: how many MPs, and the seats overlapping a council that no MP on the
    list sits for (a vacant seat, or a name the two records spell differently)."""
    path = mps_path(settings)
    last = _read(path) or _read(MPS_SEED)
    try:
        listing = mps_listing((fetch or _get)(MPS_API), fetched=datetime.now(UTC).date().isoformat())
        if last and len(listing["mps"]) < len(last["mps"]) / 2:
            raise ValueError(f"the list has {len(listing['mps'])} MPs, against {len(last['mps'])} in the last copy")
    except (OSError, ValueError, http.client.HTTPException) as exc:  # timeouts, HTTP errors, JSON that won't parse
        log.warning("Where MPs Stand's list of MPs not updated: %s", exc)
        return {"error": str(exc)[:200], "kept": (last or {}).get("fetched")}
    path.parent.mkdir(parents=True, exist_ok=True)
    part = path.with_suffix(".json.part")
    part.write_text(json.dumps(listing, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(part, path)
    return {"mps": len(listing["mps"]), "unmatched": unmatched(listing)}


_listed: dict[Path, tuple[float, dict[str, Any]]] = {}


def listed_mps(settings: Any) -> dict[str, Any]:
    """Where MPs Stand's list as this site holds it: the update's copy, or the one kept with the code, with each MP
    by their seat's ``seat_key``. Read again when the update writes a new copy."""
    path = mps_path(settings)
    if not path.is_file():
        path = MPS_SEED
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {"fetched": None, "by_seat": {}}
    kept = _listed.get(path)
    if kept is None or kept[0] != mtime:
        data = _read(path) or {"mps": []}
        kept = (mtime, {"fetched": data.get("fetched"),
                        "by_seat": {seat_key(m["constituency"]): m for m in data["mps"]
                                    if isinstance(m, dict) and m.get("constituency")}})
        _listed[path] = kept
    return kept[1]


# The seats overlapping each council

@lru_cache(maxsize=1)
def _seats() -> dict[str, list[dict[str, str]]]:
    out: dict[str, list[dict[str, str]]] = {}
    if not CONSTITUENCIES.is_file():
        return out
    with open(CONSTITUENCIES, encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            out.setdefault(r["gss"], []).append(r)
    return out


def all_seats() -> dict[str, str]:
    """Every constituency in the lookup, by code: its name."""
    return {r["pcon_code"]: r["pcon_name"] for rows in _seats().values() for r in rows}


def unmatched(listing: dict[str, Any]) -> list[str]:
    """The constituencies overlapping a council that no MP on ``listing`` sits for, by name."""
    held = {seat_key(m["constituency"]) for m in listing.get("mps") or []}
    return sorted(name for name in all_seats().values() if seat_key(name) not in held)


def mps(settings: Any, gss: str) -> dict[str, Any] | None:
    """The MPs whose seats overlap a council (or a strategic authority's area), in order of their seat's name: each
    seat with its MP and their page on Where MPs Stand, or no MP where that site lists none for it. None where the
    lookup has no seats for the council."""
    rows = _seats().get(gss)
    if not rows:
        return None
    listed = listed_mps(settings)
    seats = []
    for r in sorted(rows, key=lambda r: r["pcon_name"]):
        m = listed["by_seat"].get(seat_key(r["pcon_name"]))
        seats.append({"code": r["pcon_code"], "name": r["pcon_name"],
                      "mp": {"name": m["name"], "party": m["party"] or None, "url": mp_url(m["number"], m["slug"])}
                      if m else None})
    return {"site": MPS_NAME, "url": MPS_URL, "fetched": listed["fetched"], "seats": seats}


# The sister sites' spines, from the family kit's shelf

@lru_cache(maxsize=8)
def spine(site: str) -> str:
    """A sister site's spine as the family kit's footer shelf draws it (an SVG in its cloth), or "" without the kit's
    files. Taken from the kit, never drawn here, so it changes when the kit does."""
    for path in SHELF:
        try:
            shelf = path.read_text(encoding="utf-8")
        except OSError:
            continue
        m = re.search(rf'<svg class="wts-spine wts-cloth--{re.escape(site)}"[\s\S]*?</svg>', shelf)
        if m:
            return m.group(0)
    return ""
