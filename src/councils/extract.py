"""Read named votes and declarations of interest from a council's stored minutes, and store them.

Names are matched first to the members recorded at the meeting, then, because some councils' older attendance lists
are incomplete, to anyone recorded at the council's meetings within a year either side.
"""

from __future__ import annotations

import json
import re
from collections import defaultdict

from councils import store
from councils.config import Settings
from councils.parse import declarations, redact, votes
from councils.parse.votes import Member

# Roles in Modern.gov attendance lists that aren't elected councillors: staff, members of the public, guests, and
# co-opted or independent members.
NOT_MEMBERS = re.compile(r"officer|public|guest|invitee|observer|secretary|clerk|administrator|staff|witness|speaker"
                         r"|co-?opt|independent member|church|representative|in attendance|spare", re.I)


def is_councillor(role: str) -> bool:
    return not NOT_MEMBERS.search(role or "")


def _pool(attendance: list[dict]) -> tuple[dict[str, list[Member]], list[tuple]]:
    present: dict[str, list[Member]] = defaultdict(list)
    everyone = []
    for a in attendance:
        if a["member_type"] not in ("", "U") or not is_councillor(a["role"]):
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
    surnames = redact.councillor_surnames({m.name for _, m in everyone})
    vote_rows, decl_rows = [], []
    dropped = 0
    for it in items:
        text = it["minutes_text"]
        if not text:
            continue
        here = present.get(it["meeting_id"], [])
        members = None
        # A vote set out as a table is read from the table; the same names in the text have lost their columns.
        found = votes.parse_tables(json.loads(it["vote_tables"]), here) if it.get("vote_tables") else []
        found = found or votes.parse(text, here)
        if any(not v.member_id for v in found):
            members = members or _around(everyone, it["date"], here)
            matcher = votes.Matcher(members)
            found = [v if v.member_id else votes.Vote(v.block, v.side, v.name, matcher.match(v.name), v.outcome,
                                                       v.question, v.excerpt) for v in found]
        # The same member matched on two sides of one vote: the match is wrong somewhere, so drop it for both.
        sides_by: dict[tuple[int, str], set[str]] = defaultdict(set)
        for v in found:
            if v.member_id:
                sides_by[(v.block, v.member_id)].add(v.side)
        found = [v if not v.member_id or len(sides_by[(v.block, v.member_id)]) == 1 else
                 votes.Vote(v.block, v.side, v.name, "", v.outcome, v.question, v.excerpt) for v in found]
        # A "vote" in which most names match no member was misread from ordinary text: leave it out.
        by_block: dict[int, list] = defaultdict(list)
        for v in found:
            by_block[v.block].append(v)
        for block, vs in by_block.items():
            if sum(1 for v in vs if v.member_id) * 2 < len(vs):
                dropped += 1
                found = [v for v in found if v.block != block]
        for v in found:
            vote_rows.append({
                "vote_id": f"{it['item_id']}:{v.block}", "item_id": it["item_id"], "meeting_id": it["meeting_id"],
                "gss": gss, "date": it["date"], "year": it["year"], "question": v.question, "outcome": v.outcome,
                "member_id": v.member_id, "name": v.name, "vote": v.side,
                "excerpt": redact.redact(v.excerpt, surnames)[0],
            })
        for dcl in declarations.parse(text, here):
            member_id = dcl.member_id
            if not member_id:
                members = members or _around(everyone, it["date"], here)
                member_id = votes.Matcher(members).match(dcl.name)
            decl_rows.append({
                "item_id": it["item_id"], "meeting_id": it["meeting_id"], "gss": gss, "date": it["date"],
                "year": it["year"], "member_id": member_id, "name": dcl.name, "interest": dcl.interest,
                "excerpt": redact.redact(dcl.excerpt, surnames)[0],
            })
    store.parquet.write(root, "votes", gss, vote_rows)
    store.parquet.write(root, "declarations", gss, decl_rows)
    named = len({r["vote_id"] for r in vote_rows})
    return {"gss": gss, "named_votes": named, "dropped_votes": dropped, "vote_rows": len(vote_rows),
            "unmatched_vote_names": sum(1 for r in vote_rows if not r["member_id"]),
            "declarations": len(decl_rows), "unmatched_declarations": sum(1 for r in decl_rows if not r["member_id"])}
