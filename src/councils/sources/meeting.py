"""One Modern.gov meeting (a GetMeeting response) as rows for the store: the meeting, its agenda items with their
minutes, and who attended."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from lxml import etree

from councils.parse.minutes import to_text
from councils.sources.modgov import parse_date


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


def _bool(el: etree._Element, path: str) -> bool:
    return _t(el, path).lower() == "true"


def rows(root: etree._Element, ctx: Context) -> tuple[dict, list[dict], list[dict]]:
    """(meeting, items, attendance) for one meeting."""
    mid = int(_t(root, "meetingid"))
    d: date = parse_date(_t(root, "meetingdate"))  # type: ignore[assignment]
    meeting_key = f"{ctx.gss}:{mid}"
    base = ctx.base_url.rstrip("/")

    items = []
    pdfs = []
    for n, it in enumerate(root.iterfind("agendaitems/agendaitem")):
        iid = _t(it, "agendaitemid")
        minutes = to_text(_t(it, "minutesnonemptyhtmlbody"))
        docs = [(_t(doc, "title"), _t(doc, "url")) for doc in it.iterfind("linkeddocuments/linkeddoc")]
        pdfs += [url for title, url in docs if "minute" in title.lower()]
        items.append({
            "item_id": f"{meeting_key}:{iid}",
            "meeting_id": meeting_key,
            "gss": ctx.gss,
            "date": d,
            "year": d.year,
            "position": n,
            "number": _t(it, "fulldisplaynumberformat") or _t(it, "minutesitemnumber"),
            "title": _t(it, "agendaitemtitle"),
            "agenda_text": to_text(_t(it, "agendatext")),
            "minutes_text": minutes,
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
        "location": _t(root, "meetinglocation"),
        "webcast": _bool(root, "iswebcast"),
        "minutes_published": _bool(root, "minutepublished"),
        "items": len(items),
        "items_with_minutes": sum(1 for i in items if len(i["minutes_text"]) > 40),
        "minutes_pdf_url": pdfs[0] if pdfs else "",
        "attendees": len(attendance),
        "url": f"{base}/ieListDocuments.aspx?CId={ctx.committee_id}&MId={mid}",
    }
    return meeting, items, attendance
