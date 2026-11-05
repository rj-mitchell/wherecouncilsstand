"""Turn ranked minutes passages into numbered, citable sources (adapted from Where Countries Stand).

Each source's title tells the model where the passage comes from and who it names, using only facts from the record:
the council, the meeting and its date, the agenda item, the party in overall control of the council on the date, and
the councillors the passage names with their party on the date. Where the item has a named vote, the vote is given as
a further block: who voted which way, and their parties on the date.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from councils import store
from councils.config import Settings
from councils.rank.evidence import evidence_group, group_label
from councils.reference import people

_SENTENCE = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"“(])")
BLOCK_WORDS = 70
KIND_LABEL = {"council": "full council", "cabinet": "cabinet", "policy": "policy committee"}
SIDE_LABEL = {"for": "For", "against": "Against", "abstain": "Abstained"}
# a Scottish division is between a motion and an amendment: its sides are each for something (parse/votes.py)
SCOTTISH_SIDE_LABEL = {"for": "For the motion", "against": "For the amendment", "abstain": "Abstained"}


@dataclass
class Source:
    n: int                      # 1-based number shown as [Source n]
    kind: str                   # "minutes"
    title: str
    url: str
    blocks: list[str]           # citable text, verbatim from the minutes (other people's names removed)
    meta: dict[str, Any] = field(default_factory=dict)

    def search_result(self) -> dict[str, Any]:
        return {
            "type": "search_result",
            "source": self.url,
            "title": self.title,
            "content": [{"type": "text", "text": b} for b in self.blocks],
            "citations": {"enabled": True},
        }

    def card(self) -> dict[str, Any]:
        return {"n": self.n, "kind": self.kind, "title": self.title, "url": self.url, **self.meta}


def fmt_date(iso: str | date) -> str:
    d = date.fromisoformat(iso) if isinstance(iso, str) else iso
    return f"{d.day} {d.strftime('%B %Y')}"


def blocks_for(text: str, words: int = BLOCK_WORDS) -> list[str]:
    """Lines, with long ones split into runs of whole sentences, so a citation points at a few sentences."""
    out: list[str] = []
    for para in [p.strip() for p in text.split("\n") if p.strip()]:
        if len(para.split()) <= words:
            out.append(" ".join(para.split()))
            continue
        buf: list[str] = []
        n = 0
        for sent in _SENTENCE.split(para):
            buf.append(" ".join(sent.split()))
            n += len(sent.split())
            if n >= words:
                out.append(" ".join(buf))
                buf, n = [], 0
        if buf:
            out.append(" ".join(buf))
    return out or [text]


class Lookup:
    """Councillors' names and parties, and named votes, for the councils in a set of records (read once)."""

    def __init__(self, settings: Settings, gss_codes: set[str]):
        root = settings.parquet_dir
        self.people: dict[str, people.Council] = {}
        self.votes: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for gss in gss_codes:
            att = store.parquet.read(root, "attendance", gss)
            meetings = store.parquet.read(root, "meetings", gss)
            self.people[gss] = people.build(att, meetings).get(gss) or people.Council(gss)
            for v in store.parquet.read(root, "votes", gss):
                self.votes[v["item_id"]].append(v)

    def member(self, key: str, d: date) -> str:
        gss, _, mid = key.partition(":")
        c = self.people.get(gss)
        if not c:
            return ""
        name = re.sub(r"^(?:Councillor|Cllr|Cynghorydd)\s+", "", c.name_of(mid)).strip()
        party = people.party_name(c.party_on(mid, d), gss) if c.party_on(mid, d) else "party not recorded"
        return f"Councillor {name} ({party})"

    def vote_blocks(self, item_id: str, gss: str, d: date) -> list[str]:
        rows = self.votes.get(item_id) or []
        if not rows:
            return []
        c = self.people.get(gss)
        out = []
        for vote_id in sorted({r["vote_id"] for r in rows}):
            vs = [r for r in rows if r["vote_id"] == vote_id]
            sides: dict[str, list[str]] = defaultdict(list)
            for r in vs:
                party = people.party_name(c.party_on(r["member_id"], d), gss) if c and r["member_id"] and \
                    c.party_on(r["member_id"], d) else ""
                sides[r["vote"]].append(f"{r['name']} ({party})" if party else r["name"])
            head = "Named vote recorded in these minutes" + (
                " between a motion and an amendment" if vs[0]["question"] == "motion or amendment"
                else f" on the {vs[0]['question']}" if vs[0]["question"] else "")
            head += f", {vs[0]['outcome']}" if vs[0]["outcome"] else ""
            labels = SCOTTISH_SIDE_LABEL if vs[0]["question"] == "motion or amendment" else SIDE_LABEL
            text = head + ". " + " ".join(f"{labels[s]} ({len(names)}): {', '.join(names)}."
                                          for s, names in sides.items())
            if len(sides) == 1:
                # a vote with one side read may be incomplete; say so rather than let it read as the whole vote
                text += (" Only this side is recorded here: the minutes may give the others in a form that could "
                         "not be read, or record none.")
            out.append(text)
        return out


def record_source(n: int, r: dict[str, Any], lookup: Lookup, group_by: str = "control") -> Source:
    d = date.fromisoformat(r["date"])
    control = people.party_name(r["control"], r["gss"]) if r.get("control") else "not recorded"
    named = [lookup.member(m, d) for m in r.get("members") or []]
    title_bits = [
        f"Minutes of {r['council_name']}, {r['committee']} ({KIND_LABEL.get(r['kind'], r['kind'])}), {fmt_date(d)}",
        f"item {r['item_number']} {r['item_title']}".strip() if r.get("item_number") else r["item_title"],
        f"party in overall control of the council on the date: {control}",
    ]
    if named:
        title_bits.append("councillors named in this passage: " + "; ".join(x for x in named if x))
    title = " — ".join(b for b in title_bits if b)
    votes = lookup.vote_blocks(r["record_id"], r["gss"], d)
    blocks = blocks_for(r["text"]) + votes
    meta = {k: r.get(k) for k in ("record_id", "date", "gss", "council_name", "committee", "kind", "item_title",
                                  "item_number", "control", "parties", "heading", "ranking")}
    meta["group"] = group_label(evidence_group(r, group_by), group_by, r)
    meta["text"] = r["text"]
    # the named votes recorded at this item, for the page to show and link to (/votes/<id>)
    meta["votes"] = [{"vote_id": vid, "text": text} for vid, text in
                     zip(sorted({v["vote_id"] for v in lookup.votes.get(r["record_id"], [])}), votes, strict=False)]
    return Source(n, "minutes", title, r["url"], blocks, meta)


def build_sources(settings: Settings, records: list[dict[str, Any]], group_by: str = "control") -> list[Source]:
    lookup = Lookup(settings, {r["gss"] for r in records})
    return [record_source(i, r, lookup, group_by) for i, r in enumerate(records, 1)]
