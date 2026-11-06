"""What the council and vote pages show, read from the store. The directory is built once and rebuilt when the daily
update has changed the store; a council's own page is built when first asked for and kept until then."""

from __future__ import annotations

import re
import threading
from collections import Counter, defaultdict
from datetime import date
from functools import lru_cache
from typing import Any

import duckdb

from councils import sisters, store
from councils.config import Settings
from councils.reference import people
from councils.registry import REGION_NAMES, TYPE_NAMES, councils, withheld_codes

KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee"}

# How fully each council is covered, for the councils page: "not_yet" (not loaded), "partial" (loaded with a gap)
# or "full". It describes the site's reading of the council's record, never the council.
NOT_LOADED = {
    "robots": "Permission asked: its meetings site asks automated readers not to visit (robots.txt), so it isn't read "
              "until it agrees.",
    "blocked": "Its meetings site refuses automated requests.",
    "unreachable": "Its meetings site couldn't be reached.",
    "none": "It doesn't publish its minutes through a system we can read yet.",
    "ok": "Its meetings site answers, but it hasn't been loaded yet or failed to load.",
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
    if not row.get("loaded"):
        why = [NOT_LOADED.get(row.get("status", ""), "Not loaded yet.")]
        held = row.get("withheld")
        if held:
            why.append(f"The {held['meetings']:,} meetings read before robots.txt was checked are kept, but not shown "
                       "or used in briefings, until it agrees.")
        return "not_yet", why
    gaps = []
    if row.get("council_meetings") == 0:
        # most named votes are at full council (Sunderland, loaded once with its Cabinet alone)
        gaps.append("No full council meetings read, only its cabinet or committees, so most named votes are "
                    "missing.")
    share = row.get("with_minutes") or 0
    if share < MIN_WITH_MINUTES:
        gaps.append(f"Minutes text for only {round(share * 100)}% of meetings (often published only as documents "
                    "the site wouldn't serve, or not yet).")
    last = date.fromisoformat(row["to"]) if row.get("to") else None
    if last and (today - last).days > STALE_DAYS:
        gaps.append(f"No meeting since {last.strftime('%B %Y')}.")
    first = date.fromisoformat(row["from"]) if row.get("from") else None
    if first and first > LATE_START and row.get("gss") not in NEW_COUNCILS:
        gaps.append(f"Records start in {first.strftime('%B %Y')}, not May 2018.")
    if not attendance:
        gaps.append("No attendance records, so votes can't be matched to councillors.")
    elif with_party < MIN_PARTY * attendance:
        gaps.append(f"Party recorded for only {round(100 * with_party / attendance)}% of attendance, so votes can't "
                    "all be read by party.")
    if gaps:
        return "partial", gaps
    since = "since " + first.strftime("%B %Y") if first else ""
    return "full", [f"Meetings {since}, minutes text for {round(share * 100)}% of them, attendance and parties "
                     "recorded."]
SIDE_ORDER = ("for", "against", "abstain")


def _plain_name(name: str) -> str:
    """"The Deputy Mayor, Councillor Dominique Williams" -> "Dominique Williams": the role is the meeting's, not
    the person's name."""
    name = re.sub(r"^(?:the\s+)?(?:(?:deputy|lord|civic|vice)\s+)*(?:mayor|chair(?:man|woman|person)?),?\s*", "", name,
                  flags=re.I)
    return re.sub(r"^(?:Councillor|Cllr\.?|Cynghorydd)\s+", "", name.strip())


def _iso(d: date | None) -> str | None:
    return d.isoformat() if d else None


class Data:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.root = settings.parquet_dir
        self._lock = threading.Lock()
        self._stamp: float | None = None
        self._directory: list[dict[str, Any]] = []
        self._totals: dict[str, Any] = {}
        self._vote_ids: list[str] | None = None

    # freshness ------------------------------------------------------------------------------------------
    def stamp(self) -> float:
        """When the store last changed: the newest meetings file."""
        files = list((self.root / "meetings").glob("*.parquet"))
        return max((f.stat().st_mtime for f in files), default=0.0)

    def _fresh(self) -> None:
        stamp = self.stamp()
        if stamp != self._stamp:
            with self._lock:
                if stamp != self._stamp:
                    self._build_directory()
                    self._council.cache_clear()
                    self._vote_ids = None
                    self._stamp = stamp

    def last_update(self) -> dict[str, Any] | None:
        log = self.settings.data_dir / "updates.jsonl"
        if not log.exists():
            return None
        lines = [ln for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
        import json

        return json.loads(lines[-1]) if lines else None

    # the directory --------------------------------------------------------------------------------------
    def _build_directory(self) -> None:
        con = duckdb.connect()
        names = store.parquet.attach(con, self.root)
        meetings = {r[0]: r[1:] for r in con.execute(
            "SELECT gss, count(*), sum((kind = 'council')::int), sum((kind = 'cabinet')::int), "
            "sum((kind = 'policy')::int), min(date), max(date), avg((items_with_minutes > 0)::int) "
            "FROM meetings GROUP BY gss").fetchall()} if "meetings" in names else {}
        votes = {r[0]: r[1] for r in con.execute(
            "SELECT gss, count(DISTINCT vote_id) FROM votes GROUP BY gss").fetchall()} if "votes" in names else {}
        attendance = {r[0]: (r[1], r[2]) for r in con.execute(
            "SELECT gss, count(*), sum((coalesce(party, '') NOT IN ('', 'NONE'))::int) FROM attendance GROUP BY gss"
        ).fetchall()} if "attendance" in names else {}
        out = []
        for c in councils().values():
            m = meetings.get(c.gss)
            row = {"gss": c.gss, "name": c.name, "nation": c.nation, "type": c.type,
                   "type_name": TYPE_NAMES.get(c.type, c.type), "region": c.region,
                   "region_name": REGION_NAMES.get(c.region, c.region),
                   "site": c.modgov_url or None, "status": c.modgov_status, "loaded": bool(m) and not c.withheld}
            if m and c.withheld:
                # read before robots.txt was checked (decision 21): kept on the server, withheld from the site
                row["withheld"] = {"meetings": m[0]}
            elif m:
                row |= {"meetings": m[0], "council_meetings": m[1], "cabinet_meetings": m[2],
                        "policy_meetings": m[3], "from": _iso(m[4]), "to": _iso(m[5]),
                        "with_minutes": round(float(m[6] or 0), 3), "named_votes": votes.get(c.gss, 0)}
            row["coverage"], row["reasons"] = coverage(row, *attendance.get(c.gss, (0, 0)))
            out.append(row)
        out.sort(key=lambda r: r["name"])
        self._directory = out
        loaded = [r for r in out if r["loaded"]]
        self._totals = {"councils": len(out), "loaded": len(loaded),
                        "coverage": dict(Counter(r["coverage"] for r in out)),
                        "meetings": sum(r["meetings"] for r in loaded),
                        "named_votes": sum(r["named_votes"] for r in loaded),
                        "from": min((r["from"] for r in loaded), default=None),
                        "to": max((r["to"] for r in loaded), default=None)}
        # the party in control now, for the directory: from each council's own timeline
        for r in loaded:
            r["control"] = self._control_now(r["gss"])

    def _control_now(self, gss: str) -> dict[str, str] | None:
        c = self._people(gss)
        if not c or not c.control_by_date:
            return None
        code = c.control_on(date.today())
        return {"code": code, "name": people.party_name(code, gss), "as_of": _iso(c.control_by_date[-1][0])}

    def _people(self, gss: str) -> people.Council | None:
        att = store.parquet.read(self.root, "attendance", gss)
        meetings = store.parquet.read(self.root, "meetings", gss)
        return people.build(att, meetings).get(gss)

    def vote_ids(self) -> list[str]:
        """Every named vote's id, for the sitemap: newest first."""
        self._fresh()
        if self._vote_ids is None:
            con = duckdb.connect()
            names = store.parquet.attach(con, self.root)
            rows = con.execute("SELECT vote_id, max(date) AS d FROM votes GROUP BY vote_id ORDER BY d DESC, vote_id"
                               ).fetchall() if "votes" in names else []
            held = set(withheld_codes())
            self._vote_ids = [r[0] for r in rows if r[0].split(":")[0] not in held]
        return self._vote_ids

    def directory(self) -> dict[str, Any]:
        self._fresh()
        return {"totals": self._totals, "councils": self._directory}

    def totals(self) -> dict[str, Any]:
        self._fresh()
        return self._totals

    # a council ------------------------------------------------------------------------------------------
    def council(self, gss: str) -> dict[str, Any] | None:
        self._fresh()
        c = self._council(gss)
        return None if c is None else {**c, "landlords": sisters.landlords(gss)}

    @lru_cache(maxsize=64)  # noqa: B019 - one Data per process; cleared when the store changes
    def _council(self, gss: str) -> dict[str, Any] | None:
        entry = next((r for r in self._directory if r["gss"] == gss), None)
        if entry is None:
            return None
        if not entry["loaded"]:
            return {**entry, "control_timeline": [], "seats": None, "by_year": [], "votes": [], "recent": []}
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
            **entry,
            "control_timeline": timeline,
            "seats": seats,
            "by_year": [{"year": y, **{k: by_year[(y, k)] for k in KIND_LABEL}, "with_minutes": with_minutes[y]}
                        for y in years],
            "votes": self.votes(gss, c),
            "recent": [{"date": _iso(m["date"]), "committee": m["committee_title"], "kind": m["kind"],
                        "url": m["url"], "items_with_minutes": m["items_with_minutes"]} for m in recent],
        }

    # named votes ----------------------------------------------------------------------------------------
    def votes(self, gss: str, c: people.Council | None = None) -> list[dict[str, Any]]:
        """Every named vote at a council, newest first: the item, the result, and the count of each side by party."""
        rows = store.parquet.read(self.root, "votes", gss)
        if not rows:
            return []
        items = {i["item_id"]: i for i in store.parquet.read(self.root, "items", gss)}
        meetings = {m["meeting_id"]: m for m in store.parquet.read(self.root, "meetings", gss)}
        if c is None:
            c = self._people(gss)
        by_vote: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by_vote[r["vote_id"]].append(r)
        out = []
        for vote_id, vs in by_vote.items():
            first = vs[0]
            it, m = items.get(first["item_id"], {}), meetings.get(first["meeting_id"], {})
            sides: dict[str, Counter] = {s: Counter() for s in SIDE_ORDER}
            for v in vs:
                party = c.party_on(v["member_id"], v["date"]) if c and v["member_id"] else ""
                sides[v["vote"]][people.party_name(party, gss) if party else "Not matched"] += 1
            out.append({
                "vote_id": vote_id, "date": _iso(first["date"]), "committee": m.get("committee_title", ""),
                "kind": m.get("kind", ""), "item": it.get("title", ""), "number": it.get("number", ""),
                "question": first["question"], "outcome": first["outcome"], "url": it.get("url", ""),
                "counts": {s: sum(sides[s].values()) for s in SIDE_ORDER},
                "by_party": {s: [{"party": p, "n": n} for p, n in sides[s].most_common()] for s in SIDE_ORDER},
                "partial": sum(1 for s in SIDE_ORDER if sides[s]) == 1,
            })
        out.sort(key=lambda v: (v["date"], v["vote_id"]), reverse=True)
        return out

    def vote(self, vote_id: str) -> dict[str, Any] | None:
        self._fresh()
        gss = vote_id.split(":")[0]
        if gss not in councils() or councils()[gss].withheld:
            return None
        rows = [r for r in store.parquet.read(self.root, "votes", gss) if r["vote_id"] == vote_id]
        if not rows:
            return None
        c = self._people(gss)
        summary = next((v for v in self.votes(gss, c) if v["vote_id"] == vote_id), None)
        members = []
        for r in rows:
            party = c.party_on(r["member_id"], r["date"]) if c and r["member_id"] else ""
            known = _plain_name(c.name_of(r["member_id"])) if c and r["member_id"] else ""
            members.append({"side": r["vote"], "name": known or r["name"],
                            "written": r["name"], "matched": bool(r["member_id"]),
                            "party": people.party_name(party, gss) if party else None})
        # each side by party, largest first, then by name
        size = Counter((m["side"], m["party"]) for m in members)
        members.sort(key=lambda x: (SIDE_ORDER.index(x["side"]), x["party"] is None, -size[(x["side"], x["party"])],
                                    x["party"] or "", x["name"]))
        excerpt = rows[0]["excerpt"]
        return {**(summary or {}), "gss": gss, "council": councils()[gss].name,
                "from_table": " | " in excerpt and excerpt.rstrip().endswith("members)"),
                "control": people.party_name(c.control_on(rows[0]["date"]), gss) if c else None,
                "excerpt": excerpt, "members": members}
