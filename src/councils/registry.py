"""The councils in scope: every principal council in the UK (England, Wales, Scotland and Northern Ireland), from
data_static/councils.csv (built by scripts/build_councils.py), and England's strategic authorities (decision 17), from
data_static/strategic_authorities.csv, kept by hand.

Strategic authorities are listed with councils, under the type ``strategic_authority``, so that every reader, the
store, the index and the pages treat each one as one body, like a council. What only they have is here too: their
statutory kind, their constituent councils with dates (authority_councils.csv) and their mayors (mayors.csv).
"""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache

from councils.config import STATIC_DIR

# English regions (ONS codes), and Wales, Scotland and Northern Ireland
REGION_NAMES = {"E12000001": "North East", "E12000002": "North West", "E12000003": "Yorkshire and the Humber",
                "E12000004": "East Midlands", "E12000005": "West Midlands", "E12000006": "East of England",
                "E12000007": "London", "E12000008": "South East", "E12000009": "South West", "wales": "Wales",
                "scotland": "Scotland", "northern_ireland": "Northern Ireland"}
TYPE_NAMES = {"county": "County council", "district": "District council", "unitary": "Unitary council",
              "metropolitan": "Metropolitan borough council", "london_borough": "London borough council",
              "city_of_london": "City of London Corporation", "strategic_authority": "Strategic authority"}
AUTHORITY = "strategic_authority"
# what the law makes each strategic authority (shown on its page)
KIND_NAMES = {"mayoral_combined_authority": "Mayoral combined authority",
              "combined_authority": "Combined authority",
              "mayoral_combined_county_authority": "Mayoral combined county authority",
              "combined_county_authority": "Combined county authority",
              "greater_london_authority": "The Greater London Authority"}
# its category under the English Devolution and Community Empowerment Act 2026, s. 1
CATEGORY_NAMES = {"established_mayoral": "Established mayoral strategic authority",
                  "mayoral_established_announced": "Mayoral strategic authority (established status announced on 31 "
                                                    "July 2026, not confirmed in force)",
                  "mayoral": "Mayoral strategic authority",
                  "mayoral_no_mayor": "Mayoral strategic authority (no mayor elected yet)",
                  "foundation": "Foundation strategic authority (no mayor)"}
MEMBER_ROLES = {"constituent": "Constituent council", "non_constituent": "Non-constituent council"}


@dataclass(frozen=True)
class Council:
    gss: str
    reference: str
    name: str
    nation: str
    type: str
    region: str
    modgov_url: str         # the base address of the council's meetings site (Modern.gov, CMIS or CoINS)
    modgov_status: str      # "ok", "blocked", "unreachable", "robots" (its robots.txt forbids crawling) or "none"
    system: str = "modgov"  # which reader: "modgov" (sources/modgov.py), "cmis" or "coins"
    # strategic authorities only
    kind: str = ""          # KIND_NAMES
    category: str = ""      # CATEGORY_NAMES
    created: str = ""       # as the instrument or sources give it: "1 April 2014", "February 2025"
    regions: tuple[str, ...] = field(default_factory=tuple)   # every region it spans, its own first
    reason: str = ""        # why it isn't covered, where the status alone doesn't say

    @property
    def is_authority(self) -> bool:
        return self.type == AUTHORITY

    @property
    def withheld(self) -> bool:
        """Marked "robots" in the registry: not read, and anything stored earlier is kept but withheld from the site,
        briefings and the update. Only councils marked by hand, or by scripts/build_councils.py with ``[robots] obey``
        on, are (decision 21); none that is loaded is marked now."""
        return self.modgov_status == "robots"

    @property
    def short_name(self) -> str:
        """The name without "Council" and its kind: "Babergh", "Mid Suffolk", "West Yorkshire"."""
        if self.is_authority:
            return re.sub(r"\s+(?:Mayoral\s+)?Combined(?:\s+County)?\s+Authority$", "", self.name).strip()
        n = re.sub(r"\b(London Borough of|Royal Borough of|Borough Council of|City of|Metropolitan Borough Council|"
                   r"Metropolitan District Council|County Borough Council|Borough Council|District Council|"
                   r"County Council|City Council|Council)\b", "", self.name)
        return re.sub(r"\s+", " ", n).strip()


@lru_cache(maxsize=1)
def councils() -> dict[str, Council]:
    """Every council and strategic authority, by GSS code (or an authority's provisional key)."""
    with open(STATIC_DIR / "councils.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    out = {r["gss"]: Council(r["gss"], r["reference"], r["name"], r["nation"], r["type"], r["region"],
                             r["modgov_url"], r["modgov_status"], r.get("system") or "modgov") for r in rows}
    path = STATIC_DIR / "strategic_authorities.csv"
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            for r in csv.DictReader(fh):
                regions = tuple(x for x in (r.get("regions") or r["region"]).split(";") if x)
                out[r["gss"]] = Council(r["gss"], r["reference"], r["name"], "england", AUTHORITY, r["region"],
                                        r["modgov_url"], r["modgov_status"], r.get("system") or "modgov",
                                        kind=r["kind"], category=r["category"], created=r["created"],
                                        regions=regions or (r["region"],), reason=r.get("reason") or "")
    return out


def get(key: str) -> Council:
    """A council by GSS code, register reference ("ADU") or a unique part of its name."""
    all_ = councils()
    if key in all_ or key.upper() in all_:
        return all_.get(key) or all_[key.upper()]
    k = key.lower()
    hits = [c for c in all_.values() if c.reference.lower() == k] or \
           [c for c in all_.values() if k in c.name.lower()]
    if len(hits) != 1:
        raise KeyError(f"{key!r} matches {len(hits)} councils")
    return hits[0]


def authorities() -> list[Council]:
    return sorted((c for c in councils().values() if c.is_authority), key=lambda c: c.name)


def site_sharers(council: Council) -> list[Council]:
    """Other councils on the same Modern.gov site (councils that share services publish together). A strategic
    authority published on a council's site (Lancashire's on Lancashire County Council's) doesn't count: its
    committees are named in committees.csv instead."""
    return [c for c in councils().values()
            if c.modgov_url and c.modgov_url == council.modgov_url and c.gss != council.gss
            and c.is_authority == council.is_authority]


def shares_site_with_council(authority: Council) -> bool:
    """A strategic authority whose meetings are on a council's Modern.gov site."""
    return any(c.modgov_url == authority.modgov_url and not c.is_authority for c in councils().values()
               if c.modgov_url)


def withheld_codes() -> list[str]:
    """Councils whose stored record, if any, is withheld (Council.withheld)."""
    return sorted(c.gss for c in councils().values() if c.withheld)


# Strategic authorities' constituent councils and mayors ---------------------------------------------------------

@dataclass(frozen=True)
class Membership:
    authority: str
    council: str
    role: str                 # "constituent" or "non_constituent"
    start: date | None        # None: since the authority was created
    end: date | None          # None: still a member


@dataclass(frozen=True)
class Mayor:
    authority: str
    name: str
    party: str                # party code, as elected
    start: date
    end: date | None


def _day(text: str) -> date | None:
    return date.fromisoformat(text) if text else None


@lru_cache(maxsize=1)
def memberships() -> list[Membership]:
    path = STATIC_DIR / "authority_councils.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        return [Membership(r["authority"], r["council"], r["role"], _day(r["from"]), _day(r["to"]))
                for r in csv.DictReader(fh)]


def members_of(authority: str) -> list[Membership]:
    """An authority's constituent and non-constituent councils, constituents first, each in order of name."""
    return sorted((m for m in memberships() if m.authority == authority),
                  key=lambda m: (m.role != "constituent", councils()[m.council].short_name if m.council in councils()
                                 else m.council))


def authorities_of(council: str) -> list[Membership]:
    """The strategic authorities a council belongs to."""
    return [m for m in memberships() if m.council == council]


@lru_cache(maxsize=1)
def mayors() -> list[Mayor]:
    path = STATIC_DIR / "mayors.csv"
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as fh:
        rows = [Mayor(r["authority"], r["name"], r["party"], date.fromisoformat(r["from"]), _day(r["to"]))
                for r in csv.DictReader(fh)]
    return sorted(rows, key=lambda m: (m.authority, m.start))


def mayors_of(authority: str) -> list[Mayor]:
    return [m for m in mayors() if m.authority == authority]


def mayor_on(authority: str, d: date) -> Mayor | None:
    """The mayor in office on a date, if any (from the day of election to the day the office was left)."""
    for m in mayors_of(authority):
        if m.start <= d and (m.end is None or d < m.end):
            return m
    return None
