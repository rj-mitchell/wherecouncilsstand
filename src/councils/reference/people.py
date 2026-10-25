"""Who was on a council, in which party, and which party was in control, on any date. All from the stored
attendance, so they are as the council recorded them at its own meetings.

* **Party on the date.** Each meeting's attendance list records every member's party at the time
  (docs/DATA.md). A member's party on a date is the one recorded at their nearest meeting on or before it, or failing
  that the nearest after.
* **Party in control.** A full council meeting's attendance list gives the council's membership on that day. A
  party with more than half the members listed is in overall control; otherwise there is no overall control ("NOC").
  Older lists can be incomplete (docs/DATA.md), so control is read from the meeting with the longest list within
  three months, and is reported as recorded, not as a judgement.
"""

from __future__ import annotations

import bisect
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any

from councils.parse.parties import NAMES

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

    def party_on(self, member_id: str, d: date) -> str:
        spells = self.parties.get(member_id)
        if not spells:
            return ""
        i = bisect.bisect_right([s[0] for s in spells], d) - 1
        return spells[max(i, 0)][1]

    def name_of(self, member_id: str) -> str:
        spells = self.parties.get(member_id)
        return spells[-1][2] if spells else ""

    def control_on(self, d: date) -> str:
        if not self.control_by_date:
            return ""
        dates = [c[0] for c in self.control_by_date]
        i = bisect.bisect_right(dates, d) - 1
        i = max(i, 0)
        # the longest list among full council meetings within three months either side of the one chosen
        near = [c for c in self.control_by_date if abs((c[0] - self.control_by_date[i][0]).days) <= 92]
        return max(near, key=lambda c: (c[2], c[0] <= d))[1]


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
    return out


def party_name(code: str) -> str:
    if code == NOC:
        return "No overall control"
    if code.startswith("LOCAL:"):
        return code[6:]
    return NAMES.get(code, code or "Party not recorded")


def recent(c: Council, d: date, days: int = 366) -> list[tuple[str, str]]:
    """(member_id, name) of everyone recorded at the council's meetings within ``days`` of a date."""
    lo, hi = d - timedelta(days=days), d + timedelta(days=days)
    return [(mid, rows[-1][2]) for mid, rows in c.parties.items() if any(lo <= r[0] <= hi for r in rows)]
