"""Read named votes and declarations of interest from a council's stored minutes, and store them.

Names are matched first to the members recorded at the meeting, then, because some councils' older attendance lists
are incomplete, to anyone recorded at the council's meetings within a year either side.
"""

from __future__ import annotations

from collections import defaultdict

from councils import store
from councils.config import Settings
from councils.parse import declarations, votes
from councils.parse.votes import Member


def _pool(attendance: list[dict]) -> tuple[dict[str, list[Member]], list[tuple]]:
    present: dict[str, list[Member]] = defaultdict(list)
    everyone = []
    for a in attendance:
        if a["member_type"] not in ("", "U"):
            continue
        m = Member(a["member_id"], a["name"], a["role"])
        everyone.append((a["date"], m))
        if a["attendance"].lower().startswith(("present", "in attendance", "attended")):
            present[a["meeting_id"]].append(m)
    return present, everyone


def _around(everyone: list[tuple], d, present: list[Member]) -> list[Member]:
    ids = {m.member_id for m in present}
    out = list(present)
    for when, m in everyone:
        if m.member_id not in ids and abs((when - d).days) <= 366:
            ids.add(m.member_id)
            out.append(m)
    return out


def run(settings: Settings, gss: str) -> dict:
    root = settings.parquet_dir
    items = store.parquet.read(root, "items", gss)
    attendance = store.parquet.read(root, "attendance", gss)
    present, everyone = _pool(attendance)
    vote_rows, decl_rows = [], []
    for it in items:
        text = it["minutes_text"]
        if not text:
            continue
        here = present.get(it["meeting_id"], [])
        members = None
        for v in votes.parse(text, here):
            if not v.member_id:
                members = members or _around(everyone, it["date"], here)
                v = votes.Vote(v.block, v.side, v.name, votes.Matcher(members).match(v.name), v.outcome,
                               v.question, v.excerpt)
            vote_rows.append({
                "vote_id": f"{it['item_id']}:{v.block}", "item_id": it["item_id"], "meeting_id": it["meeting_id"],
                "gss": gss, "date": it["date"], "year": it["year"], "question": v.question, "outcome": v.outcome,
                "member_id": v.member_id, "name": v.name, "vote": v.side, "excerpt": v.excerpt,
            })
        for dcl in declarations.parse(text, here):
            member_id = dcl.member_id
            if not member_id:
                members = members or _around(everyone, it["date"], here)
                member_id = votes.Matcher(members).match(dcl.name)
            decl_rows.append({
                "item_id": it["item_id"], "meeting_id": it["meeting_id"], "gss": gss, "date": it["date"],
                "year": it["year"], "member_id": member_id, "name": dcl.name, "interest": dcl.interest,
                "excerpt": dcl.excerpt,
            })
    store.parquet.write(root, "votes", gss, vote_rows)
    store.parquet.write(root, "declarations", gss, decl_rows)
    named = len({r["vote_id"] for r in vote_rows})
    return {"gss": gss, "named_votes": named, "vote_rows": len(vote_rows),
            "unmatched_vote_names": sum(1 for r in vote_rows if not r["member_id"]),
            "declarations": len(decl_rows), "unmatched_declarations": sum(1 for r in decl_rows if not r["member_id"])}
