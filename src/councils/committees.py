"""Which committees are in the record: full council, and the cabinet or its equivalent (docs/DECISIONS.md, 3).

* **council**: full council, including its annual, budget and extraordinary meetings.
* **cabinet**: the executive: a cabinet, executive or executive board, including a mayor and cabinet. Not cabinet
  sub-committees, advisory panels or individual cabinet members' decisions.
* **policy**: for councils run by committees, which have no cabinet: the committees their constitution gives the main
  policy and budget decisions. Usually a policy and resources (or strategy and resources) committee. Where a
  council's are named otherwise, they are listed in data_static/committees.csv.

A council that changed its arrangements keeps whichever committees it had at the time, so a council that moved from a
cabinet to committees has cabinet meetings before the change and policy committee meetings after it.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache

from councils.config import STATIC_DIR

_PLACE = r"(?:full |county |city |borough |district |town |ordinary |the )?"
COUNCIL = re.compile(
    rf"^(?:meeting of )?(?:the )?{_PLACE}council(?: meeting)?"
    r"(?:\s*[-–(]?\s*(?:annual|budget|extraordinary|special|ordinary|reconvened|adjourned)(?: meeting| council)?\)?)?$"
    rf"|^(?:annual|budget|extraordinary|special|ordinary|reconvened|adjourned) (?:meeting of )?(?:the )?{_PLACE}council"
    r"(?: meeting)?$"
    r"|^full council(?:\s*[-–:]\s*[\w ,'()]+| annual general meeting| agm)$"
    r"|^cyngor(?: llawn| sir)?$",
    re.I,
)
CABINET = re.compile(
    r"^(?:the )?(?:cabinet|executive|executive board|executive cabinet|council executive|policy cabinet"
    r"|mayor and cabinet|mayor's cabinet|mayor & cabinet|leader and cabinet|cabinet \(executive\)|cabinet meeting"
    r"|executive committee|cabinet / executive|cabinet board|cabinet committee)$|^cabinet\s*[-–]\s*(?:special|extraordinary|budget)",
    re.I,
)
POLICY = re.compile(
    r"^(?:the )?(?:corporate |strategic )?(?:policy|strategy) (?:and|&) resources(?: committee)?$"
    r"|^(?:the )?resources (?:and|&) (?:policy|strategy)(?: committee)?$"
    r"|^(?:the )?policy (?:and|&) finance(?: committee)?$|^(?:the )?finance (?:and|&) policy(?: committee)?$"
    r"|^(?:the )?(?:corporate )?policy committee$|^(?:the )?strategy committee$",
    re.I,
)


@lru_cache(maxsize=1)
def overrides() -> dict[tuple[str, str], str]:
    """(GSS code, committee title) -> kind, or "" to leave a committee out, from data_static/committees.csv."""
    path = STATIC_DIR / "committees.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {(r["gss"], r["committee_title"].strip().lower()): r["kind"] for r in csv.DictReader(fh)}


def strip_prefix(title: str, prefixes: list[str]) -> str | None:
    """On a site shared by two councils, a committee's title starts with its council's name. Returns the title without
    it, or None if it names none of ``prefixes``."""
    t = title.strip()
    for p in sorted(prefixes, key=len, reverse=True):
        if t.lower().startswith(p.lower()):
            return t[len(p):].strip(" -–:") or "Council"
    return None


def kind(title: str, gss: str = "") -> str | None:
    """"council", "cabinet", "policy", or None for every other committee."""
    t = re.sub(r"\s+", " ", title.replace("&amp;", "&")).strip()
    o = overrides().get((gss, t.lower()))
    if o is not None:
        return o or None
    if COUNCIL.match(t):
        return "council"
    if CABINET.match(t):
        return "cabinet"
    if POLICY.match(t):
        return "policy"
    return None
