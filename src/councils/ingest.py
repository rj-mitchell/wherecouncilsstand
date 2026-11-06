"""Load one council's full council and cabinet meetings into the store, from the start date to today."""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from councils import committees, extract, store
from councils.config import Settings
from councils.parse import parties
from councils.registry import Council, site_sharers
from councils.sources import documents
from councils.sources import meeting as meeting_rows
from councils.sources.modgov import ROBOTS_ERROR, Client, ModgovError, Refused
from councils.sources.streak import TimeoutStreak

log = logging.getLogger(__name__)


@dataclass
class Result:
    gss: str
    committees: dict[int, tuple[str, str]] = field(default_factory=dict)   # id -> (title, kind)
    meetings: int = 0
    failed: list[int] = field(default_factory=list)
    documents_read: int = 0
    documents_refused: bool = False   # the site wouldn't serve documents to automated requests
    error: str = ""


def selected_committees(client: Client, council: Council, max_age_days: float | None = None) -> dict[int, tuple[str, str]]:
    """The council's committees in scope, by id: (title, kind)."""
    sharers = site_sharers(council)
    out = {}
    for c in client.committees(max_age_days=max_age_days):
        if c.deleted:
            continue
        title = c.title
        if sharers:  # a site shared with another council: keep only this council's committees
            own = committees.strip_prefix(title, [council.name, council.short_name])
            if own is None:
                continue
            title = own
        # full council named as the council itself: "Cornwall Council"
        k = "council" if title.strip().lower() == council.name.lower() else committees.kind(title, council.gss)
        if k:
            out[c.id] = (c.title, k)
    return out


def load(settings: Settings, council: Council, start: date | None = None, end: date | None = None,
         update: bool = False) -> Result:
    """Load a council's meetings in scope from its Modern.gov site (or the cache) and replace its stored rows.

    With ``update``, the committee list is fetched again if over a week old, and nothing is written unless every
    committee's meetings could be listed: a server that is down mustn't remove meetings already stored."""
    start = start or settings.start_date
    end = end or date.today()
    if council.modgov_status == "robots":
        # marked in the registry: its site's robots.txt forbids reading it (decision 21). Not asked at all; what is
        # stored is kept, withheld from the site (api/data.py), until permission is given.
        return Result(council.gss, error=ROBOTS_ERROR)
    if council.system != "modgov":
        return _load_other(settings, council, start, end, update)
    res = Result(council.gss)
    if not council.modgov_url:
        res.error = "no Modern.gov site"
        return res
    streak = TimeoutStreak(settings, council.gss)
    with Client(settings, council.gss, council.modgov_url) as client:
        try:
            return _load_modgov(settings, client, council, start, end, update, res, streak)
        except Refused:
            # robots.txt forbids the site now: nothing is written, what is stored is kept, and the update reports it
            # so that the registry can be marked and permission asked (docs/OPERATIONS.md)
            res.error = ROBOTS_ERROR
            return res


def _load_modgov(settings: Settings, client: Client, council: Council, start: date, end: date, update: bool,
                 res: Result, streak: TimeoutStreak) -> Result:
    meetings, items, attendance = [], [], []
    try:
        res.committees = selected_committees(client, council, max_age_days=7 if update else None)
    except Refused:
        raise
    except ModgovError as e:
        res.error = str(e)
        return res
    for cid, (title, kind) in sorted(res.committees.items()):
        refs = None
        for attempt in (1, 2):
            try:
                refs = client.meetings(cid, start, end)
                break
            except Refused:
                raise
            except ModgovError as e:
                log.warning("%s committee %s (attempt %d): %s", council.gss, cid, attempt, e)
                error = e
                if attempt == 1:
                    time.sleep(10)
        if refs is None:
            # Not a council with a committee missing (East Hampshire's council meetings were lost so,
            # November 2026): nothing is stored, so the next load or update tries again.
            res.error = f"committee {title}: {error}"
            return res
        for ref in refs:
            if ref.date > end or ref.date < start:
                continue
            try:
                root = client.meeting(ref.id, ref.date)
            except Refused:
                raise
            except ModgovError as e:
                log.warning("%s meeting %s: %s", council.gss, ref.id, e)
                res.failed.append(ref.id)
                if stop := streak.failed(ref.id, e):
                    log.warning("%s %s", council.gss, stop)
                    res.error = stop
                    return res
                continue
            streak.ok()
            ctx = meeting_rows.Context(council.gss, council.name, council.modgov_url, cid, title, kind)
            try:
                m, its, att = meeting_rows.rows(root, ctx, ref.date)
            except ValueError as e:              # a record that can't be read: this meeting, not the council
                log.warning("%s meeting %s: %s", council.gss, ref.id, e)
                res.failed.append(ref.id)
                continue
            # Members of the public and council staff in the attendance list aren't stored (docs/DECISIONS.md, 9).
            att = [a for a in att if extract.is_councillor(a["role"])]
            for a in att:
                a["party"] = parties.normalise(a["party_label"], council.gss)
            meetings.append(m)
            items += its
            attendance += att
    if settings.modgov.get("read_documents", True):
        items = _minutes_from_documents(client, meetings, items, res)
    root = settings.parquet_dir
    if update and res.failed:
        res.error = f"{len(res.failed)} meetings could not be fetched"
        return res
    store.parquet.write(root, "meetings", council.gss, meetings)
    store.parquet.write(root, "items", council.gss, items)
    store.parquet.write(root, "attendance", council.gss, attendance)
    res.meetings = len(meetings)
    return res


def _load_other(settings: Settings, council: Council, start: date, end: date, update: bool) -> Result:
    """A council on another meetings system (CMIS, CoINS): its reader fetches the same rows the Modern.gov path makes,
    and they are written the same way (nothing is written if the reader reports an error)."""
    from importlib import import_module

    try:
        reader = import_module(f"councils.sources.{council.system}")
    except ModuleNotFoundError:
        return Result(council.gss, error=f"no reader for {council.system}")
    res, meetings, items, attendance = reader.fetch(settings, council, start, end, update)
    for a in attendance:
        a["party"] = parties.normalise(a.get("party_label", ""), council.gss)
    if res.error or (update and res.failed):
        res.error = res.error or f"{len(res.failed)} meetings could not be fetched"
        return res
    root = settings.parquet_dir
    store.parquet.write(root, "meetings", council.gss, meetings)
    store.parquet.write(root, "items", council.gss, items)
    store.parquet.write(root, "attendance", council.gss, attendance)
    res.meetings = len(meetings)
    return res


def _minutes_from_documents(client: Client, meetings: list[dict], items: list[dict], res: Result) -> list[dict]:
    """For meetings whose minutes aren't in the web service, read them from the minutes document attached to the
    committee's next meeting (sources/documents.py). Stops at the first refusal: a site that blocks one document
    blocks them all."""
    by_meeting: dict[str, list[dict]] = defaultdict(list)
    for it in items:
        by_meeting[it["meeting_id"]].append(it)
    by_committee: dict[int, list[dict]] = defaultdict(list)
    for m in meetings:
        by_committee[m["committee_id"]].append(m)
    extra = []
    for ms in by_committee.values():
        ms.sort(key=lambda m: m["date"])
        for n, m in enumerate(ms):
            if m["items_with_minutes"] or res.documents_refused or (date.today() - m["date"]).days < 21:
                continue
            doc = documents.choose(m["date"], ms[n + 1:])
            if not doc:
                continue
            try:
                data = client.document(doc["url"])
            except ModgovError as e:
                log.warning("%s document: %s", m["meeting_id"], e)
                continue
            if data is None:
                res.documents_refused = True
                continue
            text = documents.pdf_text(data)
            if len(text) < 200:
                continue
            res.documents_read += 1
            own = sorted(by_meeting.get(m["meeting_id"], []), key=lambda i: i["position"])
            parts = documents.split_into_items(text, own)
            if parts:
                for it in own:
                    if it["item_id"] in parts:
                        it["minutes_text"], it["minutes_source"] = parts[it["item_id"]], "document"
            else:   # the items couldn't be found in the document: keep it whole
                extra.append({**(own[0] if own else {}), "item_id": f"{m['meeting_id']}:minutes",
                              "meeting_id": m["meeting_id"], "gss": m["gss"], "date": m["date"], "year": m["year"],
                              "position": -1, "number": "", "title": "Minutes", "agenda_text": "",
                              "minutes_text": text.strip(), "minutes_source": "document", "vote_tables": "",
                              "is_decision": False, "is_restricted": False, "is_call_in": False,
                              "declaration_count": 0, "documents": 0, "url": doc["url"]})
            m["minutes_document"] = doc["url"]
            m["items_with_minutes"] = sum(1 for i in own if len(i["minutes_text"]) > 40) or (1 if not parts else 0)
    return items + extra
