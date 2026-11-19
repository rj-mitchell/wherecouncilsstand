"""Who was on a council, in which party, and which party was in control, on any date. All from the stored
attendance, so they are as the council recorded them at its own meetings.

* **Party on the date.** Each meeting's attendance list records every member's party at the time
  (docs/DATA.md). A member's party on a date is the one recorded at their nearest meeting on or before it, or failing
  that the nearest after.
* **Party in control.** A full council meeting's attendance list gives the council's membership on that day. A
  party with more than half the members listed is in overall control; otherwise there is no overall control ("NOC").
  Older lists can be incomplete (docs/DATA.md), so control is read from the meeting with the longest list within
  three months, and is reported as recorded, not as a judgement.
* **A council's directly elected mayor** (Doncaster, Lewisham, North Tyneside, Watford and the rest; decision 27).
  The site holds no list of them: a member is taken to be the council's elected mayor where the council's own
  attendance list says so, by an elected, executive or city mayor's title in their name or role ("Elected Mayor Karen
  Clark", "Chris Cooke - Elected Mayor", "City Mayor Paul Dennett"), or by a name that is "Mayor" and a name, with no
  councillor's title, at a cabinet meeting ("Mayor Ros Jones"), which a civic mayor, who chairs full council, doesn't
  attend. The mayor on a date is the one recorded nearest before it, within three months (or failing that nearest
  after): a council that gave up its mayor (Bristol, 2024) has none after the last meeting one attended. A strategic
  authority's mayor is not read this way (data_static/mayors.csv, decision 19).
"""

from __future__ import annotations

import bisect
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from councils.parse.parties import NAMES, local_name

NOC = "NOC"


def party_key(code: str, label: str) -> str:
    """The party code, except that each local party keeps its own name ("LOCAL:R4GV"): two local groups are not one
    party."""
    return f"LOCAL:{label}" if code == "LOCAL" else (code or "")


@dataclass
class Council:
    """One council's members and control over time."""

    gss: str
    # member_id -> sorted [(date, party code, name)]
    parties: dict[str, list[tuple[date, str, str]]] = field(default_factory=dict)
    # sorted [(date, control code, seats listed)]
    control_by_date: list[tuple[date, str, int]] = field(default_factory=list)
    # sorted [(date, member_id)]: the meetings at which a member was recorded as the council's elected mayor
    mayor_seen: list[tuple[date, str]] = field(default_factory=list)

    def party_on(self, member_id: str, d: date) -> str:
        spells = self.parties.get(member_id)
        if not spells:
            return ""
        i = bisect.bisect_right([s[0] for s in spells], d) - 1
        return spells[max(i, 0)][1]

    def name_of(self, member_id: str) -> str:
        spells = self.parties.get(member_id)
        return spells[-1][2] if spells else ""

    def mayor_on(self, d: date) -> str:
        """The member id of the council's directly elected mayor on a date, or "" where none was recorded within
        three months of it."""
        before = [m for m in self.mayor_seen if m[0] <= d and (d - m[0]).days <= 92]
        if before:
            return before[-1][1]
        after = [m for m in self.mayor_seen if m[0] > d and (m[0] - d).days <= 92]
        return after[0][1] if after else ""

    def control_on(self, d: date) -> str:
        if not self.control_by_date:
            return ""
        dates = [c[0] for c in self.control_by_date]
        i = bisect.bisect_right(dates, d) - 1
        i = max(i, 0)
        # the longest list among full council meetings within three months either side of the one chosen
        near = [c for c in self.control_by_date if abs((c[0] - self.control_by_date[i][0]).days) <= 92]
        return max(near, key=lambda c: (c[2], c[0] <= d))[1]


# an elected mayor's title in a name or a role; never a deputy's, a civic or ceremonial mayor's or a Lord Mayor's
_ELECTED_MAYOR = re.compile(r"\b(?:(?:directly\s+)?elected|executive|city)\s+mayor\b", re.I)
_MAYOR_NAME = re.compile(r"^\s*mayor\s+[A-Z]", re.I)
_NOT_ELECTED_MAYOR = re.compile(r"\b(?:deputy|vice|lord|civic|ceremonial|mayoress|worshipful|councill?or|cllr|chair\w*|"
                                r"speaker)\b", re.I)
_MAYOR_TITLE = re.compile(r"^\s*(?:the\s+)?(?:(?:directly\s+)?elected\s+|executive\s+|city\s+)?mayor\s+|"
                          r"\s*[-,(]\s*(?:(?:directly\s+)?elected|executive|city)\s+mayor\)?\s*$", re.I)


def is_elected_mayor(name: str, role: str, kind: str) -> bool:
    """Whether an attendance row records the council's directly elected mayor (above): an elected, executive or city
    mayor's title in the name or the role, or "Mayor" and a name at a cabinet meeting."""
    if _NOT_ELECTED_MAYOR.search(name) or re.search(r"\b(?:deputy|vice|ceremonial|civic)\b", role, re.I):
        return False
    return bool(_ELECTED_MAYOR.search(name) or _ELECTED_MAYOR.search(role)
                or (kind == "cabinet" and _MAYOR_NAME.match(name)))


def mayor_name(name: str) -> str:
    """A mayor's name without the title: "Elected Mayor Karen Clark", "Chris Cooke - Elected Mayor" -> the name."""
    return _MAYOR_TITLE.sub("", name).strip()


def build(attendance: list[dict[str, Any]], meetings: list[dict[str, Any]]) -> dict[str, Council]:
    """Councils' party and control timelines from stored attendance and meetings rows."""
    kinds = {m["meeting_id"]: m["kind"] for m in meetings}
    out: dict[str, Council] = {}
    spells: dict[tuple[str, str], list[tuple[date, str, str]]] = defaultdict(list)
    seats: dict[tuple[str, str], Counter] = defaultdict(Counter)
    meeting_date: dict[str, date] = {}
    for a in attendance:
        gss = a["gss"]
        out.setdefault(gss, Council(gss))
        if a["member_id"]:
            spells[(gss, a["member_id"])].append((a["date"], party_key(a["party"], a["party_label"]), a["name"]))
            if is_elected_mayor(a["name"] or "", a.get("role") or "", kinds.get(a["meeting_id"]) or ""):
                out[gss].mayor_seen.append((a["date"], a["member_id"]))
        if kinds.get(a["meeting_id"]) == "council" and a["member_id"]:
            seats[(gss, a["meeting_id"])][party_key(a["party"], a["party_label"]) or "?"] += 1
            meeting_date[a["meeting_id"]] = a["date"]
    for (gss, member_id), rows in spells.items():
        rows.sort()
        out[gss].parties[member_id] = rows
    for (gss, meeting_id), count in seats.items():
        total = sum(count.values())
        party, n = count.most_common(1)[0]
        control = party if n * 2 > total and party not in ("?", "IND", "NONE") else NOC
        out[gss].control_by_date.append((meeting_date[meeting_id], control, total))
    for c in out.values():
        c.control_by_date.sort()
        c.mayor_seen = sorted(set(c.mayor_seen))
    return out


MAYOR = "MAYOR:"            # a strategic authority's "control": its mayor's party (decision 19)
NO_SINGLE_PARTY = "SA:NONE"  # a strategic authority without a mayor on the date


def party_name(code: str, gss: str = "") -> str:
    """A party code as words. A local party is named as Open Council Data names it at that council (``gss``). A
    strategic authority's "control" is always labelled as its mayor's party, never as a council's control."""
    if code == NOC:
        return "No overall control"
    if code.startswith(MAYOR):
        return f"Mayor: {party_name(code[len(MAYOR):], gss)}"
    if code == NO_SINGLE_PARTY:
        return "No mayor: no single party"
    if code.startswith("LOCAL:"):
        return local_name(code[6:], gss)
    return NAMES.get(code, code or "Party not recorded")


def recent(c: Council, d: date, days: int = 366) -> list[tuple[str, str]]:
    """(member_id, name) of everyone recorded at the council's meetings within ``days`` of a date."""
    lo, hi = d - timedelta(days=days), d + timedelta(days=days)
    return [(mid, rows[-1][2]) for mid, rows in c.parties.items() if any(lo <= r[0] <= hi for r in rows)]
