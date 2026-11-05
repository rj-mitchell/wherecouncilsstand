"""Reader for Civica's CMIS meetings system (and Nottinghamshire's variant of it, "DMS").

CMIS is an ASP.NET (DotNetNuke) site with no web service, so its pages are read as a browser would read them
(docs/DATA.md, "CMIS"):

* the committee lists (``Committees.aspx`` and the site's other pages of committees) link each committee's page,
  ``.../ctl/ViewCMIS_CommitteeDetails/mid/<m>/id/<committee>/Default.aspx``;
* a committee's page lists its meetings ten at a time, oldest first, in a grid paged by ASP.NET postbacks;
* a meeting's page, ``.../ctl/ViewMeetingPublic/mid/<m>/Meeting/<id>/Committee/<committee>/Default.aspx``, has its
  date, status and venue, the agenda (where the council enters one), its documents (``Document.ashx?...``), and
  grids of members who attended, sent apologies or were absent, and of declarations of interest, each paged 25 at a
  time;
* a councillor's page, ``.../ctl/ViewCMIS_Person/.../id/<person>/Default.aspx``, has their party and ward history
  with dates, from which the party at each meeting is read. A meeting with no party history covering its date
  gets no party: one is never guessed.

Minutes are rarely entered per agenda item; usually they are a document on the meeting's own page ("Minutes of the
Full Council meeting held on 27 January 2026") or at the item of the next meeting that approves them. The document
is read and split into the agenda's items, or kept whole as one "Minutes" item. Where the attendance grids are empty,
the "Present:" list at the top of the minutes is read instead.

Every response is cached under ``raw/cmis/<council>/`` (gzip), so a council is fetched once and parsed often.
Requests honour robots.txt (sources/robots.py): a site that forbids crawling is not read, and a refusal, bot check
or 403 is never worked around (docs/DECISIONS.md, 2).
"""

from __future__ import annotations

import gzip
import hashlib
import html as htmllib
import json
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

import httpx
from lxml import etree
from lxml import html as lhtml

from councils import committees as committee_kinds
from councils import extract
from councils.config import Settings
from councils.parse import votes
from councils.parse.minutes import to_text, vote_tables
from councils.registry import Council
from councils.sources import documents, robots
from councils.sources.meeting import MINUTES_ITEM

log = logging.getLogger(__name__)

ROBOTS_ERROR = "robots.txt forbids crawling"
# a firewall's or bot check's page served with 200 (as modgov.probe recognises them)
_REFUSAL = re.compile(r"has been blocked|request rejected|connection denied by geolocation|_Incapsula_Resource|"
                      r"<title>\s*(?:access denied|just a moment|attention required)", re.I)


class CmisError(RuntimeError):
    pass


class Refused(CmisError):
    """The site refused the crawler (403, a bot check), or its robots.txt forbids the page."""


@dataclass(frozen=True)
class CommitteeRef:
    id: int
    title: str
    url: str


@dataclass(frozen=True)
class MeetingRef:
    id: int
    committee_id: int
    date: date
    url: str


# Pages -------------------------------------------------------------------------------------------------------------

def _root(text: str) -> etree._Element:
    root = lhtml.fromstring(text or "<html></html>")
    for bad in root.xpath("//script|//style"):
        bad.drop_tree()
    return root


def _clean(s: str | None) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(s or "")).strip()


def _inner_html(el: etree._Element) -> str:
    return (el.text or "") + "".join(etree.tostring(c, encoding="unicode", method="html") for c in el)


def parse_date(text: str) -> date | None:
    """"06 January 2026 - 19:30 : 20:30", "27 Jan 2026 - 19:30", "Thu 3 May 2012", "2014-06-03"."""
    t = _clean(text)
    m = re.search(r"(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})", t)
    if m:
        mon = documents.MONTHS.get(m.group(2).lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", t) or None
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b", t)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
        except ValueError:
            return None
    return None


def committee_links(text: str, page_url: str) -> list[CommitteeRef]:
    """Committees linked from a page of committees, in the order given."""
    out, seen = [], set()
    for a in _root(text).iter("a"):
        href = a.get("href") or ""
        m = re.search(r"/ctl/ViewCMIS_CommitteeDetails/mid/\d+/id/(\d+)/", href, re.I)
        if not m or int(m.group(1)) in seen:
            continue
        title = _clean(a.get("title")) or _clean(a.text_content())
        if not title:
            continue
        seen.add(int(m.group(1)))
        out.append(CommitteeRef(int(m.group(1)), title, urljoin(page_url, href)))
    return out


def committee_pages(text: str, page_url: str, base: str) -> list[str]:
    """The site's own pages of committees, linked from its navigation: "Committees.aspx", "FormerCommittees.aspx",
    "CommitteesandNotices/CommitteesfromMay2016.aspx", "Committees/HistoricalCommittees.aspx"."""
    base_path = urlparse(base).path.rstrip("/").lower()
    out = []
    for a in _root(text).iter("a"):
        url = urljoin(page_url, a.get("href") or "").split("#")[0]
        u = urlparse(url)
        path = u.path.lower()
        if (u.netloc.lower() != urlparse(base).netloc.lower() or not path.startswith(base_path + "/")
                or not path.endswith(".aspx") or "/ctl/" in path or "/tabid/" in path):
            continue
        if "committee" in path[len(base_path):] and url not in out:
            out.append(url)
    return out


def _grid(root: etree._Element, name: str) -> etree._Element | None:
    found = root.xpath(f"//div[contains(@class, 'RadGrid') and substring(@id, string-length(@id) - "
                       f"{len(name) - 1}) = '{name}']")
    return found[0] if found else None


def pager(text_or_root: str | etree._Element, grid: str) -> tuple[int, int]:
    """(current page, number of pages) of a paged grid; (1, 1) when it isn't paged."""
    root = _root(text_or_root) if isinstance(text_or_root, str) else text_or_root
    g = _grid(root, grid)
    if g is None:
        return 1, 1
    info = g.xpath(".//*[contains(@class, 'rgInfoPart')]")
    m = re.search(r"Page\s+(\d+)\s+of\s+(\d+)", _clean(info[0].text_content())) if info else None
    return (int(m.group(1)), int(m.group(2))) if m else (1, 1)


def pager_target(text: str, grid: str, page: int) -> str | None:
    """The postback target that shows ``page`` of a grid: its page link, or the "previous/next pages" link of the
    pager's window that leads to it."""
    root = _root(text)
    g = _grid(root, grid)
    if g is None:
        return None
    links = {}
    for a in g.xpath(".//*[contains(@class, 'rgPager')]//a"):
        m = re.search(r"__doPostBack\('([^']+)'", htmllib.unescape(a.get("href") or ""))
        if m:
            links[_clean(a.get("title"))] = m.group(1)
    if f"Go to Page {page}" in links:
        return links[f"Go to Page {page}"]
    shown = [int(t.rsplit(" ", 1)[1]) for t in links if re.fullmatch(r"Go to Page \d+", t)]
    if shown and page < min(shown):
        return links.get("Previous Pages")
    if shown and page > max(shown):
        return links.get("Next Pages")
    return None


def form_fields(text: str) -> dict[str, str]:
    """The page's form, as a browser would post it (hidden fields, text inputs and checked boxes; no buttons)."""
    root = lhtml.fromstring(text)
    forms = root.xpath("//form")
    if not forms:
        raise CmisError("no form on the page")
    data = {}
    for el in forms[0].xpath(".//input"):
        name, kind = el.get("name"), (el.get("type") or "text").lower()
        if not name or kind in ("submit", "image", "button", "reset", "file"):
            continue
        if kind in ("checkbox", "radio") and el.get("checked") is None:
            continue
        data[name] = el.get("value") or ""
    return data


def meeting_links(text: str, page_url: str) -> list[MeetingRef]:
    """The meetings in a committee page's grid."""
    root = _root(text)
    g = _grid(root, "gridMeetings")
    scope = g if g is not None else root
    out, seen = [], set()
    for a in scope.iter("a"):
        href = a.get("href") or ""
        m = re.search(r"/ctl/ViewMeetingPublic/mid/\d+/Meeting/(\d+)/Committee/(\d+)/", href, re.I)
        if not m or int(m.group(1)) in seen:
            continue
        d = parse_date(a.text_content())
        if d is None:
            continue
        seen.add(int(m.group(1)))
        out.append(MeetingRef(int(m.group(1)), int(m.group(2)), d, urljoin(page_url, href)))
    return out


def _labelled(root: etree._Element) -> dict[str, str]:
    """The meeting summary's fields by label: {"committee": "Council", "date/time": "27 Jan 2026 - 19:30", ...}."""
    out = {}
    for span in root.xpath("//div[contains(@class, 'SummaryPanel')]//span[contains(@id, '_lblLabel')]"):
        label = _clean(span.text_content()).rstrip(":").lower()
        holder = span.xpath("ancestor::div[contains(concat(' ', @class, ' '), ' holder ')][1]")
        if not holder:
            continue
        values = holder[0].xpath("./div[contains(concat(' ', @class, ' '), ' Value ')]")
        if values and label not in out:
            out[label] = _clean(values[0].text_content())
    return out


def spaced(title: str) -> str:
    """A document title written as one word, spaced out so its words and date can be read:
    "02-MinutesOfLastMeetingHeldOn3March2021" -> "02-Minutes Of Last Meeting Held On 3 March 2021"."""
    return re.sub(r"(?<=[a-z])(?=[A-Z])|(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z]{2})(?!(?:st|nd|rd|th)\b)", " ", title)


def _documents_in(el: etree._Element, page_url: str) -> list[dict]:
    out = []
    for a in el.xpath(".//a[contains(translate(@href, 'DOCUMENTASHX', 'documentashx'), 'document.ashx')]"):
        title = _clean(a.text_content())
        if not title:
            m = re.match(r"Click to view:?\s*'?(.*?)'?$", _clean(a.get("title")))
            title = m.group(1) if m else _clean(a.get("title"))
        out.append({"title": spaced(title), "url": urljoin(page_url, a.get("href"))})
    return out


def _grid_rows(root: etree._Element, grid: str, page_url: str) -> list[dict]:
    g = _grid(root, grid)
    if g is None:
        return []
    rows = []
    for tr in g.xpath(".//table[contains(@class, 'rgMasterTable')]/tbody/tr[contains(@class, 'rgRow') or "
                      "contains(@class, 'rgAltRow')]"):
        cells = tr.xpath("./td")
        if not cells:
            continue
        link = cells[0].xpath(".//a[contains(@href, 'ViewCMIS_Person')]")
        href = urljoin(page_url, link[0].get("href")) if link else ""
        pid = re.search(r"/id/(\d+)/", href)
        rows.append({"name": _clean(cells[0].text_content()), "person_id": pid.group(1) if pid else "",
                     "person_url": href, "cells": [_clean(c.text_content()) for c in cells]})
    return rows


ATTENDANCE_GRIDS = {"gridAttended": ("Present", "Committee Member"),
                    "gridOthersAttended": ("In attendance", "Other Member"),
                    "gridApology": ("Apologies", "Committee Member"),
                    "gridAbsent": ("Absent", "Committee Member")}
PAGED_GRIDS = (*ATTENDANCE_GRIDS, "gridDOI")
_RESTRICTED = re.compile(r"exempt|private|confidential|part (?:2|ii|b)\b|closed session|not for publication", re.I)


def meeting_page(text: str, page_url: str) -> dict:
    """What a meeting's page holds: summary fields, agenda items, documents, attendance and declarations."""
    root = _root(text)
    fields = _labelled(root)
    items = []
    for section in root.xpath("//div[contains(concat(' ', @class, ' '), ' Sections ')]"
                              "//div[contains(concat(' ', @class, ' '), ' Section ')]"):
        names = section.xpath("./div[contains(concat(' ', @class, ' '), ' Name ')]")
        section_name = _clean(names[0].text_content()) if names else ""
        for it in section.xpath(".//div[contains(concat(' ', @class, ' '), ' Item ')]"):
            title_el = it.xpath("./div[contains(concat(' ', @class, ' '), ' Title ')]")
            if not title_el:
                continue
            t = title_el[0]
            num = t.xpath("./span[contains(@class, 'Number')]")
            number = _clean(num[0].text_content()) if num else ""
            link = t.xpath("./a")
            if link:
                title = _clean(link[0].text_content())
            else:   # the title's own text, without the number and file size
                title = _clean(" ".join([t.text or ""] + [c.tail or "" for c in t]))
            details = it.xpath("./div[contains(concat(' ', @class, ' '), ' Details ')]")
            minute = it.xpath(".//div[contains(concat(' ', @class, ' '), ' MinuteDetails ')]")
            minutes_html = _inner_html(minute[0]) if minute else ""
            items.append({
                "number": number,
                "title": title,
                "agenda_text": to_text(_inner_html(details[0])) if details else "",
                "minutes_html": minutes_html if to_text(minutes_html) else "",
                "documents": _documents_in(it, page_url),
                "is_decision": bool(it.xpath(".//a[contains(@href, 'DecisionDetails')]")),
                "is_restricted": bool(_RESTRICTED.search(section_name)),
            })
    in_items = {d["url"] for it in items for d in it["documents"]}
    docs = [d for d in _documents_in(root, page_url) if d["url"] not in in_items]
    attendance = [a for grid in ATTENDANCE_GRIDS for a in grid_attendance(root, grid, page_url)]
    declarations = grid_declarations(root, page_url)
    # the meeting's own panel (not the site's header and footer, which may link the council's YouTube channel)
    panel = root.xpath("//div[contains(@id, 'ViewMeetingPublic_pnl') or contains(@class, 'SummaryPanel')]")
    panel_text = " ".join(_clean(p.text_content()) for p in panel[:3])
    return {
        "committee": fields.get("committee", ""),
        "date": parse_date(fields.get("date/time", "")),
        "status": fields.get("status", ""),
        "location": fields.get("venue", ""),
        "webcast": bool(re.search(r"webcast|broadcast|live ?stream|youtube\.com/watch|youtu\.be/", panel_text, re.I)),
        "items": items,
        "documents": docs,
        "attendance": attendance,
        "declarations": declarations,
    }


def grid_attendance(root: etree._Element, grid: str, page_url: str) -> list[dict]:
    status, role = ATTENDANCE_GRIDS[grid]
    return [{"name": r["name"], "person_id": r["person_id"], "person_url": r["person_url"], "attendance": status,
             "role": role} for r in _grid_rows(root, grid, page_url)]


def grid_declarations(root: etree._Element, page_url: str) -> list[dict]:
    """Declarations of interest: (member, item reference)."""
    return [{"name": r["name"], "person_id": r["person_id"], "item": (r["cells"] + [""])[1]}
            for r in _grid_rows(root, "gridDOI", page_url)]


def party_history(text: str, grid: str = "grdRadPartyHistory") -> list[tuple[str, date | None, date | None]]:
    """A councillor's party (or ward) history: (name, from, to), with ``to`` None while it continues."""
    root = _root(text)
    out = []
    for r in _grid_rows(root, grid, ""):
        cells = r["cells"]
        if len(cells) >= 2 and cells[0]:
            out.append((cells[0], parse_date(cells[1]), parse_date(cells[2]) if len(cells) > 2 else None))
    return out


def on_date(history: list[tuple[str, date | None, date | None]], d: date) -> str:
    """The entry covering a date, or "" if none does."""
    hits = [(f, name) for name, f, t in history if f and f <= d and (t is None or d <= t)]
    return max(hits)[1] if hits else ""


# The minutes' "Present:" list --------------------------------------------------------------------------------------

_PRESENT_END = re.compile(r"\n\s*(?:apologies|also (?:present|in attendance)|in attendance|officers?|absent|"
                          r"(?:\d+\.?\s+)?declarations?|\d+\.\s|\d+\s+[A-Z][a-z])", re.I)
_ROLE_WORDS = r"(?:(?:deputy |vice[- ])?(?:lord |civic )?(?:mayor|chair(?:man|woman|person)?|leader|presiding member))"


# the minutes' heading, laid out next to the list in some documents: "MINUTES", "Full Council", "Tuesday"
_NOT_A_NAME = re.compile(r"\b[A-Z]{3,}\b|\b(?i:minutes|council|committee|cabinet|meeting|present|chamber|hall|room|"
                         r"centre|monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b")


def present_list(text: str) -> list[tuple[str, str]]:
    """(name, role) for each councillor in the minutes' "Present:" list: "Councillors Kendrick (Lord Mayor), Wright,
    Sands (M) and Young"; "The Mayor (Councillor L Scanlan) in the Chair, Councillors Atkinson, Dixon, D"."""
    m = re.search(r"\bpresent\s*:", text[:6000], re.I)
    if not m:
        return []
    rest = text[m.end():m.end() + 4000]
    end = _PRESENT_END.search(rest)
    block = rest[:end.start()] if end else rest[:1500]
    block = re.sub(r"[ \t\xa0]+", " ", block.replace("’", "'"))    # lines are kept: some lists are one per line
    out: list[tuple[str, str]] = []
    chair = re.search(rf"(?:the\s+)?({_ROLE_WORDS})\s*\((?:councill?or|cllr)\.?\s+([^)]+)\)(?:\s+in\s+the\s+chair)?",
                      block, re.I)
    if chair:
        out.append((re.sub(r"\s+", " ", chair.group(2)).strip(), chair.group(1).strip().title()))
        block = block[:chair.start()] + " , " + block[chair.end():]
    block = re.sub(r"\b(?:councill?ors?|cllrs?)\b\.?", ",", block, flags=re.I)
    block = re.sub(r"\bin\s+the\s+chair\b", "", block, flags=re.I)
    for tok in re.split(r",|;|\band\b|&|\n", block):
        tok = tok.strip(" .;:")
        if not tok:
            continue
        role = ""
        rm = re.search(rf"\((?:the\s+)?({_ROLE_WORDS})\)", tok, re.I)
        if rm:
            role = rm.group(1).title()
            tok = (tok[:rm.start()] + tok[rm.end():]).strip()
        if re.fullmatch(r"\([A-Z]{1,2}\)", tok) and out:      # "Sands" / "(M)" split over two lines
            out[-1] = (f"{out[-1][0]} {tok}", out[-1][1])
            continue
        if re.fullmatch(r"[A-Z](?:\.?\s?[A-Z])?\.?", tok) and out and " " not in out[-1][0]:
            out[-1] = (f"{tok} {out[-1][0]}", out[-1][1])      # "Dixon, D" -> "D Dixon"
            continue
        if not re.fullmatch(r"(?:[A-Z][\w'.-]*\s+){0,3}[A-Z][\w'-]+(?:\s*\([A-Z]{1,2}\))?", tok):
            continue
        if (not role and re.fullmatch(rf"(?:the\s+)?{_ROLE_WORDS}", tok, re.I)) or _NOT_A_NAME.search(tok):
            continue
        out.append((tok, role))
    return out


def slug(name: str) -> str:
    n = re.sub(r"\b(?:councill?ors?|cllrs?)\b\.?", " ", name, flags=re.I)
    return re.sub(r"[^a-z0-9]+", "-", n.lower()).strip("-")


def _surname(name: str) -> str:
    n = re.sub(r"\([^)]*\)", " ", name)
    words = [w for w in re.sub(r"[^\w' -]", " ", votes_honours(n)).split() if w]
    return words[-1].lower() if words else ""


def votes_honours(name: str) -> str:
    from councils.parse.votes import _HONOURS

    return _HONOURS.sub(" ", name)


# Minutes documents ---------------------------------------------------------------------------------------------------

def repair_pdf(data: bytes) -> bytes:
    """CMIS appends an update to some PDFs whose cross-reference offsets are a few bytes out, which some readers
    (pdfminer) can't recover from. Point each ``startxref`` and ``/Prev`` at the nearest cross-reference section."""
    def fix(m: re.Match) -> bytes:
        n = int(m.group(2))
        if data[n:n + 4] == b"xref" or re.match(rb"\d+\s+\d+\s+obj", data[n:n + 24]):
            return m.group(0)
        lo = max(0, n - 64)
        near = [lo + x.start() for x in re.finditer(rb"xref|\d+\s+\d+\s+obj", data[lo:n + 64])]
        near = [x for x in near if data[x:x + 4] == b"xref" or x == lo or not data[x - 1:x].isdigit()]
        if not near:
            return m.group(0)
        new = str(min(near, key=lambda x: abs(x - n)))
        return m.group(0) if len(new) > len(m.group(2)) else m.group(1) + new.zfill(len(m.group(2))).encode()

    return re.sub(rb"(startxref\s+|/Prev\s+)(\d+)", fix, data)


def pdf_text(data: bytes) -> str:
    text = documents.pdf_text(data)
    if len(text.strip()) < 200 and data.startswith(b"%PDF"):
        fixed = repair_pdf(data)
        if fixed != data:
            text = documents.pdf_text(fixed) or text
    return text


def _is_minutes(title: str) -> bool:
    return bool(re.search(r"\bminute", title, re.I)) and not re.search(r"summary of decisions|action|appendi|minute (?:no|number)", title, re.I)


def title_dates(title: str, on_or_before: date) -> set[date]:
    """Dates in a document title (documents.dates_in), and dates written without a year ("Public Minutes of 9 February
    Cabinet meeting", Warwick), taken as the latest such day on or before the meeting whose page lists it."""
    out = documents.dates_in(title)
    for d, mon in re.findall(r"\b(?=(\d{1,2})(?:\s?(?:st|nd|rd|th))?\s+([a-z]{3,9})\b(?!\.?,?\s+\d{2,4}\b))", title.lower()):
        if mon in documents.MONTHS:
            for y in (on_or_before.year, on_or_before.year - 1):
                try:
                    when = date(y, documents.MONTHS[mon], int(d))
                except ValueError:
                    continue
                if when <= on_or_before:
                    out.add(when)
                    break
    return out


def own_minutes(docs: list[dict], meeting_date: date) -> dict | None:
    """The meeting's own minutes among the documents on its page: titled as minutes, with its date."""
    for d in docs:
        if _is_minutes(d["title"]) and meeting_date in title_dates(d["title"], meeting_date):
            return d
    return None


def choose(meeting_date: date, later: list[dict]) -> dict | None:
    """As documents.choose, reading dates written without a year too: this meeting's minutes among the minutes
    documents of the committee's following meetings ({"date", "docs"}, nearest first)."""
    for n, x in enumerate(later[:3]):
        dated = [d for d in x["docs"] if meeting_date in title_dates(d["title"], x["date"])]
        if dated:
            return dated[0]
        if n == 0 and len(x["docs"]) == 1 and not title_dates(x["docs"][0]["title"], x["date"]):
            return x["docs"][0]   # the very next meeting approves one set of minutes, with no date given
    return None


def all_documents(page: dict) -> list[dict]:
    return [d for it in page["items"] for d in it["documents"]] + page["documents"]


def earlier_minutes(page: dict, meeting_date: date) -> list[dict]:
    """Minutes of earlier meetings on this meeting's page: at the item approving them, or among its documents titled
    as minutes, leaving out its own."""
    out = [d for it in page["items"] if MINUTES_ITEM.search(it["title"]) for d in it["documents"]]
    out += [d for d in all_documents(page) if _is_minutes(d["title"])]
    out = [d for d in out if meeting_date not in title_dates(d["title"], meeting_date)]
    seen, uniq = set(), []
    for d in out:
        if d["url"] not in seen:
            seen.add(d["url"])
            uniq.append({"title": d["title"], "url": d["url"]})
    return uniq


# Transport -----------------------------------------------------------------------------------------------------------

class Client:
    """One council's CMIS site: polite, cached requests."""

    _locks: dict[str, threading.Lock] = {}

    def __init__(self, settings: Settings, council: str, base_url: str):
        cfg = settings.modgov
        self.council = council
        self.base = base_url.rstrip("/")
        self.cache = settings.raw_dir / "cmis" / council
        self.user_agent = cfg.get("user_agent", "WhereCouncilsStand")
        self.interval = float(cfg.get("min_interval_seconds", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self.refetch_days = int(cfg.get("refetch_days", 120))
        self.http = httpx.Client(headers={"User-Agent": self.user_agent},
                                 timeout=float(cfg.get("timeout_seconds", 40)), follow_redirects=True)
        self._last = 0.0
        self._lock = self._locks.setdefault(urlparse(self.base).netloc.lower(), threading.Lock())
        self.requests = 0

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def allowed(self, url: str) -> bool:
        """robots.txt allows the page. Paths are also compared ignoring case, as these (IIS) sites treat them: a rule
        for ``/DMS/Document.ashx`` covers ``/dms/document.ashx`` too."""
        if not robots.allowed(url, self.user_agent):
            return False
        u = urlparse(url)
        rp = robots._parser(f"{u.scheme}://{u.netloc}", self.user_agent)
        if rp is None:
            return False
        entry = (next((e for e in rp.entries if "*" not in e.useragents and e.applies_to(self.user_agent)), None)
                 or next((e for e in rp.entries if "*" in e.useragents), None) or rp.default_entry)
        if entry is None:
            return True
        path = (u.path or "/").lower()
        for line in entry.rulelines:      # the first rule that applies decides, as in urllib.robotparser
            rule = line.path.lower()
            if rule == "*" or path.startswith(rule):
                return line.allowance
        return True

    def _delay(self, url: str) -> float:
        """The interval between requests: the configured one, or longer if robots.txt asks (Crawl-delay)."""
        u = urlparse(url)
        rp = robots._parser(f"{u.scheme}://{u.netloc}", self.user_agent)
        try:
            asked = float(rp.crawl_delay(self.user_agent) or 0) if rp else 0.0
        except (TypeError, ValueError):
            asked = 0.0
        return max(self.interval, asked)

    def _request(self, method: str, url: str, data: dict | None = None) -> httpx.Response:
        if not self.allowed(url):
            raise Refused(f"{ROBOTS_ERROR}: {url}")
        interval = self._delay(url)
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries):
                wait = interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = self.http.request(method, url, data=data)
                    self._last = time.monotonic()
                    self.requests += 1
                    if r.status_code in (401, 403) and "/login.aspx" in str(r.url).lower():
                        raise CmisError(f"{self.council}: the page needs a login: {url}")   # not a refusal
                    if r.status_code in (401, 403, 429) or (r.status_code == 200 and "html" in
                                                            r.headers.get("content-type", "") and
                                                            _REFUSAL.search(r.text[:5000])):
                        raise Refused(f"{self.council}: the site refused the request (HTTP {r.status_code}): {url}")
                    if r.status_code == 200:
                        return r
                    last_error = CmisError(f"{self.council}: HTTP {r.status_code}: {url}")
                    if r.status_code in (400, 404, 410):
                        break
                except httpx.HTTPError as e:
                    self._last = time.monotonic()
                    last_error = CmisError(f"{self.council}: {type(e).__name__}: {url}")
                time.sleep(2 * (attempt + 1))
            raise last_error or CmisError(url)

    def _path(self, name: str) -> Path:
        return self.cache / name

    def _fresh(self, path: Path, refresh: bool, max_age_days: float | None) -> bool:
        if not path.exists():
            return True
        if refresh:
            return True
        return max_age_days is not None and (time.time() - path.stat().st_mtime) > max_age_days * 86_400

    def _store(self, path: Path, text: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(gzip.compress(text.encode("utf-8")))
        tmp.replace(path)

    def page(self, name: str, url: str, refresh: bool = False, max_age_days: float | None = None,
             postback: tuple[str, str] | None = None) -> tuple[str, bool]:
        """(page, fetched now). A cached copy is used unless it is missing, ``refresh`` is set or it is older than
        ``max_age_days``. ``postback`` is (the page posted from, the control's postback target). If fetching again
        fails, a cached copy is used: a server that is down mustn't lose what is already known."""
        path = self._path(name + ".html.gz")
        if not self._fresh(path, refresh, max_age_days):
            return gzip.decompress(path.read_bytes()).decode("utf-8"), False
        try:
            if postback:
                data = form_fields(postback[0])
                data["__EVENTTARGET"], data["__EVENTARGUMENT"] = postback[1], ""
                r = self._request("POST", url, data)
            else:
                r = self._request("GET", url)
        except CmisError as e:
            if path.exists() and not isinstance(e, Refused):
                log.warning("%s; using the cached copy", e)
                return gzip.decompress(path.read_bytes()).decode("utf-8"), False
            raise
        self._store(path, r.text)
        return r.text, True

    def cached(self, name: str) -> str | None:
        path = self._path(name + ".html.gz")
        return gzip.decompress(path.read_bytes()).decode("utf-8") if path.exists() else None

    def document(self, url: str) -> bytes | None:
        """A document (usually a PDF), cached by its address; None if robots.txt forbids it or it isn't a PDF."""
        path = self.cache / "documents" / f"{hashlib.sha1(url.encode()).hexdigest()[:20]}.pdf"
        if path.exists():
            return path.read_bytes()
        if not self.allowed(url):
            return None
        r = self._request("GET", url)
        if not r.content.startswith(b"%PDF"):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return r.content


# Reading a site ------------------------------------------------------------------------------------------------------

def _before(url: str, start: date | None) -> bool:
    """A page of committees for council years wholly before ``start``: ".../CommitteesandNotices/2015-16.aspx"."""
    m = re.search(r"(?<!\d)(20\d\d)[-_](\d\d)(?!\d)", urlparse(url).path)
    return bool(start and m and 2000 + int(m.group(2)) < start.year)


def find_committees(client: Client, max_age_days: float | None = None, start: date | None = None) -> list[CommitteeRef]:
    """Every committee the site lists: from ``Committees.aspx`` and the other pages of committees its navigation
    links (former and historical committees, committees by year, leaving out years before ``start``)."""
    base = client.base
    seen_pages: set[str] = set()
    todo = [f"{base}/Committees.aspx", f"{base}/"]
    found: dict[int, CommitteeRef] = {}
    answered = False
    while todo and len(seen_pages) < 40:
        url = todo.pop(0)
        if url.lower() in seen_pages:
            continue
        seen_pages.add(url.lower())
        name = "lists/" + (re.sub(r"[^\w]+", "_", urlparse(url).path[len(urlparse(base).path):]).strip("_")
                           or "home")
        try:
            text, _ = client.page(name, url, max_age_days=max_age_days)
        except Refused:
            raise
        except CmisError as e:
            log.info("%s", e)
            continue
        answered = True
        for c in committee_links(text, url):
            found.setdefault(c.id, c)
        for p in committee_pages(text, url, base):
            if p.lower() not in seen_pages and not _before(p, start):
                todo.append(p)
    if not answered:
        raise CmisError(f"no CMIS site at {base}")
    return list(found.values())


def list_meetings(client: Client, committee: CommitteeRef, start: date, end: date) -> list[MeetingRef]:
    """A committee's meetings from ``start`` to ``end``. The grid is paged oldest first; the page shown first is the
    one around today, so pages are walked back to ``start`` and on to ``end``. A listing running to today is fetched
    again once a day (or on every update), so new meetings appear; one wholly in the past is fetched once."""
    current = end >= date.today()
    key = f"committee/{committee.id}_{start:%Y%m%d}_{'latest' if current else f'{end:%Y%m%d}'}"
    max_age = 0.9 if current else None
    cached = client.cached(f"{key}/first")
    if current and cached is not None:   # a committee that stopped meeting over a year ago is checked monthly
        cur, total = pager(cached, "gridMeetings")
        ms = meeting_links(cached, committee.url)
        if cur == total and (not ms or max(m.date for m in ms) < date.fromordinal(date.today().toordinal() - 365)):
            max_age = 30
    first, fresh = client.page(f"{key}/first", committee.url, max_age_days=max_age)
    cur, total = pager(first, "gridMeetings")
    pages = {cur: first}
    refs = {m.id: m for m in meeting_links(first, committee.url)}

    def visit(frm: int, to: int) -> list[MeetingRef]:
        target = pager_target(pages[frm], "gridMeetings", to)
        if not target:
            raise CmisError(f"{client.council} committee {committee.id}: no way to page {to}")
        text, _ = client.page(f"{key}/p{to}", committee.url, refresh=fresh, postback=(pages[frm], target))
        got, _n = pager(text, "gridMeetings")
        if got != to:
            raise CmisError(f"{client.council} committee {committee.id}: asked for page {to}, got {got}")
        pages[to] = text
        ms = meeting_links(text, committee.url)
        refs.update({m.id: m for m in ms})
        return ms

    k, ms = cur, list(refs.values())
    while k > 1 and (not ms or min(m.date for m in ms) >= start):
        ms = visit(k, k - 1)
        k -= 1
    k, ms = cur, meeting_links(first, committee.url)
    while k < total and (not ms or max(m.date for m in ms) <= end):
        ms = visit(k, k + 1)
        k += 1
    return sorted((m for m in refs.values() if start <= m.date <= end), key=lambda m: (m.date, m.id))


def fetch_meeting(client: Client, ref: MeetingRef, refresh: bool = False) -> tuple[str, list[tuple[str, str]], bool]:
    """A meeting's page, the further pages of its paged grids (attendance over 25 names, declarations) as (grid,
    page), and whether the page was fetched now."""
    recent = (date.today() - ref.date).days < client.refetch_days
    text, fresh = client.page(f"meeting/{ref.id}", ref.url, refresh=refresh, max_age_days=0.9 if recent else None)
    extra = []
    for grid in PAGED_GRIDS:
        last = text
        _, total = pager(text, grid)
        for k in range(2, total + 1):
            target = pager_target(last, grid, k)
            if not target:
                break
            last, _ = client.page(f"meeting/{ref.id}_{grid}_{k}", ref.url, refresh=fresh, postback=(last, target))
            extra.append((grid, last))
    return text, extra, fresh


def _item_key(ref: str) -> str:
    m = re.search(r"(?:item\s*)?(\d+[a-z]?)", ref.lower())
    return m.group(1) if m else ""


def meeting_rows(gss: str, council: str, committee: CommitteeRef, kind: str, ref: MeetingRef, text: str,
                 extra: list[tuple[str, str]] = ()) -> tuple[dict, list[dict], list[dict]]:
    """(meeting, items, attendance) for one meeting, in the store's columns (sources/meeting.py). The meeting keeps
    its page's documents under ``_documents`` until its minutes are read."""
    page = meeting_page(text, ref.url)
    for grid, more in extra:   # further pages of the grids
        root = _root(more)
        if grid == "gridDOI":
            page["declarations"] += grid_declarations(root, ref.url)
        else:
            page["attendance"] += grid_attendance(root, grid, ref.url)
    d = page["date"] or ref.date
    meeting_id = f"{gss}:{ref.id}"
    decl_by_item: dict[str, int] = {}
    for dcl in page["declarations"]:
        decl_by_item[_item_key(dcl["item"])] = decl_by_item.get(_item_key(dcl["item"]), 0) + 1
    items = []
    for n, it in enumerate(page["items"]):
        minutes = to_text(it["minutes_html"])
        tables = vote_tables(it["minutes_html"])
        items.append({
            "item_id": f"{meeting_id}:{n}",
            "meeting_id": meeting_id,
            "gss": gss,
            "date": d,
            "year": d.year,
            "position": n,
            "number": it["number"],
            "title": it["title"],
            "agenda_text": it["agenda_text"],
            "minutes_text": minutes,
            "minutes_source": "html" if minutes else "",
            "vote_tables": json.dumps(tables) if tables else "",
            "is_decision": it["is_decision"],
            "is_restricted": it["is_restricted"],
            "is_call_in": False,
            "declaration_count": decl_by_item.pop(_item_key(it["number"]), 0) if it["number"] else 0,
            "documents": len(it["documents"]),
            "url": ref.url,
        })
    seen, attendance = set(), []
    for a in page["attendance"]:
        member_id = a["person_id"] or slug(a["name"])
        if not member_id or member_id in seen:
            continue
        seen.add(member_id)
        attendance.append({
            "meeting_id": meeting_id, "gss": gss, "date": d, "year": d.year, "member_id": member_id,
            "member_type": "", "name": a["name"], "role": a["role"], "attendance": a["attendance"],
            "party_label": "", "ward": "", "_person_url": a["person_url"],
        })
    earlier = earlier_minutes(page, d)
    meeting = {
        "meeting_id": meeting_id,
        "gss": gss,
        "council": council,
        "committee_id": committee.id,
        "committee_title": committee.title,
        "kind": kind,
        "date": d,
        "year": d.year,
        "status": page["status"],
        "location": page["location"],
        "webcast": page["webcast"],
        "minutes_published": any(i["minutes_text"] for i in items),
        "items": len(items),
        "items_with_minutes": sum(1 for i in items if len(i["minutes_text"]) > 40),
        "earlier_minutes": json.dumps(earlier) if earlier else "",
        "minutes_document": "",
        "attendees": len(attendance),
        "url": ref.url,
        "_documents": all_documents(page),
    }
    return meeting, items, attendance


def _whole(meeting: dict, text: str, url: str) -> dict:
    return {"item_id": f"{meeting['meeting_id']}:minutes", "meeting_id": meeting["meeting_id"], "gss": meeting["gss"],
            "date": meeting["date"], "year": meeting["year"], "position": -1, "number": "", "title": "Minutes",
            "agenda_text": "", "minutes_text": text.strip(), "minutes_source": "document", "vote_tables": "",
            "is_decision": False, "is_restricted": False, "is_call_in": False, "declaration_count": 0,
            "documents": 0, "url": url}


def apply_minutes(meeting: dict, items: list[dict], attendance: list[dict], text: str, url: str) -> list[dict]:
    """Put a minutes document's text into the meeting's items (or one "Minutes" item), take roles from its "Present:"
    list, and, if the site recorded no attendance, take the attendance from that list. Returns items to add."""
    meeting["minutes_document"] = url
    meeting["minutes_published"] = True
    own = sorted(items, key=lambda i: i["position"])
    listed = votes.line_lists(text)     # Sunderland's recorded votes: one member to a line
    parts = documents.split_into_items(listed, own) if own else None
    extra = []
    if parts:
        for it in own:
            if it["item_id"] in parts and not it["minutes_text"]:
                it["minutes_text"], it["minutes_source"] = parts[it["item_id"]], "document"
    else:
        extra.append(_whole(meeting, listed, url))
    meeting["items_with_minutes"] = sum(1 for i in own if len(i["minutes_text"]) > 40) or (1 if extra else 0)
    present = present_list(text)
    by_surname: dict[str, list[dict]] = {}
    for a in attendance:
        by_surname.setdefault(_surname(a["name"]), []).append(a)
    for name, role in present:
        hits = by_surname.get(_surname(name), [])
        if role and len(hits) == 1:
            hits[0]["role"] = role
    if not attendance:
        seen = set()
        for name, role in present:
            member_id = slug(name)
            if not member_id or member_id in seen:
                continue
            seen.add(member_id)
            attendance.append({
                "meeting_id": meeting["meeting_id"], "gss": meeting["gss"], "date": meeting["date"],
                "year": meeting["year"], "member_id": member_id, "member_type": "",
                "name": name if re.match(r"(?i)councill?or", name) else f"Councillor {name}", "role": role or
                "Committee Member", "attendance": "Present", "party_label": "", "ward": "", "_person_url": "",
            })
        meeting["attendees"] = len(attendance)
    return extra


def fetch(settings: Settings, council: Council, start: date, end: date, update: bool = False):
    """(Result, meetings, items, attendance) for a council on CMIS, in the rows the Modern.gov path writes."""
    from councils.ingest import Result

    res = Result(council.gss)
    base = (council.modgov_url or "").rstrip("/")
    if not base:
        res.error = "no CMIS site"
        return res, [], [], []
    meetings: list[dict] = []
    items: list[dict] = []
    attendance: list[dict] = []
    with Client(settings, council.gss, base) as client:
        if not client.allowed(f"{base}/Committees.aspx"):
            res.error = ROBOTS_ERROR
            return res, [], [], []
        try:
            refs = find_committees(client, max_age_days=7 if update else None, start=start)
        except Refused as e:
            res.error = ROBOTS_ERROR if ROBOTS_ERROR in str(e) else str(e)
            return res, [], [], []
        except CmisError as e:
            res.error = str(e)
            return res, [], [], []
        chosen = {}
        for c in refs:
            k = committee_kinds.kind(c.title, council.gss)
            if k:
                chosen[c.id] = (c, k)
        res.committees = {cid: (c.title, k) for cid, (c, k) in chosen.items()}
        try:
            for cid, (c, kind) in sorted(chosen.items()):
                listed = None
                for attempt in (1, 2):
                    try:
                        listed = list_meetings(client, c, start, end)
                        break
                    except Refused:
                        raise
                    except CmisError as e:
                        log.warning("%s committee %s (attempt %d): %s", council.gss, cid, attempt, e)
                        error = e
                        time.sleep(5 * attempt)
                if listed is None:
                    # Not a council with one committee missing (Sunderland's council meetings were lost so,
                    # November 2026): nothing is stored, so the next load or update tries again.
                    res.error = f"committee {c.title}: {error}"
                    return res, [], [], []
                for ref in listed:
                    try:
                        text, extra, _ = fetch_meeting(client, ref)
                        m, its, att = meeting_rows(council.gss, council.name, c, kind, ref, text, extra)
                    except Refused:
                        raise
                    except (CmisError, ValueError) as e:
                        log.warning("%s meeting %s: %s", council.gss, ref.id, e)
                        res.failed.append(ref.id)
                        continue
                    meetings.append(m)
                    items += its
                    attendance += att
            if settings.modgov.get("read_documents", True):
                items += _read_minutes(client, meetings, items, attendance, res)
            _parties(client, attendance, update)
        except Refused as e:
            res.error = ROBOTS_ERROR if ROBOTS_ERROR in str(e) else str(e)
            return res, [], [], []
    for m in meetings:
        m.pop("_documents", None)
    for a in attendance:
        a.pop("_person_url", None)
    # Members of the public and council staff aren't stored (docs/DECISIONS.md, 9).
    attendance = [a for a in attendance if extract.is_councillor(a["role"])]
    res.meetings = len(meetings)
    log.info("%s: %d meetings, %d requests", council.gss, len(meetings), client.requests)
    return res, meetings, items, attendance


def _read_minutes(client: Client, meetings: list[dict], items: list[dict], attendance: list[dict], res) -> list[dict]:
    """Minutes from documents, for meetings whose items have none: the document on the meeting's own page, else the
    one at the next meetings of the committee that approve them (documents.choose)."""
    by_meeting: dict[str, list[dict]] = {}
    for it in items:
        by_meeting.setdefault(it["meeting_id"], []).append(it)
    att_by_meeting: dict[str, list[dict]] = {}
    for a in attendance:
        att_by_meeting.setdefault(a["meeting_id"], []).append(a)
    by_committee: dict[int, list[dict]] = {}
    for m in meetings:
        by_committee.setdefault(m["committee_id"], []).append(m)
    extra: list[dict] = []
    forbidden = False
    used: set[str] = set()     # two meetings on one day (extraordinary meetings) mustn't take the same minutes
    for ms in by_committee.values():
        ms.sort(key=lambda m: (m["date"], int(m["meeting_id"].rsplit(":", 1)[1])))
        for n, m in enumerate(ms):
            if m["items_with_minutes"] or forbidden:
                continue
            # the next meetings' minutes documents, not yet taken; beyond the very next meeting only dated ones,
            # looking past meetings with none (extraordinary meetings approve no minutes)
            later = []
            for k, x in enumerate(ms[n + 1:n + 8]):
                docs = [d for d in json.loads(x["earlier_minutes"] or "[]") if d["url"] not in used
                        and (k == 0 or title_dates(d["title"], x["date"]))]
                if k == 0 or docs:
                    later.append({"date": x["date"], "docs": docs})
            doc = own_minutes([d for d in m.get("_documents", []) if d["url"] not in used], m["date"]) or \
                choose(m["date"], later)
            if not doc:
                continue
            if not client.allowed(doc["url"]):
                forbidden = True              # robots.txt forbids the site's documents
                res.documents_refused = True
                log.info("%s: robots.txt forbids documents", client.council)
                continue
            try:
                data = client.document(doc["url"])
            except Refused:
                res.documents_refused = True
                forbidden = True
                continue
            except CmisError as e:
                log.warning("%s document: %s", m["meeting_id"], e)
                continue
            if not data:
                continue
            text = pdf_text(data)
            if len(text.strip()) < 200:
                continue
            res.documents_read += 1
            used.add(doc["url"])
            got = apply_minutes(m, by_meeting.get(m["meeting_id"], []), att_by_meeting.setdefault(m["meeting_id"], []),
                                text, doc["url"])
            extra += got
            if not any(a["meeting_id"] == m["meeting_id"] for a in attendance):
                attendance += att_by_meeting[m["meeting_id"]]    # read from the minutes' "Present:" list
    return extra


def _parties(client: Client, attendance: list[dict], update: bool) -> None:
    """Party and ward on the date, from each councillor's page. Left blank where the page's history doesn't cover the
    date."""
    histories: dict[str, tuple[list, list]] = {}
    for a in attendance:
        url = a.get("_person_url")
        if not url:
            continue
        pid = a["member_id"]
        if pid not in histories:
            try:
                text, _ = client.page(f"person/{pid}", url, max_age_days=30 if update else None)
            except Refused:
                raise
            except CmisError as e:
                log.warning("%s person %s: %s", client.council, pid, e)
                histories[pid] = ([], [])
                continue
            histories[pid] = (party_history(text, "grdRadPartyHistory"), party_history(text, "grdRadWardHistory"))
        party, ward = histories[pid]
        a["party_label"] = on_date(party, a["date"])
        a["ward"] = on_date(ward, a["date"])
