"""What minutes text and agenda items' titles go through before they are searched, shown or given to the model, in one
place (docs/DECISIONS.md, 9):

1. each declaration of interest is cut down to who declared, the item and the kind of interest, without the reason
   (parse/declarations.py, ``without_reasons``);
2. the names of people who aren't councillors are removed (parse/redact.py);
3. the names and phrases on the owner's suppression list are removed (suppress.py).

The search index is built with them (index/build.py). They are applied again as a page is served or a briefing's
sources are made, so a change to the rules or to the suppression list reaches readers and the model at once, before
the index is built again; and to saved and cached briefings as they are shown, which were written before.
"""

from __future__ import annotations

import copy
from functools import lru_cache
from pathlib import Path
from typing import Any

from councils import store, suppress
from councils.parse import declarations, redact


def minutes_text(text: str, surnames: set[str], suppressions: suppress.Suppressions, gss: str, item_id: str = "",
                 title: str = "") -> str:
    """Minutes text as it may be searched, shown or given to the model."""
    if not text:
        return text
    text = declarations.without_reasons(text, title)
    text, _ = redact.redact(text, surnames)
    return suppressions.apply(text, gss, item_id)


def item_title(title: str, surnames: set[str], suppressions: suppress.Suppressions, gss: str,
               item_id: str = "") -> str:
    """An agenda item's title as it may be searched, shown or given to the model ("Presentation of CIL Petition –
    Mr Steve Dally" names the petitioner)."""
    if not title:
        return title
    return suppressions.apply(redact.redact(title, surnames)[0], gss, item_id)


def _attendance_stamp(root: Path, gss: str) -> float:
    p = store.parquet.path(root, "attendance", gss)
    return p.stat().st_mtime if p.exists() else 0.0


@lru_cache(maxsize=512)
def _surnames(root: Path, gss: str, _stamp: float) -> frozenset[str]:
    attendance = store.parquet.read(root, "attendance", gss)
    return frozenset(redact.councillor_surnames({a["name"] for a in attendance if a.get("member_id")}))


def surnames(root: Path, gss: str) -> set[str]:
    """The surnames of a council's councillors, from its attendance lists (read again when they change)."""
    return set(_surnames(Path(root), gss, _attendance_stamp(Path(root), gss)))


# What in a saved briefing's events is never minutes text or a name: left as it is
_LEAVE = {"type", "url", "source", "gss", "record_id", "vote_id", "date", "id", "kind", "control", "parties", "group",
          "status", "n", "ranking", "item_number", "council_name", "committee", "sources", "question", "plan"}


def briefing_events(events: list[dict[str, Any]], root: Path, data_dir: Path) -> list[dict[str, Any]]:
    """A saved or cached briefing's events as they may be shown now: its sources' minutes text and titles, and its
    own words, through the same steps as a new briefing's (written before a rule or an entry on the suppression
    list was added, it may hold what they now remove). The reader's question and the plan are left as they are."""
    sup = suppress.load(data_dir)
    councils = sorted({card.get("gss") for e in events if e.get("type") == "sources"
                       for card in e.get("sources") or [] if card.get("gss")})
    names: dict[str, set[str]] = {g: surnames(root, g) for g in councils}
    everyone = set().union(*names.values()) if names else set()

    def own_words(text: str) -> str:
        # what the model wrote: a name it repeated from the minutes before a rule removed it, and any suppressed
        return sup.apply_any(redact.redact(text, everyone)[0], councils) if text else text

    def walk(value: Any, fix) -> Any:
        if isinstance(value, str):
            return fix(value)
        if isinstance(value, list):
            return [walk(v, fix) for v in value]
        if isinstance(value, dict):
            return {k: v if k in _LEAVE else walk(v, fix) for k, v in value.items()}
        return value

    def card(c: dict[str, Any]) -> dict[str, Any]:
        gss, rid = c.get("gss") or "", c.get("record_id") or ""
        here = names.get(gss, set())
        out = {}
        for k, v in c.items():
            if k == "text" and isinstance(v, str):
                out[k] = minutes_text(v, here, sup, gss, rid, c.get("item_title") or "")
            elif k == "votes":       # councillors' names and how they voted: only the suppression list applies
                out[k] = walk(v, lambda s: sup.apply(s, gss, rid))
            elif k in _LEAVE:
                out[k] = v
            else:
                out[k] = walk(v, lambda s: item_title(s, here, sup, gss, rid))
        return out

    out = []
    for e in copy.deepcopy(events):
        if e.get("type") == "sources":
            e = {**e, "sources": [card(c) for c in e.get("sources") or []]}
        elif e.get("type") in ("final", "text"):
            e = {k: v if k in _LEAVE else walk(v, own_words) for k, v in e.items()}
        out.append(e)
    return out

