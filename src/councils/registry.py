"""The councils in scope: every principal council in the UK (England, Wales, Scotland and Northern Ireland), from
data_static/councils.csv (built by scripts/build_councils.py)."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from functools import lru_cache

from councils.config import STATIC_DIR

# English regions (ONS codes), and Wales, Scotland and Northern Ireland
REGION_NAMES = {"E12000001": "North East", "E12000002": "North West", "E12000003": "Yorkshire and the Humber",
                "E12000004": "East Midlands", "E12000005": "West Midlands", "E12000006": "East of England",
                "E12000007": "London", "E12000008": "South East", "E12000009": "South West", "wales": "Wales",
                "scotland": "Scotland", "northern_ireland": "Northern Ireland"}
TYPE_NAMES = {"county": "County council", "district": "District council", "unitary": "Unitary council",
              "metropolitan": "Metropolitan borough council", "london_borough": "London borough council",
              "city_of_london": "City of London Corporation", "isles_of_scilly": "Council of the Isles of Scilly"}


@dataclass(frozen=True)
class Council:
    gss: str
    reference: str
    name: str
    nation: str
    type: str
    region: str
    modgov_url: str
    modgov_status: str

    @property
    def short_name(self) -> str:
        """The name without "Council" and its kind: "Babergh", "Mid Suffolk"."""
        n = re.sub(r"\b(London Borough of|Royal Borough of|Borough Council of|City of|Metropolitan Borough Council|"
                   r"Metropolitan District Council|County Borough Council|Borough Council|District Council|"
                   r"County Council|City Council|Council)\b", "", self.name)
        return re.sub(r"\s+", " ", n).strip()


@lru_cache(maxsize=1)
def councils() -> dict[str, Council]:
    with open(STATIC_DIR / "councils.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    return {r["gss"]: Council(r["gss"], r["reference"], r["name"], r["nation"], r["type"], r["region"],
                              r["modgov_url"], r["modgov_status"]) for r in rows}


def get(key: str) -> Council:
    """A council by GSS code, register reference ("ADU") or a unique part of its name."""
    all_ = councils()
    if key in all_:
        return all_[key]
    k = key.lower()
    hits = [c for c in all_.values() if c.reference.lower() == k] or \
           [c for c in all_.values() if k in c.name.lower()]
    if len(hits) != 1:
        raise KeyError(f"{key!r} matches {len(hits)} councils")
    return hits[0]


def site_sharers(council: Council) -> list[Council]:
    """Other councils on the same Modern.gov site (councils that share services publish together)."""
    return [c for c in councils().values()
            if c.modgov_url and c.modgov_url == council.modgov_url and c.gss != council.gss]
