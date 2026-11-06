"""One Modern.gov meeting (a GetMeeting response) as rows for the store: the meeting, its agenda items with their
minutes, and who attended."""

from __future__ import annotations

import html
import json
import re
from dataclasses import dataclass
from datetime import date

from lxml import etree

from councils.parse.minutes import to_text, vote_tables
from councils.sources.modgov import parse_date

# The agenda item at which a meeting approves the minutes of the one before; the earlier minutes are attached to it.
MINUTES_ITEM = re.compile(r"^\W*(?:\d+[.)]?\s*)?(?:approval of (?:the )?|confirmation of (?:the )?|to (?:approve|confirm) "
                          r"(?:the )?)?minutes\b|minutes of (?:the )?(?:last|previous|meeting)|^cofnodion", re.I)


@dataclass(frozen=True)
class Context:
    """What the meeting record doesn't say about itself."""

    gss: str                # the council's GSS code
    council: str            # the council's name
    base_url: str           # its Modern.gov site
    committee_id: int
    committee_title: str
    kind: str               # "council", "cabinet" or "policy" (committees.py)


def _t(el: etree._Element, path: str) -> str:
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


def _plain(el: etree._Element, path: str) -> str:
    """A text field with HTML entities decoded ("Members&#39; Announcements")."""
    return html.unescape(_t(el, path))


def _bool(el: etree._Element, path: str) -> bool:
    return _t(el, path).lower() == "true"


def rows(root: etree._Element, ctx: Context, listed: date | None = None) -> tuple[dict, list[dict], list[dict]]:
    """(meeting, items, attendance) for one meeting."""
    mid = int(_t(root, "meetingid"))
    # the meeting's own date, else the one the committee's list of meetings gave (a meeting record with its date
    # missing stopped six councils loading, November 2026)
    found = parse_date(_t(root, "meetingdate")) or listed
    if found is None:
        raise ValueError(f"meeting {mid} has no date")
    d: date = found
    meeting_key = f"{ctx.gss}:{mid}"
    base = ctx.base_url.rstrip("/")

    items = []
    earlier_minutes = []
    for n, it in enumerate(root.iterfind("agendaitems/agendaitem")):
        iid = _t(it, "agendaitemid")
        minutes_html = _t(it, "minutesnonemptyhtmlbody")
        minutes = to_text(minutes_html)
        tables = vote_tables(minutes_html)
        docs = [(_t(doc, "title"), _t(doc, "url")) for doc in it.iterfind("linkeddocuments/linkeddoc")]
        if MINUTES_ITEM.search(_t(it, "agendaitemtitle")):
            earlier_minutes += [{"title": title, "url": url} for title, url in docs if url]
        items.append({
            "item_id": f"{meeting_key}:{iid}",
            "meeting_id": meeting_key,
            "gss": ctx.gss,
            "date": d,
            "year": d.year,
            "position": n,
            "number": _plain(it, "fulldisplaynumberformat") or _t(it, "minutesitemnumber"),
            "title": _plain(it, "agendaitemtitle"),
            "agenda_text": to_text(_t(it, "agendatext")),
            "minutes_text": minutes,
            "minutes_source": "html" if minutes else "",
            "vote_tables": json.dumps(tables) if tables else "",
            "is_decision": _bool(it, "isdecision"),
            "is_restricted": _bool(it, "isrestricted"),
            "is_call_in": _bool(it, "iscallin"),
            "declaration_count": int(_t(it, "declarationcount") or 0),
            "documents": len(docs),
            "url": f"{base}/mgAi.aspx?ID={iid}",
        })

    attendance = []
    for a in root.iterfind("attendees/attendee"):
        attendance.append({
            "meeting_id": meeting_key,
            "gss": ctx.gss,
            "date": d,
            "year": d.year,
            "member_id": a.get("memberid", ""),
            "member_type": a.get("membertype", ""),
            "name": a.get("name", ""),
            "role": a.get("roledescription", ""),
            "attendance": a.get("attendance", ""),
            "party_label": a.get("politicalparty", ""),
            "ward": a.get("ward", ""),
            # the body the member represents: on a strategic authority, their home council ("Bradford Council")
            "representing": a.get("representing", ""),
            "_keyposts": a.get("keyposts", ""),     # used only to tell the mayor; not stored
        })

    meeting = {
        "meeting_id": meeting_key,
        "gss": ctx.gss,
        "council": ctx.council,
        "committee_id": ctx.committee_id,
        "committee_title": ctx.committee_title,
        "kind": ctx.kind,
        "date": d,
        "year": d.year,
        "status": _t(root, "meetingstatus"),
        "location": _plain(root, "meetinglocation"),
        "webcast": _bool(root, "iswebcast"),
        "minutes_published": _bool(root, "minutepublished"),
        "items": len(items),
        "items_with_minutes": sum(1 for i in items if len(i["minutes_text"]) > 40),
        "earlier_minutes": json.dumps(earlier_minutes) if earlier_minutes else "",
        "minutes_document": "",
        "attendees": len(attendance),
        "url": f"{base}/ieListDocuments.aspx?CId={ctx.committee_id}&MId={mid}",
    }
    return meeting, items, attendance
