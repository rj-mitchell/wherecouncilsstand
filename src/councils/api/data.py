"""What the council and vote pages show, read from the store.

The nightly update rewrites the store one council at a time while the site is serving, so what is kept is kept by
what it was made from. The directory (and the list of every named vote, for the sitemap) is built from every
council's files and built again when any of them changes. What a council's own pages show (its page, its named
votes and their labels, its members' parties) is built when first asked for and kept until that council's own
files change, or the suppression list does: a change to one council never throws away another's. Until November
2026 any change threw away every council's, so during the update every page was built afresh, again and again,
while search engines' crawlers read the named votes (docs/OPERATIONS.md, "Built to keep working"). What is hidden
while a concern is decided is never kept here: the routes leave it out on each request (app.py)."""

from __future__ import annotations

import os
import re
import threading
from collections import Counter, defaultdict
from collections.abc import Callable, Hashable
from datetime import date
from typing import Any, TypeVar

import duckdb
import pyarrow.parquet as pq

from councils import authority, scrub, sisters, store, suppress
from councils.api import titles
from councils.config import Settings
from councils.reference import people
from councils.registry import (
    CATEGORY_NAMES,
    KIND_NAMES,
    MEMBER_ROLES,
    REGION_NAMES,
    TYPE_NAMES,
    Council,
    authorities_of,
    councils,
    mayor_on,
    mayors_of,
    members_of,
    withheld_codes,
)

KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee", "board": "Board",
              "mayor": "Mayor’s decisions", "scrutiny": "Overview and scrutiny"}
AUTHORITY_KINDS = ("board", "mayor", "scrutiny")

# How fully each council is covered, for the councils page: "not_yet" (not loaded), "partial" (loaded with a gap)
# or "full". It describes the site's reading of the council's record, never the council.
NOT_LOADED = {
    "robots": "Its meetings site asks automated readers not to visit (robots.txt).",
    "blocked": "Its meetings site refuses automated requests.",
    "unreachable": "Its meetings site couldn’t be reached.",
    "none": "It doesn’t publish its minutes through a system we can read yet.",
    "ok": "Its meetings site answers, but it hasn’t been loaded yet or failed to load.",
}
MIN_WITH_MINUTES = 0.7          # share of meetings with minutes text
STALE_DAYS = 120                # no meeting for this long
LATE_START = date(2019, 12, 31) # records that begin after this (May 2018 is the start)
MIN_PARTY = 0.8                 # share of attendance with a party
# councils created since May 2018, whose records start later as a matter of course (E06000058 BCP ... E06000066
# Somerset)
NEW_COUNCILS = {f"E060000{n}" for n in range(58, 67)}


def coverage(row: dict[str, Any], attendance: int = 0, with_party: int = 0, today: date | None = None
             ) -> tuple[str, list[str]]:
    """("full" | "partial" | "not_yet", the reasons in plain words)."""
    today = today or date.today()
    authority = row.get("type") == "strategic_authority"
    if not row.get("loaded"):
        why = [row.get("reason") or NOT_LOADED.get(row.get("status", ""), "Not loaded yet.")]
        held = row.get("withheld")
        if held:
            why.append(f"The {held['meetings']:,} meetings read earlier are kept, but not shown or used in briefings.")
        return "not_yet", why
    gaps = []
    if authority:
        if row.get("board_meetings") == 0:
            gaps.append("No board meetings read, only its committees, so its main decisions are missing.")
    elif row.get("council_meetings") == 0:
        # most named votes are at full council (Sunderland, loaded once with its Cabinet alone)
        gaps.append("No full council meetings read, only its cabinet or committees, so most named votes are "
                    "missing.")
    share = row.get("with_minutes") or 0
    if share < MIN_WITH_MINUTES:
        gaps.append(f"Minutes text for only {round(share * 100)}% of meetings (often published only as documents "
                    "the site wouldn’t serve, or not yet).")
    last = date.fromisoformat(row["to"]) if row.get("to") else None
    if last and (today - last).days > STALE_DAYS:
        gaps.append(f"No meeting since {last.strftime('%B %Y')}.")
    first = date.fromisoformat(row["from"]) if row.get("from") else None
    created = re.search(r"\b(\d{4})\b", row.get("created") or "")
    new = row.get("gss") in NEW_COUNCILS or (authority and created is not None and int(created.group(1)) >= 2018)
    if first and first > LATE_START and not new:
        gaps.append(f"Records start in {first.strftime('%B %Y')}, not May 2018.")
    if not attendance:
        gaps.append("No attendance records, so votes can’t be matched to councillors.")
    elif with_party < MIN_PARTY * attendance:
        gaps.append(f"Party recorded for only {round(100 * with_party / attendance)}% of attendance, so votes can’t "
                    "all be read by party.")
    if gaps:
        return "partial", gaps
    since = "since " + first.strftime("%B %Y") if first else ""
    return "full", [f"Meetings {since}, minutes text for {round(share * 100)}% of them, attendance and parties "
                     "recorded."]
SIDE_ORDER = ("for", "against", "abstain")


# Strategic authorities (decisions 17 to 20)

def authority_facts(c: Council) -> dict[str, Any]:
    """What only a strategic authority has, for its row and page: its statutory kind and category, when it was
    created, and every region it spans."""
    return {"kind_name": KIND_NAMES.get(c.kind, c.kind), "category_name": CATEGORY_NAMES.get(c.category, ""),
            "created": c.created, "regions": [{"code": r, "name": REGION_NAMES.get(r, r)} for r in c.regions],
            "reason": c.reason or None}


def authority_control(gss: str, today: date | None = None) -> dict[str, Any]:
    """An authority's "control" now: its mayor's party, labelled as the mayor's, or no single party (decision 19)."""
    d = today or date.today()
    m = mayor_on(gss, d)
    code = authority.control_key(gss, d)
    return {"code": code, "name": people.party_name(code), "mayor": m.name if m else None,
            "since": _iso(m.start) if m else None}


def authority_members(meetings: list[dict[str, Any]], att: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The members listed at the authority's latest board meeting (the longest list within three months of it), each
    with their role and party on the date, and where that party comes from (decision 20). Appointed members who
    aren't councillors are counted, not named."""
    boards = sorted((m for m in meetings if m["kind"] == "board"), key=lambda m: m["date"])
    if not boards:
        return None
    by_meeting: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for a in att:
        if (a.get("attendance") or "").lower() != "not required":
            by_meeting[a["meeting_id"]].append(a)
    last = boards[-1]["date"]
    best = max((m for m in boards if (last - m["date"]).days <= 92),
               key=lambda m: (len(by_meeting[m["meeting_id"]]), m["date"]))
    order = {"mayor": 0, "assembly_member": 1, "constituent": 1, "non_constituent": 2, "co_opted": 3, "appointed": 4,
             "substitute": 5}
    rows = []
    for a in sorted(by_meeting[best["meeting_id"]], key=lambda a: (order.get(a.get("member_role") or "", 9),
                                                                    a.get("representing") or "", a["name"])):
        role = a.get("member_role") or ""
        named = role not in ("appointed",) and bool(a.get("member_id"))
        home = a.get("home_gss") or ""
        rows.append({"name": _plain_name(authority.bare_name(a["name"])) if named else None,
                     "role": role, "role_name": authority.ROLE_LABELS.get(role, a.get("role") or ""),
                     "party": people.party_name(a["party"]) if a.get("party") else None,
                     "party_code": a.get("party") or "", "party_source": a.get("party_source") or None,
                     "home": {"gss": home, "name": councils()[home].name} if home in councils() else None,
                     "representing": a.get("representing") or None, "attendance": a.get("attendance") or ""})
    return {"date": _iso(best["date"]), "committee": best["committee_title"], "members": rows}


def _plain_name(name: str) -> str:
    """"The Deputy Mayor, Councillor Dominique Williams" -> "Dominique Williams": the role is the meeting's, not
    the person's name."""
    name = re.sub(r"^(?:the\s+)?(?:(?:deputy|lord|civic|vice)\s+)*(?:mayor|chair(?:man|woman|person)?),?\s*", "", name,
                  flags=re.I)
    return re.sub(r"^(?:Councillor|Cllr\.?|Cynghorydd)\s+", "", name.strip())


def _link(v: dict[str, Any]) -> dict[str, Any]:
    """A named vote as another page links to it."""
    return {k: v.get(k) for k in ("vote_id", "date", "heading", "label", "outcome", "counts", "partial", "question",
                                  "kind", "item")}


def _nearby(everything: list[dict[str, Any]], vote_id: str, item_id: str, meeting_id: str) -> dict[str, Any]:
    """The other named votes on the same item (in the minutes' order) and at the same meeting, and the council's
    named votes just before and after this one in the order they were taken, so that every vote can be reached
    from the next by a link."""
    in_time = sorted(everything, key=lambda v: (v["date"] or "", v["vote_id"].rsplit(":", 1)[0], _block(v["vote_id"])))
    at = next(i for i, v in enumerate(in_time) if v["vote_id"] == vote_id)
    on_item = [v for v in everything if v["vote_id"].rsplit(":", 1)[0] == item_id]
    meeting = meeting_id + ":"
    return {"siblings": [_link(v) for v in sorted(on_item, key=lambda v: _block(v["vote_id"]))
                         if v["vote_id"] != vote_id],
            "same_meeting": [_link(v) for v in reversed(everything) if v["vote_id"].startswith(meeting)
                             and v["vote_id"].rsplit(":", 1)[0] != item_id],
            "earlier": _link(in_time[at - 1]) if at > 0 else None,
            "later": _link(in_time[at + 1]) if at + 1 < len(in_time) else None}


def _block(vote_id: str) -> int:
    """A vote's place among its item's named votes, from its id ("E07000092:1559:11918:4" -> 4)."""
    tail = vote_id.rsplit(":", 1)[-1]
    return int(tail) if tail.isdigit() else 0


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


T = TypeVar("T")
# the tables the directory is built from, every council's files of each
DIRECTORY_TABLES = ("meetings", "votes", "attendance")
# the tables a council's own pages are built from, its own file of each
COUNCIL_TABLES = ("meetings", "items", "attendance", "votes")
PEOPLE_TABLES = ("meetings", "attendance")


def _written(path: str | os.PathLike[str]) -> tuple[int, int, int]:
    """When a file was last written, as part of a key: its time, size and inode (each write replaces the whole file,
    so it has a new inode even when two writes fall in the same tick of the clock). Zeros if it isn't there."""
    try:
        s = os.stat(path)
    except FileNotFoundError:
        return (0, 0, 0)
    return (s.st_mtime_ns, s.st_size, s.st_ino)


# what a vote's page gives of each member, kept as a tuple of these
MEMBER_FIELDS = ("side", "name", "written", "matched", "party")


def _sides(rows: list[dict[str, Any]], c: people.Council | None, gss: str, same: dict[str, str]
           ) -> list[tuple[Any, ...]]:
    """Each member's side in a named vote, with the name the council's lists give them and their party on the
    date; each side by party, largest first, then by name. Kept for every vote of every council, so each name is
    held once (``same``), not once for each vote."""
    members = []
    for r in rows:
        party = c.party_on(r["member_id"], r["date"]) if c and r["member_id"] else ""
        known = _plain_name(c.name_of(r["member_id"])) if c and r["member_id"] else ""
        written = same.setdefault(r["name"], r["name"])
        members.append((r["vote"], same.setdefault(known, known) or written, written, bool(r["member_id"]),
                        people.party_name(party, gss) if party else None))
    size = Counter((m[0], m[4]) for m in members)
    members.sort(key=lambda m: (SIDE_ORDER.index(m[0]), m[4] is None, -size[(m[0], m[4])], m[4] or "", m[1]))
    return members


def _control_on(gss: str, d: date, c: people.Council | None) -> str | None:
    """The party in control of a council on a date (an authority's mayor's party), as words."""
    if councils()[gss].is_authority:
        return people.party_name(authority.control_key(gss, d))
    return people.party_name(c.control_on(d), gss) if c else None


class _Kept:
    """Values kept by name, each with the key of what it was made from. Asked again with the same key, the value
    kept is given; with another, it is made again and replaces the old one, so there is never more than one value
    for a name (one for each council, at most). One thread makes a value while any others asking for it wait for
    it, rather than all making it at once: the pages are served from a pool of threads, and a crawler asks for
    many of one council's votes together."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._held: dict[Hashable, tuple[Hashable, Any]] = {}
        self._making: dict[Hashable, threading.Lock] = {}

    def get(self, name: Hashable, key: Hashable, make: Callable[[], T]) -> T:
        with self._lock:
            held = self._held.get(name)
            if held is not None and held[0] == key:
                return held[1]
            making = self._making.setdefault(name, threading.Lock())
        with making:
            with self._lock:
                held = self._held.get(name)
                if held is not None and held[0] == key:
                    return held[1]       # made by the thread this one waited for
            value = make()
            with self._lock:
                self._held[name] = (key, value)
            return value


class Data:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.parquet_dir
        self._lock = threading.Lock()
        # what the directory was built from (None until it is first built), and the directory: replaced whole, so
        # a request never sees one build's rows with another's totals
        self._built_from: tuple[tuple[str, int], ...] | None = None
        self._dir: dict[str, Any] = {"councils": [], "by_gss": {}, "totals": {}}
        self._kept = _Kept()
        # how many councils' named votes are made at once: each reads its items' minutes, and the work is the
        # processor's (two in the container), so more at once is slower for each and holds more in memory
        self._making_votes = threading.BoundedSemaphore(2)

    # Freshness
    def stamp(self) -> float:
        """When the store last changed: the newest meetings file, or the suppression list (suppress.py), whose
        entries the pages show at once. Part of the answer cache's key (app.py)."""
        files = list((self.root / "meetings").glob("*.parquet"))
        return max(max((f.stat().st_mtime for f in files), default=0.0), suppress.stamp(self.settings.data_dir))

    def _files(self, table: str) -> int:
        """Every council's file of one table, as a key that changes when any of them is written, added or removed."""
        try:
            with os.scandir(self.root / table) as found:
                return hash(frozenset((e.name, *_written(e.path)) for e in found if e.name.endswith(".parquet")))
        except FileNotFoundError:
            return 0

    def _own(self, gss: str, tables: tuple[str, ...] = COUNCIL_TABLES, *, suppressions: bool = True) -> Hashable:
        """What a council's own pages are made from, as a key: its own files, and the suppression list, whose
        entries are removed from every council's pages at once."""
        files = tuple(_written(store.parquet.path(self.root, t, gss)) for t in tables)
        return (files, suppress.stamp(self.settings.data_dir)) if suppressions else files

    def _fresh(self) -> tuple[tuple[str, int], ...]:
        """Build the directory again if any council's files have changed since it was built, and give what it is
        built from now. While one thread builds it, the others are given the directory as it was rather than wait
        (except for the first build). Nothing kept for each council is thrown away: that is kept by its own files."""
        now = tuple((t, self._files(t)) for t in DIRECTORY_TABLES)
        if now != self._built_from and self._lock.acquire(blocking=self._built_from is None):
            try:
                if now != self._built_from:
                    self._dir = self._build_directory()
                    self._built_from = now
            finally:
                self._lock.release()
        return self._built_from or now

    def version(self) -> Hashable:
        """What the directory and the list of named votes (``vote_dates``) given now are made from: it changes
        whenever either may have. For keeping what is made from them (the sitemaps, app.py)."""
        return self._fresh()

    def last_update(self) -> dict[str, Any] | None:
        log = self.settings.data_dir / "updates.jsonl"
        if not log.exists():
            return None
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        import json

        return json.loads(lines[-1]) if lines else None

    # The directory
    def _build_directory(self) -> dict[str, Any]:
        con = duckdb.connect()
        names = store.parquet.attach(con, self.root)
        meetings = {r[0]: r[1:] for r in con.execute(
            "SELECT gss, count(*), sum((kind = 'council')::int), sum((kind = 'cabinet')::int), "
            "sum((kind = 'policy')::int), min(date), max(date), avg((items_with_minutes > 0)::int), "
            "sum((kind = 'board')::int), sum((kind = 'scrutiny')::int), sum((kind = 'mayor')::int) "
            "FROM meetings GROUP BY gss").fetchall()} if "meetings" in names else {}
        votes = {r[0]: r[1] for r in con.execute(
            "SELECT gss, count(DISTINCT vote_id) FROM votes GROUP BY gss").fetchall()} if "votes" in names else {}
        # members with no id are an authority's appointed members who aren't councillors: no party to record
        attendance = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT gss, count(*), sum((coalesce(party, '') NOT IN ('', 'NONE'))::int) FROM attendance "
            "WHERE coalesce(member_id, '') <> '' GROUP BY gss"
        ).fetchall()} if "attendance" in names else {}
        out = []
        for c in councils().values():
            m = meetings.get(c.gss)
            row = {"gss": c.gss, "name": c.name, "nation": c.nation, "type": c.type,
                   "type_name": TYPE_NAMES.get(c.type, c.type), "region": c.region,
                   "region_name": REGION_NAMES.get(c.region, c.region),
                   "site": c.modgov_url or None, "status": c.modgov_status, "loaded": bool(m) and not c.withheld}
            if c.is_authority:
                row |= authority_facts(c)
            if m and c.withheld:
                # read before robots.txt was checked (decision 21): kept on the server, withheld from the site
                row["withheld"] = {"meetings": m[0]}
            elif m:
                row |= {"meetings": m[0], "council_meetings": m[1], "cabinet_meetings": m[2],
                        "policy_meetings": m[3], "from": _iso(m[4]), "to": _iso(m[5]),
                        "with_minutes": round(float(m[6] or 0), 3), "named_votes": votes.get(c.gss, 0)}
                if c.is_authority:
                    row |= {"board_meetings": m[7], "scrutiny_meetings": m[8], "mayor_meetings": m[9]}
            row["coverage"], row["reasons"] = coverage(row, *attendance.get(c.gss, (0, 0)))
            out.append(row)
        out.sort(key=lambda r: r["name"])
        loaded = [r for r in out if r["loaded"]]
        bodies = [r for r in out if r["type"] != "strategic_authority"]
        sa = [r for r in out if r["type"] == "strategic_authority"]
        totals = {"councils": len(bodies), "loaded": sum(1 for r in bodies if r["loaded"]),
                  "authorities": len(sa), "authorities_loaded": sum(1 for r in sa if r["loaded"]),
                  "coverage": dict(Counter(r["coverage"] for r in bodies)),
                  "meetings": sum(r["meetings"] for r in loaded),
                  "named_votes": sum(r["named_votes"] for r in loaded),
                  "from": min((r["from"] for r in loaded), default=None),
                  "to": max((r["to"] for r in loaded), default=None)}
        # the party in control now, for the directory: from each council's own timeline; an authority's mayor
        for r in loaded:
            r["control"] = self._control_now(r["gss"])
        for r in sa:
            r["control"] = authority_control(r["gss"])
        return {"councils": out, "by_gss": {r["gss"]: r for r in out}, "totals": totals}

    def _control_now(self, gss: str) -> dict[str, str] | None:
        """The party in control of a council today, from its own timeline: kept until its meetings or attendance
        change (or the day does), so that building the directory again reads only the councils that changed."""
        def now() -> dict[str, str] | None:
            c = self._people(gss)
            if not c or not c.control_by_date:
                return None
            code = c.control_on(date.today())
            return {"code": code, "name": people.party_name(code, gss), "as_of": _iso(c.control_by_date[-1][0])}

        return self._kept.get(("control", gss), (self._own(gss, PEOPLE_TABLES, suppressions=False), date.today()),
                              now)

    def _people(self, gss: str) -> people.Council | None:
        """A council's members and control over time. Not kept: it holds every attendance, a few megabytes for a
        large council, and what is made from it is kept instead."""
        att = store.parquet.read(self.root, "attendance", gss)
        meetings = store.parquet.read(self.root, "meetings", gss)
        return people.build(att, meetings).get(gss)

    def vote_ids(self) -> list[str]:
        """Every named vote's id, for the sitemap: newest first."""
        return [vote_id for vote_id, _ in self.vote_dates()]

    def vote_dates(self) -> list[tuple[str, str]]:
        """Every named vote's id and the date of its meeting (ISO), newest first: for the sitemap. Read again only
        when a council's named votes have changed."""
        votes = dict(self._fresh())["votes"]
        return self._kept.get(("vote dates",), votes, self._read_vote_dates)

    def _read_vote_dates(self) -> list[tuple[str, str]]:
        con = duckdb.connect()
        names = store.parquet.attach(con, self.root)
        rows = con.execute("SELECT vote_id, max(date) AS d FROM votes GROUP BY vote_id ORDER BY d DESC, vote_id"
                           ).fetchall() if "votes" in names else []
        held = set(withheld_codes())
        return [(r[0], _iso(r[1]) or "") for r in rows if r[0].split(":")[0] not in held]

    def latest_votes(self, n: int = 20, hidden: Callable[[str], bool] = lambda _: False,
                     shown: Hashable = ()) -> list[dict[str, Any]]:
        """The newest ``n`` named votes across every council, for the home page (decision 32): newest first, those
        on one day by council, each council's in the order its page lists them, none that is ``hidden``. Each as its
        council's page lists it (its heading is its own page's, api/titles.py), with the council's code and name.

        Kept until the record, the suppression list or what is hidden (``shown``, the caller's key for it) changes.
        Each council's named votes come from what is kept for that council's own pages, so a change to one council
        makes only its votes again."""
        key = (self.version(), suppress.stamp(self.settings.data_dir), shown, n)
        return self._kept.get(("latest votes",), key, lambda: self._latest_votes(n, hidden))

    def _latest_votes(self, n: int, hidden: Callable[[str], bool]) -> list[dict[str, Any]]:
        every = councils()
        chosen: list[tuple[str, str]] = []
        last_day = None
        for vote_id, when in self.vote_dates():          # newest first
            if len(chosen) >= n and when != last_day:
                break                                    # every vote on the last day taken is taken
            gss = vote_id.split(":")[0]
            if gss in every and not every[gss].withheld and not hidden(vote_id):
                chosen.append((vote_id, when))
                last_day = when
        out = []
        for gss in dict.fromkeys(vote_id.split(":")[0] for vote_id, _ in chosen):
            wanted = {vote_id for vote_id, _ in chosen if vote_id.startswith(gss + ":")}
            for place, v in enumerate(self.votes(gss)):
                if v["vote_id"] in wanted:
                    out.append({**_link(v), "title": v.get("title"), "gss": gss, "council": every[gss].name,
                                "place": place})
        out.sort(key=lambda v: (v["council"], v["place"]))
        out.sort(key=lambda v: v["date"] or "", reverse=True)      # stable: on one day, by council
        return [{k: x for k, x in v.items() if k != "place"} for v in out[:n]]

    def directory(self) -> dict[str, Any]:
        self._fresh()
        d = self._dir
        return {"totals": d["totals"], "councils": d["councils"]}

    def totals(self) -> dict[str, Any]:
        self._fresh()
        return self._dir["totals"]

    # A council
    def council(self, gss: str) -> dict[str, Any] | None:
        """A council's page: its row in the directory, the authorities it belongs to (or an authority's councils
        and mayors), and what is made from its own record, kept until that changes."""
        self._fresh()
        d = self._dir
        entry = d["by_gss"].get(gss)
        if entry is None:
            return None
        # the strategic authorities a council belongs to, and an authority's councils and mayors (decision 17)
        links = self._links(gss, d["by_gss"])
        if not entry["loaded"]:
            page = {**entry, **links, "control_timeline": [], "seats": None, "members": None, "by_year": [],
                    "votes": [], "recent": []}
        else:
            page = {**entry, **links, **self._kept.get(("council", gss), self._own(gss),
                                                       lambda: self._council(gss, entry["type"]))}
        # where its record meets the sister sites': Where Landlords Stand's pages for it, and the MPs whose seats
        # overlap it on Where MPs Stand (decision 31), from files kept here, never asked of another site now
        return {**page, "landlords": sisters.landlords(gss), "mps": sisters.mps(self.settings, gss)}

    def _council(self, gss: str, kind: str) -> dict[str, Any]:
        """What a loaded council's page shows from its own record."""
        meetings = store.parquet.read(self.root, "meetings", gss)
        att = store.parquet.read(self.root, "attendance", gss)
        c = people.build(att, meetings).get(gss)

        # control over time: a new row whenever it changes
        timeline: list[dict[str, Any]] = []
        if c:
            for d, _, _ in c.control_by_date:
                code = c.control_on(d)
                if not timeline or timeline[-1]["code"] != code:
                    timeline.append({"from": _iso(d), "code": code, "name": people.party_name(code, gss)})

        # members by party at the latest full council meeting with the longest list near it
        seats = None
        council_meetings = sorted((m for m in meetings if m["kind"] == "council"), key=lambda m: m["date"])
        if council_meetings and c:
            last = council_meetings[-1]["date"]
            near = [m for m in council_meetings if (last - m["date"]).days <= 92]
            by_meeting = defaultdict(list)
            for a in att:
                if a["member_id"]:
                    by_meeting[a["meeting_id"]].append(a)
            best = max(near, key=lambda m: (len(by_meeting[m["meeting_id"]]), m["date"]))
            count = Counter(people.party_key(a["party"], a["party_label"]) or "?" for a in by_meeting[best["meeting_id"]])
            seats = {"date": _iso(best["date"]), "total": sum(count.values()),
                     "parties": [{"code": k, "name": people.party_name(k, gss) if k != "?" else "Party not recorded",
                                  "members": n} for k, n in count.most_common()]}

        by_year = Counter((m["year"], m["kind"]) for m in meetings)
        with_minutes = Counter(m["year"] for m in meetings if m["items_with_minutes"])
        years = sorted({y for y, _ in by_year})
        recent = sorted(meetings, key=lambda m: m["date"], reverse=True)[:12]
        return {
            "control_timeline": timeline,
            "seats": seats,
            "members": authority_members(meetings, att) if kind == "strategic_authority" else None,
            "by_year": [{"year": y, **{k: by_year[(y, k)] for k in KIND_LABEL}, "with_minutes": with_minutes[y]}
                        for y in years],
            "votes": self.votes(gss, c),
            "recent": [{"date": _iso(m["date"]), "committee": m["committee_title"], "kind": m["kind"],
                        "url": m["url"], "items_with_minutes": m["items_with_minutes"]} for m in recent],
        }

    def _links(self, gss: str, rows: dict[str, dict[str, Any]]) -> dict[str, Any]:
        c = councils()[gss]
        if c.is_authority:
            return {"constituents": [{"gss": m.council, "name": councils()[m.council].name,
                                      "role": m.role, "role_name": MEMBER_ROLES.get(m.role, m.role),
                                      "from": _iso(m.start), "to": _iso(m.end),
                                      "loaded": bool(rows.get(m.council, {}).get("loaded"))}
                                     for m in members_of(gss) if m.council in councils()],
                    "mayors": [{"name": m.name, "party": m.party, "party_name": people.party_name(m.party),
                                "from": _iso(m.start), "to": _iso(m.end)} for m in mayors_of(gss)]}
        return {"authorities": [{"gss": m.authority, "name": councils()[m.authority].name, "role": m.role,
                                 "role_name": MEMBER_ROLES.get(m.role, m.role), "from": _iso(m.start),
                                 "to": _iso(m.end)} for m in authorities_of(gss) if m.authority in councils()]}

    # Named votes
    def votes(self, gss: str, c: people.Council | None = None) -> list[dict[str, Any]]:
        """Every named vote at a council, newest first: the item, the result, the count of each side by party, and
        what the vote is called (api/titles.py): its label among the item's votes, its heading and its page's
        title. Built once for each council and kept until its own record or the suppression list changes."""
        return self._record(gss)["votes"]

    def _record(self, gss: str) -> dict[str, Any]:
        """A council's named votes as its page lists them (``votes``), and what each vote's own page shows of its
        record (``pages``: by vote id, its first row, each member's side and the council's control on the date),
        made together, from the same files, and kept together."""
        return self._kept.get(("votes", gss), self._own(gss), lambda: self._votes(gss))

    def _votes(self, gss: str) -> dict[str, Any]:
        rows = store.parquet.read(self.root, "votes", gss)
        if not rows:
            return {"votes": [], "pages": {}}
        with self._making_votes:
            return self._make_votes(gss, rows)

    def _make_votes(self, gss: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
        # only the items voted on, and only what is used of them: each item's minutes are the most there is to read
        p = store.parquet.path(self.root, "items", gss)
        voted = sorted({r["item_id"] for r in rows})
        items = {i["item_id"]: i for i in (pq.read_table(p, columns=["item_id", "number", "title", "url",
                                                                       "minutes_text"],
                                                          filters=[("item_id", "in", voted)]).to_pylist()
                                           if p.exists() else [])}
        meetings = {m["meeting_id"]: m for m in store.parquet.read(self.root, "meetings", gss)}
        c = self._people(gss)
        # an item's title can name someone who isn't a councillor ("Petition – Mr Steve Dally"): as for the index
        names, sup = scrub.surnames(self.root, gss), suppress.load(self.settings.data_dir)
        by_vote: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by_vote[r["vote_id"]].append(r)
        labels = self._labels(gss, by_vote, items, names, sup)
        body = councils()[gss]
        short = body.short_name if sum(1 for x in councils().values() if x.short_name == body.short_name) == 1 \
            else body.name
        out, pages, same = [], {}, {}
        for vote_id, vs in by_vote.items():
            first = vs[0]
            it, m = items.get(first["item_id"], {}), meetings.get(first["meeting_id"], {})
            sides: dict[str, Counter] = {s: Counter() for s in SIDE_ORDER}
            for v in vs:
                party = c.party_on(v["member_id"], v["date"]) if c and v["member_id"] else ""
                sides[v["vote"]][people.party_name(party, gss) if party else "Not matched"] += 1
            v = {
                "vote_id": vote_id, "date": _iso(first["date"]), "committee": m.get("committee_title", ""),
                "kind": m.get("kind", ""), "number": it.get("number", ""),
                "item": scrub.item_title(it.get("title", ""), names, sup, gss, first["item_id"]),
                "question": first["question"], "outcome": first["outcome"], "url": it.get("url", ""),
                "counts": {s: sum(sides[s].values()) for s in SIDE_ORDER},
                "by_party": {s: [{"party": p, "n": n} for p, n in sides[s].most_common()] for s in SIDE_ORDER},
                "partial": sum(1 for s in SIDE_ORDER if sides[s]) == 1,
                **labels[vote_id],
            }
            v["heading"] = titles.heading(v, body.name)
            v["title"] = titles.title(v, body.name, short)
            v["budget"] = titles.is_budget(v)
            out.append(v)
            pages[vote_id] = ({k: first[k] for k in ("excerpt", "item_id", "meeting_id")}, _sides(vs, c, gss, same),
                              _control_on(gss, first["date"], c))
        out.sort(key=lambda v: (v["date"], v["vote_id"].rsplit(":", 1)[0], -_block(v["vote_id"])), reverse=True)
        return {"votes": out, "pages": pages}

    def _labels(self, gss: str, by_vote: dict[str, list[dict[str, Any]]], items: dict[str, dict[str, Any]],
                names: set[str], sup: suppress.Suppressions) -> dict[str, dict[str, Any]]:
        """Each vote's label among its item's named votes (api/titles.py), read from the item's minutes where its
        extract can be found in them, otherwise from its extract. A label that names who moved an amendment keeps
        the name only if it is a councillor's and nothing removes it: the rules the extracts go through."""
        by_item: dict[str, list[str]] = defaultdict(list)
        for vote_id, vs in by_vote.items():
            by_item[vs[0]["item_id"]].append(vote_id)
        out: dict[str, dict[str, Any]] = {}
        for item_id, ids in by_item.items():
            ids.sort(key=_block)
            excerpts = [by_vote[i][0].get("excerpt") or "" for i in ids]
            contexts = titles.minutes_context((items.get(item_id) or {}).get("minutes_text") or "", excerpts)
            found = []
            for vote_id, excerpt, context in zip(ids, excerpts, contexts, strict=True):
                question = by_vote[vote_id][0].get("question") or ""
                label = titles.derive_label(context if context is not None else titles.before_vote(excerpt),
                                            question, titles.headings(excerpt))
                if label and " by Cllr " in label:
                    who = label.split(" by Cllr ", 1)[1]
                    surname = re.sub(r"[^\w-]", "", who.split()[-1]).lower()
                    if surname not in names or scrub.minutes_text(label, names, sup, gss, item_id) != label:
                        label = label.split(" by Cllr ")[0]
                found.append({"vote_id": vote_id, "label": label})
            out.update(titles.item_labels(found))
        return out

    def vote(self, vote_id: str, hidden: Callable[[str], bool] = lambda _: False) -> dict[str, Any] | None:
        """One named vote's page: its summary, each member's side and party on the date, the extract, and links to
        the council's other named votes near it: on the same item, at the same meeting, and the votes just before
        and after it (none that is ``hidden``)."""
        self._fresh()
        gss = vote_id.split(":")[0]
        if gss not in councils() or councils()[gss].withheld:
            return None
        record = self._record(gss)
        page = record["pages"].get(vote_id)
        if page is None:
            return None
        first, sides, control = page
        everything = [v for v in record["votes"] if v["vote_id"] == vote_id or not hidden(v["vote_id"])]
        summary = next((v for v in everything if v["vote_id"] == vote_id), None)
        # stored with others' names removed by the rules of the day: through them again, as the minutes are
        excerpt = scrub.minutes_text(first["excerpt"], scrub.surnames(self.root, gss),
                                     suppress.load(self.settings.data_dir), gss, first["item_id"],
                                     (summary or {}).get("item") or "")
        return {**(summary or {}), "gss": gss, "council": councils()[gss].name,
                "is_authority": councils()[gss].is_authority,
                "from_table": " | " in excerpt and excerpt.rstrip().endswith("members)"),
                "control": control,
                "excerpt": excerpt, "members": [dict(zip(MEMBER_FIELDS, m, strict=True)) for m in sides],
                "description": titles.description(summary, councils()[gss].name) if summary else "",
                **(_nearby(everything, vote_id, first["item_id"], first["meeting_id"]) if summary else {})}
