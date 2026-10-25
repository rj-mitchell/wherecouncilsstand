"""Choose a balanced evidence set for synthesis, and summarise it (adapted from Where Countries Stand).

A briefing that says "councils under Labour control did X, councils under no overall control Y" needs evidence from
each, not the twelve best-scoring items (often six from one council). Selection is deterministic:

1. drop candidates far weaker than the best match (``min_relevance_ratio``);
2. cap items per council and per meeting (``max_per_council``, ``max_per_meeting``);
3. take the best remaining item from each group in turn (groups ordered by their best score), then fill any remaining
   places by score.

How items are grouped (``group_by``), always by facts recorded on the date and the same way for every party:

* ``control`` (default): the party in overall control of the council on the date, or no overall control;
* ``region``: the council's region (and Wales);
* ``type``: the kind of council (county, district, unitary, metropolitan borough, London borough);
* ``council``: each council on its own.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from councils.rank.composite import Scored
from councils.reference.people import party_name

TYPE_LABELS = {"county": "County councils", "district": "District councils", "unitary": "Unitary councils",
               "metropolitan": "Metropolitan borough councils", "london_borough": "London borough councils",
               "city_of_london": "City of London", "isles_of_scilly": "Isles of Scilly"}
GROUP_BY = ("control", "region", "type", "council")
CONTROLLED_BY = {"LAB": "Labour", "CON": "the Conservatives", "LD": "the Liberal Democrats", "GRN": "the Greens",
                 "REF": "Reform UK", "PC": "Plaid Cymru", "UKIP": "UKIP", "LIB": "the Liberal Party",
                 "YP": "Your Party", "IND": "independents"}


def evidence_group(rec: dict[str, Any], group_by: str = "control") -> str:
    """Group key for a record (as returned by the engine, or a passage row)."""
    if group_by == "region":
        return rec.get("region") or rec.get("nation") or "other"
    if group_by == "type":
        return rec.get("council_type") or "other"
    if group_by == "council":
        return rec.get("gss") or "other"
    return rec.get("control") or "unknown"


def group_label(key: str, group_by: str, rec: dict[str, Any] | None = None) -> str:
    if group_by == "region":
        return "Wales" if key == "wales" else key.replace("-", " ").title()
    if group_by == "type":
        return TYPE_LABELS.get(key, key)
    if group_by == "council":
        return (rec or {}).get("council_name") or key
    if key == "unknown":
        return "Control not recorded"
    if key == "NOC":
        return "Councils under no overall control"
    return f"Councils controlled by {CONTROLLED_BY.get(key, party_name(key, (rec or {}).get('gss', '')))}"


def select_evidence(scored: list[Scored], k: int, *, group_by: str = "control", max_per_council: int = 2,
                    max_per_meeting: int = 1, min_relevance_ratio: float = 0.25) -> list[Scored]:
    if not scored:
        return []
    best_rel = max(s.relevance for s in scored)
    pool = [s for s in scored if s.relevance >= best_rel * min_relevance_ratio]
    groups: dict[str, list[Scored]] = defaultdict(list)
    for s in pool:  # already in score order
        groups[evidence_group(s.candidate.data, group_by)].append(s)
    order = sorted(groups, key=lambda g: -groups[g][0].score)
    chosen: list[Scored] = []
    taken: set[str] = set()
    per_council: Counter[str] = Counter()
    per_meeting: Counter[str] = Counter()

    def take(s: Scored) -> bool:
        d = s.candidate.data
        council = d.get("gss") or ""
        meeting = s.candidate.record_id.rsplit(":", 1)[0]
        if s.candidate.record_id in taken or per_council[council] >= max_per_council or \
                per_meeting[meeting] >= max_per_meeting:
            return False
        chosen.append(s)
        taken.add(s.candidate.record_id)
        per_council[council] += 1
        per_meeting[meeting] += 1
        return True

    progress = True
    while len(chosen) < k and progress:
        progress = False
        for g in order:
            for s in groups[g]:
                if take(s):
                    progress = True
                    break
            if len(chosen) >= k:
                break
    for s in pool:  # fill by score if the groups ran dry
        if len(chosen) >= k:
            break
        take(s)
    chosen.sort(key=lambda s: (-s.score, s.candidate.record_id))
    return chosen


def evidence_summary(records: list[dict[str, Any]], group_by: str = "control") -> dict[str, Any]:
    """Deterministic description of the evidence base (shown to the reader, not model-written)."""
    groups: Counter[str] = Counter()
    kinds: Counter[str] = Counter()
    councils: set[str] = set()
    meetings: set[str] = set()
    dates = []
    for r in records:
        groups[group_label(evidence_group(r, group_by), group_by, r)] += 1
        kinds[r.get("kind") or ""] += 1
        councils.add(r.get("gss") or r["record_id"])
        meetings.add(r["record_id"].rsplit(":", 1)[0])
        dates.append(r["date"])
    return {
        "records": len(records),
        "councils": len(councils),
        "meetings": len(meetings),
        "date_from": min(dates) if dates else None,
        "date_to": max(dates) if dates else None,
        "groups": dict(groups.most_common()),
        "kinds": dict(kinds.most_common()),
    }
