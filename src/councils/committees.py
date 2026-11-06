"""Which committees are in the record: full council, and the cabinet or its equivalent (docs/DECISIONS.md, 3).

* **council**: full council, including its annual, budget and extraordinary meetings.
* **cabinet**: the executive: a cabinet, executive or executive board, including a mayor and cabinet. Not cabinet
  sub-committees, advisory panels or individual cabinet members' decisions.
* **policy**: for councils run by committees, which have no cabinet: the committees their constitution gives the main
  policy and budget decisions. Usually a policy and resources (or strategy and resources) committee. Where a
  council's are named otherwise, they are listed in data_static/committees.csv.

A council that changed its arrangements keeps whichever committees it had at the time, so a council that moved from a
cabinet to committees has cabinet meetings before the change and policy committee meetings after it.

Strategic authorities (decision 18) have kinds of their own:

* **board**: the authority's main decision-making meeting, whatever it is called ("Greater Manchester Combined
  Authority", "Combined Authority Board", "WMCA Board", "Cabinet"), including its budget meetings.
* **mayor**: the mayor's decisions, where the meetings system publishes them as a committee of decisions.
* **scrutiny**: its overview and scrutiny committees. Not joint committees with other bodies, joint health scrutiny,
  police and crime panels (or the boards that hold a mayor to account for policing), informal meetings or briefings.

Each authority's choices are written in data_static/committees.csv, with the reason; the rules below pick up a new or
renamed committee in the meantime. An authority on a council's site (Lancashire's) takes only the committees named
there, so none of the council's own is mistaken for the authority's.
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


AUTHORITY_BOARD = re.compile(
    r"^(?:the )?(?:[\w&'’ ]+ )?(?:mayoral )?combined (?:county )?authority(?: board| committee)?$"
    r"|^(?:the )?(?:mayoral )?combined (?:county )?authority board$",
    re.I,
)
AUTHORITY_SCRUTINY = re.compile(r"\bscrutiny (?:committee|board|sub-committee)\b", re.I)
NOT_SCRUTINY = re.compile(r"\b(?:joint|health|police|crime|informal|briefings?|lep|pool|review of|public scrutiny|"
                          r"agenda|knowledge)\b", re.I)
AUTHORITY_MAYOR = re.compile(r"^(?:the )?(?:mayoral|mayor's) decisions?(?: notices?)?$"
                             r"|^decisions? (?:of|by|taken by) the mayor$", re.I)
AUTHORITY_KINDS = ("board", "mayor", "scrutiny")


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


def _own_name(title: str, gss: str) -> bool:
    """Full council titled with the council's own name, as in Scotland ("Aberdeenshire Council", "City of Edinburgh
    Council", "The Highland Council")."""
    if not gss:
        return False
    from councils.registry import councils

    c = councils().get(gss)
    if not c:
        return False
    return _bare(title) == _bare(c.name)


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z ]", " ", text.lower().replace("&", " and ")).split())


def _named_for(title: str, authority) -> bool:
    """The committee carries the authority's own name, and isn't its shadow (before it was created)."""
    t = _key(title)
    return _key(authority.name) in t and "shadow" not in t


def _guest_authority(title: str, gss: str) -> bool:
    """A committee on a council's site named for a strategic authority published there (Cheshire and Warrington's on
    Cheshire West and Chester's)."""
    from councils.registry import councils

    c = councils().get(gss)
    if not c or not c.modgov_url:
        return False
    return any(a.is_authority and a.modgov_url == c.modgov_url and _key(a.name) in _key(title)
               for a in councils().values())


def _bare(name: str) -> str:
    """A council's name without "the" and its kind of council: "Flintshire County Council" and "Flintshire Council"
    are the same council."""
    s = re.sub(r"^the\s+", "", name.strip(), flags=re.I).lower()
    return re.sub(r"\b(?:county|borough|city|district|metropolitan|royal)\s+(?=(?:\w+\s+)*council$)", "", s).strip()


def kind(title: str, gss: str = "") -> str | None:
    """"council", "cabinet", "policy", or None for every other committee; for a strategic authority, "board",
    "mayor", "scrutiny" or None."""
    t = re.sub(r"\s+", " ", title.replace("&amp;", "&")).strip()
    o = overrides().get((gss, t.lower()))
    if o is not None:
        return o or None
    if _authority(gss):
        return authority_kind(t, gss)
    if _guest_authority(t, gss):
        return None              # a strategic authority's committee on this council's site: read as the authority's
    if COUNCIL.match(t) or _own_name(t, gss):
        return "council"
    if CABINET.match(t):
        return "cabinet"
    if POLICY.match(t):
        return "policy"
    return None


def _authority(gss: str):
    if not gss:
        return None
    from councils.registry import councils

    c = councils().get(gss)
    return c if c is not None and c.is_authority else None


def authority_kind(title: str, gss: str) -> str | None:
    """A strategic authority's committee by the rules, where committees.csv doesn't name it. An authority on a
    council's site takes only the committees named in committees.csv."""
    from councils.registry import shares_site_with_council

    a = _authority(gss)
    if a is None:
        return None
    if shares_site_with_council(a):
        # on a council's site: only committees named for the authority itself ("Cheshire and Warrington Combined
        # Authority", "... Overview and Scrutiny Committee"), never its shadow board, by the rules below
        if not _named_for(title, a):
            return None
    t = re.sub(r"^archived\s*[-–]\s*", "", title, flags=re.I)
    if AUTHORITY_MAYOR.match(t):
        return "mayor"
    if AUTHORITY_SCRUTINY.search(t) and not NOT_SCRUTINY.search(t):
        return "scrutiny"
    if AUTHORITY_BOARD.match(t) or CABINET.match(t) or re.fullmatch(rf"{re.escape(a.reference)} board", t, re.I):
        return "board"
    return None
