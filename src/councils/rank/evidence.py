"""Choose a balanced evidence set for synthesis, and summarise it (adapted from Where Countries Stand).

A briefing that says "councils under Labour control did X, councils under no overall control Y" needs evidence from
each, not the twelve best-scoring items (often six from one council). Selection is deterministic:

1. drop candidates far weaker than the best match (``min_relevance_ratio``);
2. cap items per council and per meeting (``max_per_council``, ``max_per_meeting``);
3. take the best remaining item from each group in turn (groups ordered by their best score), then fill any remaining
   places by score.

How items are grouped (``group_by``), always by facts recorded on the date and the same way for every party:

* ``control`` (default): the party in overall control of the council on the date, or no overall control; a strategic
  authority by its mayor's party on the date, or without a mayor, never in a council's group (decision 19);
* ``region``: the council's region (and Wales);
* ``type``: the kind of council (county, district, unitary, metropolitan borough, London borough);
* ``council``: each council on its own.
"""

from __future__ import annotations

from collections import Counter
from typing import Any

from wts_core.checks import round_robin

from councils.rank.composite import Scored
from councils.reference.people import party_name

TYPE_LABELS = {"county": "County councils", "district": "District councils", "unitary": "Unitary councils",
               "metropolitan": "Metropolitan borough councils", "london_borough": "London borough councils",
               "city_of_london": "City of London", "strategic_authority": "Strategic authorities"}
GROUP_BY = ("control", "region", "type", "council")
MAYOR_OF = {"LAB": "a Labour", "CON": "a Conservative", "LD": "a Liberal Democrat", "GRN": "a Green",
            "REF": "a Reform UK", "IND": "an independent"}
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
        from councils.registry import REGION_NAMES

        return REGION_NAMES.get(key, key)
    if group_by == "type":
        return TYPE_LABELS.get(key, key)
    if group_by == "council":
        return (rec or {}).get("council_name") or key
    if key == "unknown":
        return "Control not recorded"
    if key == "NOC":
        return "Councils under no overall control"
    if key.startswith("MAYOR:"):
        party = key[6:]
        return f"Strategic authorities with {MAYOR_OF.get(party) or 'a ' + party_name(party)} mayor"
    if key == "SA:NONE":
        return "Strategic authorities without a mayor"
    return f"Councils controlled by {CONTROLLED_BY.get(key, party_name(key, (rec or {}).get('gss', '')))}"


def select_evidence(scored: list[Scored], k: int, *, group_by: str = "control", max_per_council: int = 2,
                    max_per_meeting: int = 1, min_relevance_ratio: float = 0.25) -> list[Scored]:
    """The balanced choice: what is far weaker than the best match is dropped, and the groups then take turns (the
    Where They Stand sites' shared round robin, ``wts_core.checks.round_robin``), with this site's caps: so many
    items from one council, and so many from one meeting."""
    if not scored:
        return []
    best_rel = max(s.relevance for s in scored)
    pool = [s for s in scored if s.relevance >= best_rel * min_relevance_ratio]      # already in score order
    return round_robin(
        pool, k,
        group_of=lambda s: evidence_group(s.candidate.data, group_by),
        key_of=lambda s: s.candidate.record_id,
        score_of=lambda s: s.score,
        caps=((lambda s: s.candidate.data.get("gss") or "", max_per_council),
              (lambda s: s.candidate.record_id.rsplit(":", 1)[0], max_per_meeting)))


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
