"""Links to the charity's sister sites where their records meet this one's (README, "In the family").

Where Landlords Stand covers social landlords in England, councils among them. Both sites key councils by ONS GSS
code, so a council's page here links to the council's own page there, where it owns homes, and to the area page
listing the landlords with homes in its area. The pages are listed in data_static/landlords_links.csv, built from
that site's published data by scripts/landlords_links.py, so a link never depends on the other site being up.
"""

from __future__ import annotations

import csv
from functools import lru_cache
from typing import Any

from councils.config import STATIC_DIR

LANDLORDS_URL = "https://wherelandlordsstand.com"


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
