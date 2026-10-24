"""Load one council's full council and cabinet meetings into the store, from the start date to today."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date

from councils import committees, extract, store
from councils.config import Settings
from councils.parse import parties
from councils.registry import Council, site_sharers
from councils.sources import meeting as meeting_rows
from councils.sources.modgov import Client, ModgovError

log = logging.getLogger(__name__)


@dataclass
class Result:
    gss: str
    committees: dict[int, tuple[str, str]] = field(default_factory=dict)   # id -> (title, kind)
    meetings: int = 0
    failed: list[int] = field(default_factory=list)
    error: str = ""


def selected_committees(client: Client, council: Council) -> dict[int, tuple[str, str]]:
    """The council's committees in scope, by id: (title, kind)."""
    sharers = site_sharers(council)
    out = {}
    for c in client.committees():
        if c.deleted:
            continue
        title = c.title
        if sharers:  # a site shared with another council: keep only this council's committees
            own = committees.strip_prefix(title, [council.short_name])
            if own is None:
                continue
            title = own
        k = committees.kind(title, council.gss)
        if k:
            out[c.id] = (c.title, k)
    return out


def load(settings: Settings, council: Council, start: date | None = None, end: date | None = None) -> Result:
    start = start or settings.start_date
    end = end or date.today()
    res = Result(council.gss)
    if not council.modgov_url:
        res.error = "no Modern.gov site"
        return res
    meetings, items, attendance = [], [], []
    with Client(settings, council.gss, council.modgov_url) as client:
        try:
            res.committees = selected_committees(client, council)
        except ModgovError as e:
            res.error = str(e)
            return res
        for cid, (title, kind) in sorted(res.committees.items()):
            try:
                refs = client.meetings(cid, start, end)
            except ModgovError as e:
                log.warning("%s committee %s: %s", council.gss, cid, e)
                continue
            for ref in refs:
                if ref.date > end or ref.date < start:
                    continue
                try:
                    root = client.meeting(ref.id, ref.date)
                except ModgovError as e:
                    log.warning("%s meeting %s: %s", council.gss, ref.id, e)
                    res.failed.append(ref.id)
                    continue
                ctx = meeting_rows.Context(council.gss, council.name, council.modgov_url, cid, title, kind)
                m, its, att = meeting_rows.rows(root, ctx)
                # Members of the public and council staff in the attendance list aren't stored (docs/DECISIONS.md, 9).
                att = [a for a in att if extract.is_councillor(a["role"])]
                for a in att:
                    a["party"] = parties.normalise(a["party_label"], council.gss)
                meetings.append(m)
                items += its
                attendance += att
    root = settings.parquet_dir
    store.parquet.write(root, "meetings", council.gss, meetings)
    store.parquet.write(root, "items", council.gss, items)
    store.parquet.write(root, "attendance", council.gss, attendance)
    res.meetings = len(meetings)
    return res
