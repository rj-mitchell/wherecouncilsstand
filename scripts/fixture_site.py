"""A small made-up record for running the site without the real data: three councils' meetings, members and named
votes, one made-up statement beside a vote, and one strategic authority's board and scrutiny meetings (South
Yorkshire, of which Barnsley is a constituent council), indexed with the offline test embedder. Used by CI's
accessibility check (scripts/a11y.mjs), and handy for working on the pages.

    uv run python scripts/fixture_site.py /tmp/councils-fixture
    COUNCILS_DATA_DIR=/tmp/councils-fixture uv run councils serve

A folder this script made before is emptied first; any other folder must be empty. Nothing here is real minutes: the councils are real, the meetings and votes are not.
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import date
from pathlib import Path

BARNSLEY, GUILDFORD, CARDIFF = "E08000038", "E07000209", "W06000015"
SOUTH_YORKSHIRE = "E47000002"
FIXTURE_MARK = "FIXTURE.txt"


def meeting(gss: str, mid: int, d: date, kind: str = "council") -> dict:
    title = {"council": "Full Council", "cabinet": "Cabinet", "policy": "Policy and Resources Committee",
             "board": "Mayoral Combined Authority Board", "scrutiny": "Overview and Scrutiny Committee"}[kind]
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "council": gss,
            "committee_id": 1 if kind in ("council", "board") else 2,
            "committee_title": title, "kind": kind, "date": d, "year": d.year, "status": "", "location": "",
            "webcast": False, "minutes_published": True, "items": 1, "items_with_minutes": 1, "earlier_minutes": "",
            "minutes_document": "", "attendees": 3, "url": f"https://example.org/{gss}/meetings/{mid}"}


def item(gss: str, mid: int, iid: int, d: date, title: str, text: str) -> dict:
    return {"item_id": f"{gss}:{mid}:{iid}", "meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year,
            "position": 0, "number": f"{iid}.", "title": title, "agenda_text": "", "minutes_text": text,
            "minutes_source": "html", "vote_tables": "", "is_decision": False, "is_restricted": False,
            "is_call_in": False, "declaration_count": 0, "documents": 0,
            "url": f"https://example.org/{gss}/items/{iid}"}


def member(gss: str, mid: int, d: date, member_id: str, name: str, party: str) -> dict:
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year, "member_id": member_id,
            "member_type": "U", "name": name, "role": "Committee Member", "attendance": "Present, as expected",
            "party_label": party, "party": party, "ward": ""}


def authority_members(mid: int, d: date) -> list[dict]:
    """South Yorkshire's board: its mayor, Barnsley's leader (as in Barnsley's own fixture, so his party comes from
    there), and an appointed member who isn't a councillor, whose name isn't kept (decision 20)."""
    base = {"meeting_id": f"{SOUTH_YORKSHIRE}:{mid}", "gss": SOUTH_YORKSHIRE, "date": d, "year": d.year,
            "member_type": "U", "attendance": "Present, as expected", "ward": ""}
    return [
        {**base, "member_id": "101", "name": "Mayor Oliver Coppard", "role": "Chair", "party_label": "LAB",
         "party": "LAB", "member_role": "mayor", "party_source": "as elected", "representing": "SYMCA",
         "home_gss": ""},
        {**base, "member_id": "102", "name": "Councillor Steve Houghton", "role": "Committee Member",
         "party_label": "LAB", "party": "LAB", "member_role": "constituent", "party_source": "home council",
         "representing": "Barnsley Council", "home_gss": BARNSLEY},
        {**base, "member_id": "", "name": "[name removed]", "role": "Committee Member", "party_label": "",
         "party": "", "member_role": "appointed", "party_source": "", "representing": "Business Advisory Board",
         "home_gss": ""},
    ]


AUTHORITY_ITEMS = [
    ("board", "Bus Franchising", "The Mayor introduced the report on bus franchising across South Yorkshire. RESOLVED "
                                 "that the Board approve the move to a franchised bus network."),
    ("board", "Mayoral Budget and Precept 2025/26", "The Board considered the Mayor's budget and the mayoral precept. "
                                                    "RESOLVED that the budget be approved."),
    ("scrutiny", "Bus Services Performance", "Councillor Houghton asked about bus punctuality. The Committee noted the "
                                             "report on bus services."),
]


def vote(gss: str, mid: int, iid: int, d: date, sides: list[tuple[str, str, str]], outcome: str) -> list[dict]:
    excerpt = (f"A recorded vote was taken. For: {', '.join(n for _, n, s in sides if s == 'for')}. Against: "
               f"{', '.join(n for _, n, s in sides if s == 'against')}. The motion was {outcome}.")
    return [{"vote_id": f"{gss}:{mid}:{iid}:0", "item_id": f"{gss}:{mid}:{iid}", "meeting_id": f"{gss}:{mid}",
             "gss": gss, "date": d, "year": d.year, "question": "motion", "outcome": outcome, "member_id": m,
             "name": n, "vote": side, "excerpt": excerpt} for m, n, side in sides]


COUNCILLORS = {
    BARNSLEY: [("1", "Councillor Hannah Kitching", "LD"), ("2", "Councillor Steve Houghton", "LAB"),
               ("3", "Councillor Robin Franklin", "LAB"), ("4", "Councillor Peter Fielding", "REF"),
               ("5", "Councillor Sarah Tattersall", "LAB")],
    GUILDFORD: [("7", "Councillor Julia McShane", "LD"), ("8", "Councillor Tim Anderson", "LD"),
                ("9", "Councillor Paul Spooner", "CON"), ("10", "Councillor Ruth Brothwell", "GRN"),
                ("11", "Councillor Carla Morson", "LD")],
    CARDIFF: [("20", "Councillor Huw Thomas", "LAB"), ("21", "Councillor Rhys Taylor", "LD"),
              ("22", "Councillor Adrian Robson", "CON"), ("23", "Councillor Owen Jones", "LAB"),
              ("24", "Councillor Andrea Gibson", "PC")],
}
ITEMS = {
    BARNSLEY: [("Notice of Motion - Weekly Bin Collections",
                "Councillor Kitching moved that weekly bin collections be restored. Upon being put to the vote the "
                "motion was lost."),
               ("Budget 2025/26", "The Cabinet recommended the revenue budget and council tax for 2025/26. RESOLVED "
                                  "that the budget be approved."),
               ("Library Strategy", "The Cabinet considered the library strategy, including community libraries. "
                                    "RESOLVED that the strategy be adopted.")],
    GUILDFORD: [("Waste and Recycling Strategy",
                 "Councillor McShane introduced the waste and recycling strategy, including fortnightly bin "
                 "collections. RESOLVED that the strategy be adopted."),
                ("Climate Emergency Motion", "Councillor Anderson moved that the council declare a climate emergency. "
                                             "Upon being put to the vote the motion was carried."),
                ("Public Toilets", "The Executive considered the future of public toilets in the town centre.")],
    CARDIFF: [("Second Homes Council Tax Premium",
               "The Cabinet considered a council tax premium on second homes and long-term empty homes. RESOLVED that "
               "the premium be set at 100 per cent."),
              ("Bus Services", "Councillor Thomas reported on supported bus services. RESOLVED that the report be noted."),
              ("Motion on Local Libraries", "Councillor Taylor moved that no branch library be closed. Upon being put "
                                            "to the vote the motion was carried.")],
}


def build(folder: Path) -> None:
    from councils import store
    from councils.config import load_settings
    from councils.embed.base import HashingEmbedder
    from councils.index.build import Indexer, embed_pending

    if folder.exists() and any(folder.iterdir()):
        if not (folder / FIXTURE_MARK).exists():  # never empty a folder this script didn't make
            sys.exit(f"{folder} isn't empty and wasn't made by this script: give an empty or new folder")
        shutil.rmtree(folder)
    folder.mkdir(parents=True, exist_ok=True)
    (folder / FIXTURE_MARK).write_text("Made by scripts/fixture_site.py: a made-up record, safe to delete.\n")
    (folder / "settings.local.toml").write_text('[embedding]\nbackend = "hashing"\ndim = 64\n')
    settings = load_settings()
    root = settings.parquet_dir
    dates = [date(2024, 7, 18), date(2025, 2, 26), date(2025, 10, 15)]
    for gss, items in ITEMS.items():
        meetings, rows, attendance, votes = [], [], [], []
        for n, (d, (title, text)) in enumerate(zip(dates, items, strict=True), start=1):
            kind = "council" if n != 2 else "cabinet"
            meetings.append(meeting(gss, n, d, kind))
            rows.append(item(gss, n, n * 10, d, title, text))
            attendance += [member(gss, n, d, *c) for c in COUNCILLORS[gss]]
            if "vote" in text:
                people = COUNCILLORS[gss]
                won = "carried" in text
                sides = [(m, name.removeprefix("Councillor ").split()[-1],
                          "for" if (i < 3) == won else ("abstain" if i == 4 else "against"))
                         for i, (m, name, _) in enumerate(people)]
                votes += vote(gss, n, n * 10, d, sides, "carried" if won else "lost")
        store.parquet.write(root, "meetings", gss, meetings)
        store.parquet.write(root, "items", gss, rows)
        store.parquet.write(root, "attendance", gss, attendance)
        store.parquet.write(root, "votes", gss, votes)
    meetings, rows, attendance = [], [], []
    for n, (d, (kind, title, text)) in enumerate(zip(dates, AUTHORITY_ITEMS, strict=True), start=1):
        meetings.append(meeting(SOUTH_YORKSHIRE, n, d, kind))
        rows.append(item(SOUTH_YORKSHIRE, n, n * 10, d, title, text))
        attendance += authority_members(n, d) if kind == "board" else authority_members(n, d)[1:2]
    store.parquet.write(root, "meetings", SOUTH_YORKSHIRE, meetings)
    store.parquet.write(root, "items", SOUTH_YORKSHIRE, rows)
    store.parquet.write(root, "attendance", SOUTH_YORKSHIRE, attendance)
    store.parquet.write(root, "votes", SOUTH_YORKSHIRE, [])
    idx = Indexer(settings)
    idx.index_all()
    embed_pending(settings, idx.index, idx.state, HashingEmbedder(64))
    # a statement under the right of reply (decision 22), published beside Barnsley's named vote and so on its page
    # too: plainly made up, from no real person, so the pages can be checked with one shown
    from councils.api.state import StateDB

    state = StateDB(settings.data_dir / "state.db")
    sid = state.add_statement(
        f"/votes/{BARNSLEY}:1:10:0", BARNSLEY, "An Example Councillor", "A made-up statement, for testing the site",
        "This is a made-up statement, to show how one is set beside the record. A real one would be up to 150 words, "
        "in its author's own name, about this vote.\n\nIt would point to the record where it could.",
        "https://example.org/minutes", "")
    state.publish_statement(sid)
    (folder / "updates.jsonl").write_text(json.dumps(
        {"finished": "2025-10-16T03:41:00", "minutes": 21.5, "councils": 3, "changed": 1, "new_meetings": 1,
         "failed": [], "needs_attention": False}) + "\n")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit("usage: uv run python scripts/fixture_site.py <empty data folder>")
    target = Path(sys.argv[1]).resolve()
    import os

    os.environ["COUNCILS_DATA_DIR"] = str(target)
    build(target)
    print(f"A made-up record for three councils and a strategic authority is in {target}. Run the site on it with:\n"
          f"  COUNCILS_DATA_DIR={target} uv run councils serve")
