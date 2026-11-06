"""Strategic authorities' members (decision 20): who each attendee is, their party on the date, and whose names are
shown.

A board's or committee's attendance in Modern.gov lists each member with their role, their party as the authority
recorded it, and the body they represent ("Bradford Council", "Tameside MBC", "West Yorkshire Business Board").
Each member is classed as:

* **the mayor**: the mayor in office on the date (data_static/mayors.csv), with the party they were elected for;
* **constituent** or **non-constituent member**: a councillor representing one of the authority's constituent or
  non-constituent councils on the date (authority_councils.csv), or any other council (non-constituent);
* **substitute**: a councillor attending, or listed, in a member's place;
* **co-opted member**: a councillor co-opted to the committee;
* **appointed member who isn't a councillor**: anyone else listed as a member (a business board's chair, an independent
  person). Decision 9 names only councillors, so their name is replaced with "[name removed]", their member id is left
  out, and their name is removed from the meeting's minutes too.

Officers, staff, guests and members of the public in the list aren't stored, as for councils.

A councillor's party is taken from **their home council's record** on the date where the site has it: the councillor
listed at that council's meetings within a year of the date whose first initial and surname match, if exactly one
does. Otherwise it is the authority's own record ("party_source" says which), which can lag a change of party.
"""

from __future__ import annotations

import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any

from councils import store
from councils.parse import parties
from councils.parse.redact import REMOVED
from councils.parse.votes import _surname_keys
from councils.reference import people
from councils.registry import Council, councils, mayor_on, members_of

# roles of people in the list who aren't members (as extract.NOT_MEMBERS, without co-opted and independent members,
# who are members of an authority's committees)
NOT_MEMBERS = re.compile(r"officer|public|guest|invitee|observer|secretary|clerk|administrator|staff|witness|speaker"
                         r"|representative|in attendance|spare|church", re.I)
COUNCILLOR = re.compile(r"^\s*(?:the\s+)?(?:(?:deputy|city|lord|elected)\s+)*(?:councill?or|cllr\.?|mayor)\b", re.I)
_TITLES = re.compile(r"^\s*(?:(?:GM|the|deputy|city|elected|lord)\s+)*(?:mayor|councill?or|cllr\.?)\s+", re.I)
_BODY_WORDS = re.compile(r"\b(?:the|council|councils|city|county|borough|district|metropolitan|mbc|mdc|cc|bc|dc|of|"
                         r"and|unitary|authority)\b")

ROLE_LABELS = {"mayor": "Mayor", "constituent": "Constituent member", "non_constituent": "Non-constituent member",
               "substitute": "Substitute", "co_opted": "Co-opted member",
               "appointed": "Appointed member (not a councillor)"}


def bare_name(name: str) -> str:
    """"GM Mayor Andy Burnham" -> "Andy Burnham"; "Councillor Susan Hinchcliffe" -> "Susan Hinchcliffe"."""
    return _TITLES.sub("", name).strip()


def _body_key(text: str) -> str:
    t = re.sub(r"[^a-z ]", " ", text.lower().replace("&", " and ").replace("-", " "))
    return " ".join(_BODY_WORDS.sub(" ", t).split())


def home_council(representing: str, authority: str, d: date | None = None) -> str:
    """The GSS code of the council a member represents, from the body the attendance names: the authority's own
    councils first, then any council whose name matches exactly one; "" if none does."""
    key = _body_key(representing)
    if not key:
        return ""
    own = [m.council for m in members_of(authority) if (d is None or ((m.start is None or m.start <= d)
                                                                      and (m.end is None or d < m.end)))]
    for gss in own:
        c = councils().get(gss)
        if c and key in (_body_key(c.short_name), _body_key(c.name)):
            return gss
    hits = [c.gss for c in councils().values() if not c.is_authority
            and key in (_body_key(c.short_name), _body_key(c.name))]
    return hits[0] if len(hits) == 1 else ""


@lru_cache(maxsize=64)
def _home_people(root: str, gss: str, stamp: float) -> people.Council | None:
    att = store.parquet.read(Path(root), "attendance", gss)
    meetings = store.parquet.read(Path(root), "meetings", gss)
    return people.build(att, meetings).get(gss)


def home_party(root: Path, home: str, name: str, d: date) -> str:
    """The member's party on the date at their home council, from its stored attendance; "" if the site doesn't hold
    the council (or it is withheld), or no councillor, or more than one, there has the same first initial and surname
    within a year of the date."""
    c = councils().get(home)
    p = store.parquet.path(root, "attendance", home)
    if c is None or c.withheld or not p.exists():
        return ""
    who = _home_people(str(root), home, p.stat().st_mtime)
    if who is None:
        return ""
    key = _surname_keys(bare_name(name))[1]
    hits = [mid for mid, nm in people.recent(who, d, 366) if _surname_keys(nm)[1] == key]
    return who.party_on(hits[0], d) if len(hits) == 1 else ""


def classify(attendance: list[dict[str, Any]], authority: Council, root: Path) -> tuple[list[dict[str, Any]], list[str]]:
    """An authority meeting's attendance rows with each member's role and party (decision 20), and the names to
    remove from its minutes: those of appointed members who aren't councillors. Officers, staff and guests are left
    out."""
    out, removed = [], []
    for a in attendance:
        keyposts = a.pop("_keyposts", "")
        role = a.get("role") or ""
        if NOT_MEMBERS.search(role):
            continue
        d = a["date"]
        name = a.get("name") or ""
        representing = a.get("representing") or ""
        mayor = mayor_on(authority.gss, d)
        surname = _surname_keys(mayor.name)[0] if mayor else ""
        is_mayor = bool(mayor) and not re.search(r"\bdeputy\b", f"{name} {role} {keyposts}", re.I) and \
            bool(surname) and _surname_keys(bare_name(name))[1] == _surname_keys(mayor.name)[1]
        home = "" if is_mayor else home_council(representing, authority.gss, d)
        councillor = not is_mayor and (bool(COUNCILLOR.match(name)) or bool(home))
        label = a.get("party_label") or ""
        if is_mayor:
            a.update(member_role="mayor", party=mayor.party, party_source="as elected", home_gss="")
        elif councillor:
            constituents = {m.council: m.role for m in members_of(authority.gss)}
            member_role = ("substitute" if re.search(r"substitute", role, re.I) else
                           "co_opted" if re.search(r"co-?opt", role, re.I) else
                           "constituent" if constituents.get(home) == "constituent" else "non_constituent")
            party = home_party(root, home, name, d) if home else ""
            a.update(member_role=member_role, home_gss=home,
                     party=party or parties.normalise(label, authority.gss),
                     party_source="home council" if party else ("authority" if label else ""))
        else:
            if bare_name(name):
                removed.append(bare_name(name))
            a.update(member_role="co_opted" if re.search(r"co-?opt", role, re.I) else "appointed", name=REMOVED,
                     member_id="", party="", party_label="", party_source="", home_gss="", ward="")
        out.append(a)
    return out, sorted(set(removed), key=len, reverse=True)


def remove_names(text: str, names: list[str]) -> str:
    """Remove appointed members' names from minutes: "Mandy Ridyard", "Ms Ridyard", "M Ridyard"."""
    for full in names:
        words = full.split()
        if not words:
            continue
        surname = re.escape(words[-1])
        patterns = [r"\b" + r"\s+".join(re.escape(w) for w in words) + r"\b",
                    rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame)\.?\s+(?:{re.escape(words[0])}\s+)?{surname}\b",
                    rf"\b{re.escape(words[0][0])}\.?\s+{surname}\b" if len(words) > 1 else None]
        for p in patterns:
            if p:
                text = re.sub(p, REMOVED, text)
    return text


def control_key(gss: str, d: date) -> str:
    """What stands for "control" at a strategic authority on a date (decision 19): "MAYOR:LAB" for a mayor of that
    party, or "SA:NONE" (no single party) where there is no mayor."""
    m = mayor_on(gss, d)
    return f"{people.MAYOR}{m.party}" if m else people.NO_SINGLE_PARTY
