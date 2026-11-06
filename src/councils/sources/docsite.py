"""Reader for strategic authorities that publish their meetings as documents on their own websites, not through a
meetings system (docs/DATA.md, "Meetings: authorities' own websites"): Tees Valley, Hull and East Yorkshire,
Cumbria, and Hampshire and the Solent (November 2026).

Each authority's committees in scope, and the pages that list their meetings, are in
``data_static/document_sites.csv``. Two layouts are read:

* **sections**: one or more pages listing the committee's meetings under dated headings ("31st July 2026",
  "28 September 2026 @ 2.30pm"), each followed by links to its documents (Tees Valley's WordPress pages, Hampshire
  and the Solent's). A meeting is a date at the start of a heading or a short paragraph; the document links after it,
  up to the next date, are its own.
* **listing**: a list of meetings, each linking to a page of its own ("Cumbria Combined Authority Board: 17 July
  2026", "2025.09.26 - Executive Board"), with its documents. The list's further pages ("?page=1") and council years
  ("2025/26") are followed (Cumbria's LocalGov Drupal directory, Hull and East Yorkshire's Jadu directory). A meeting
  link is one whose text names the committee and a date.

A meeting's minutes are the document titled as minutes that carries its date, in its title or its file name
("Cabinet-minutes-25-July-2025.pdf", "Minutes-280619.pdf", "260928_Board-Minutes-Final.pdf"), from its own documents
or, failing that, from a later meeting's ("Draft Minutes 27 June 2024" on the next agenda). Approved or final minutes
are preferred to drafts, and a link whose file carries another meeting's date is never taken (Tees Valley's page links
one meeting's minutes from another's). Minutes of an annual meeting held the same day as an ordinary one (Tees Valley's
AGM) are read with them. The text is kept whole as one "Minutes" item: these minutes number their items in ways that
don't survive the PDF's columns, and there is no agenda to split them by.

Attendance is the minutes' list of who was present ("Present:", "ATTENDEES / Members"), its sections ("Associate
Members", "Apologies", "In attendance", "Officers") and the roles and councils written beside names. A councillor
named without their council ("Councillors Handley, Ross", "Cllr M Fryer") is matched to the authority's member
councils' records (authority.find_member). Members are then classed by ``authority.classify`` (decision 20):
councillors and the mayor are named; anyone else who is a member (business board chairs, a police and crime
commissioner) is counted but not named; officers aren't stored.

Every response is cached, gzipped, under ``raw/docsite/<authority>/``. Requests to a site are one at a time, at least
``min_interval_seconds`` apart (longer if robots.txt asks, with Crawl-delay), with the crawler's own user agent. A
refusal (401, 403, 429, a bot check) stops the authority's load: it is asked, never worked around (decision 21).
"""

from __future__ import annotations

import contextlib
import csv
import gzip
import hashlib
import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import date
from functools import lru_cache
from pathlib import Path
from urllib.parse import unquote, urljoin, urlparse

import httpx
from lxml import html as lhtml

from councils import authority
from councils import committees as committee_kinds
from councils.config import STATIC_DIR, Settings
from councils.registry import Council, councils, mayor_on
from councils.sources import cmis, documents, robots

log = logging.getLogger(__name__)

_REFUSAL = re.compile(r"has been blocked|request rejected|connection denied by geolocation|_Incapsula_Resource|"
                      r"<title>\s*(?:access denied|just a moment|attention required)|cf-chl-|captcha", re.I)


class SiteError(RuntimeError):
    pass


class Refused(SiteError):
    """The site refused the request (401, 403, 429 or a bot check). Not retried, and never worked around."""


# Configuration --------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Committee:
    gss: str
    id: int                 # its position among the authority's committees in the file, from 1
    title: str
    layout: str             # "sections" or "listing"
    pages: tuple[str, ...]


@lru_cache(maxsize=1)
def sites() -> dict[str, list[Committee]]:
    """The committees read from each authority's own website, by authority (data_static/document_sites.csv)."""
    out: dict[str, list[Committee]] = {}
    with open(STATIC_DIR / "document_sites.csv", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            own = out.setdefault(r["gss"], [])
            own.append(Committee(r["gss"], len(own) + 1, r["committee_title"], r["layout"],
                                 tuple(r["pages"].split())))
    return out


# Dates ----------------------------------------------------------------------------------------------------------

_MONTH = r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|sept?(?:ember)?|oct(?:ober)?" \
         r"|nov(?:ember)?|dec(?:ember)?)"
_WEEKDAY = r"(?:(?:mon|tues|wednes|thurs|fri|satur|sun)day,?\s+)?"
_DAY_MONTH_YEAR = re.compile(rf"(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?,?\s+(\d{{4}})", re.I)
_LEADING_DATE = re.compile(rf"^\s*{_WEEKDAY}(\d{{1,2}})(?:st|nd|rd|th)?\s+({_MONTH})\.?,?\s+(\d{{4}})\b", re.I)
_ISO_DOTTED = re.compile(r"\b(20\d\d)[.\-/](\d{1,2})[.\-/](\d{1,2})\b")


def _month(word: str) -> int:
    w = word.lower().rstrip(".")
    return documents.MONTHS.get(w) or documents.MONTHS[w[:3]]


def leading_date(text: str) -> date | None:
    """A date at the start of a heading: "31st July 2026", "28 September 2026 @ 2.30pm", "Friday 28th June 2019"."""
    m = _LEADING_DATE.match(text)
    if not m:
        return None
    with contextlib.suppress(ValueError, KeyError):
        return date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))
    return None


def text_date(text: str) -> date | None:
    """The first date written in a link's text: "Cumbria Combined Authority Board: 17 July 2026",
    "2025.09.26 - Executive Board"."""
    found = []
    for m in _DAY_MONTH_YEAR.finditer(text):
        with contextlib.suppress(ValueError, KeyError):
            found.append((m.start(), date(int(m.group(3)), _month(m.group(2)), int(m.group(1)))))
    for m in _ISO_DOTTED.finditer(text):
        with contextlib.suppress(ValueError):
            found.append((m.start(), date(int(m.group(1)), int(m.group(2)), int(m.group(3)))))
    return min(found)[1] if found else None


def document_dates(label: str, url: str) -> set[date]:
    """Dates in a document's link text and file name, in the forms these sites use: "25th Sept 2026",
    "18.06.25", "280619" (day, month, year), "260928_Board-Minutes" (year, month, day: Hampshire and the Solent's)."""
    name = unquote(urlparse(url).path.rsplit("/", 1)[-1])
    name = re.sub(r"\.(?:pdf|docx?)$", "", name, flags=re.I)
    out: set[date] = set()
    for t in (label, name):
        t = re.sub(r"[-_]+", " ", t)
        out |= documents.dates_in(t)
        for run in re.findall(r"(?<!\d)(\d{6})(?!\d)", t):      # also year, month, day
            with contextlib.suppress(ValueError):
                out.add(date(2000 + int(run[:2]), int(run[2:4]), int(run[4:])))
        for m in _ISO_DOTTED.finditer(t.replace(" ", ".")):
            with contextlib.suppress(ValueError):
                out.add(date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
    return out


# Pages ----------------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Document:
    label: str
    url: str


@dataclass
class Meeting:
    date: date
    url: str                                   # the page it is listed on, or its own page
    documents: list[Document] = field(default_factory=list)


def _doc(text: str):
    return lhtml.fromstring(text or "<html></html>")


def _content(doc):
    """The page's own content: its <main>, without navigation, headers, footers and scripts."""
    for bad in doc.xpath("//script|//style|//noscript|//nav|//header|//footer"):
        bad.drop_tree()
    main = doc.xpath("//main") or doc.xpath('//*[@id="main" or @id="content" or @role="main"]')
    return main[0] if main else (doc.body if doc.body is not None else doc)


def _clean(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").replace("\xa0", " ")).strip()


_DOCUMENT = re.compile(r"\.(?:pdf|docx?)(?:$|\?)|/downloads/file/|/download/", re.I)


def is_document(href: str) -> bool:
    return bool(_DOCUMENT.search(urlparse(href).path + ("?" if urlparse(href).query else "")))


def _label(a) -> str:
    """A link's text without its size ("(PDF, 1.14MB)", "(3.03mb)")."""
    return re.sub(r"\(\s*(?:pdf|word|docx?)?,?\s*[\d.]+\s*[kmg]b\s*\)", "", _clean(a.text_content()), flags=re.I).strip()


def parse_sections(text: str, page_url: str) -> list[Meeting]:
    """Meetings under dated headings on a page, each with the document links that follow it."""
    root = _content(_doc(text))
    out: list[Meeting] = []
    current: Meeting | None = None
    for el in root.iter():
        if not isinstance(el.tag, str):
            continue
        if el.tag == "a":
            href = el.get("href") or ""
            if current is not None and href and is_document(href):
                url = urljoin(page_url, href)
                if all(d.url != url for d in current.documents):
                    current.documents.append(Document(_label(el), url))
            continue
        if el.tag not in ("h1", "h2", "h3", "h4", "h5", "h6", "p", "strong", "b", "dt", "summary", "button"):
            continue
        if el.xpath("ancestor::a"):
            continue
        words = _clean(el.text_content())
        d = leading_date(words)
        if d is None or (el.tag in ("p", "dt") and len(words) > 240):
            continue
        if current is None or current.date != d:
            current = next((m for m in out if m.date == d), None)
            if current is None:
                current = Meeting(d, page_url)
                out.append(current)
    return out


def _key(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", text.lower().replace("&", " and ")).split())


def parse_listing(text: str, page_url: str, committee: str) -> tuple[list[tuple[date, str]], list[str]]:
    """(meetings as (date, page), further pages of the list) on a page listing a committee's meetings: links whose
    text names the committee and a date; and the list's other pages ("?page=1") and council years ("2025/26")."""
    doc = _doc(text)
    here = urlparse(page_url)
    meetings, more = [], []
    for a in doc.iter("a"):            # the list's pager is often in a <nav>, so the whole page is read first
        url = urljoin(page_url, a.get("href") or "").split("#")[0]
        u = urlparse(url)
        if (u.netloc.lower() == here.netloc.lower() and u.path.rstrip("/") == here.path.rstrip("/")
                and re.search(r"(?:^|&)page=\d+(?:&|$)", u.query) and not re.search(r"(?:^|&)f(?:%5B|\[)", u.query)):
            more.append(url)
    for a in _content(doc).iter("a"):
        href = a.get("href") or ""
        if not href or href.startswith(("#", "mailto:")):
            continue
        url = urljoin(page_url, href)
        u = urlparse(url)
        if u.netloc.lower() != here.netloc.lower() or is_document(url):
            continue
        words = _clean(a.text_content())
        d = text_date(words)
        if d and _key(committee) in _key(words):
            meetings.append((d, url.split("#")[0]))
        elif re.fullmatch(r"(?:19|20)\d\d\s*/\s*\d\d", words):
            more.append(url.split("#")[0])
    return meetings, list(dict.fromkeys(more))


def parse_meeting_page(text: str, page_url: str) -> list[Document]:
    """The documents linked from a meeting's own page."""
    root = _content(_doc(text))
    out: list[Document] = []
    for a in root.iter("a"):
        href = a.get("href") or ""
        if href and is_document(href):
            url = urljoin(page_url, href)
            if all(d.url != url for d in out):
                out.append(Document(_label(a), url))
    return out


# Minutes --------------------------------------------------------------------------------------------------------

_MINUTES = re.compile(r"minute", re.I)              # also "DraftMinutesFinal"
_NOT_MINUTES = re.compile(r"\bextract\b|\bappendi|\baction|decision record|\bagenda\b|\bpapers?\b|\bpack\b"
                          r"|development corporation|\bstdc\b|\bmdc\b|\bhdc\b", re.I)
_FINAL = re.compile(r"\b(?:approved|confirmed|final|signed)\b", re.I)
_DRAFT = re.compile(r"\bdraft\b", re.I)
_ANNUAL = re.compile(r"\bagm\b|annual (?:general )?meeting", re.I)


def is_minutes(doc: Document) -> bool:
    name = unquote(urlparse(doc.url).path.rsplit("/", 1)[-1]).replace("-", " ").replace("_", " ")
    both = f"{doc.label} {name}"
    return bool(_MINUTES.search(both)) and not _NOT_MINUTES.search(both)


def _rank(doc: Document, own: bool) -> tuple[int, int]:
    name = unquote(urlparse(doc.url).path.rsplit("/", 1)[-1]).replace("-", " ").replace("_", " ")
    final = bool(_FINAL.search(name) or _FINAL.search(doc.label))
    # a file called "...Final" is final whatever its link says ("Draft HSCCA Board Minutes" -> "...Minutes-Final.pdf")
    draft = bool(_DRAFT.search(name) and not _FINAL.search(name)) or (bool(_DRAFT.search(doc.label)) and not final)
    return (0 if final else 1 if not draft else 2, 0 if own else 1)


def choose_minutes(meeting: Meeting, later: list[Meeting]) -> list[Document]:
    """The meeting's minutes: documents titled as minutes carrying its date, its own first, then those on the
    committee's next three meetings; approved or final ones before drafts. An annual meeting's minutes held the same
    day are kept with the ordinary meeting's (two documents). An undated minutes document is taken only where it is
    the meeting's only one and no date is written on it at all."""
    found: list[tuple[tuple[int, int], Document]] = []
    for n, m in enumerate([meeting] + later[:3]):
        for doc in m.documents:
            if not is_minutes(doc):
                continue
            dates = document_dates(doc.label, doc.url)
            if meeting.date in dates:
                found.append((_rank(doc, n == 0), doc))
            elif n == 0 and not dates and sum(1 for d in meeting.documents if is_minutes(d)) == 1:
                found.append(((3, 0), doc))
    if not found:
        return []
    out: list[Document] = []
    for kind in (True, False):                 # the annual meeting's minutes first, then the ordinary meeting's
        same = sorted((r, d) for r, d in found if bool(_ANNUAL.search(f"{d.label} {d.url}")) == kind)
        if same:
            out.append(same[0][1])
    return out


# Attendance -----------------------------------------------------------------------------------------------------

@dataclass(frozen=True)
class Attendee:
    name: str           # "Councillor Ian Blades", "Mayor Ben Houchen", "Darren Hankey"
    role: str           # "Chair", "Vice Chair", "Substitute", "Associate member", "" (a member)
    attendance: str     # "Present", "Apologies", "In attendance"
    representing: str   # the body written beside the name: "Middlesbrough Council", "HEY Skills Board Chair"


_START = re.compile(r"^\s*(?:present|attendees|attendance|members present)\s*(?::-|:|–|-)?\s*(.*)$", re.I)
_SECTION = re.compile(
    r"^\s*(?P<h>members(?:\s+present)?|present|(?:associate|advisory|non[- ]constituent|co-?opted|independent|"
    r"substitute|voting|non[- ]voting)\s+members?|substitutes?|apolog(?:y|ies)(?:\s+for\s+absence)?(?:\s+received)?"
    r"|absent|also\s+(?:present|in\s+attendance|attending)|in\s+attendance|officers?(?:\s+(?:and\s+others\s+)?"
    r"(?:in\s+attendance|present))?|officials|observers?)\s*(?::-|:|–|-)?\s*(?P<rest>.*)$", re.I)
# a line that ends the list: the first item of business, or the note under it
_END = re.compile(r"^\s*(?:\d{1,3}\s*\.?\s*$|\d{1,3}\.?\s+(?-i:[A-Z])|(?:TVCA|OSC|HEY|CCA|HSCCA)\s*\d|[A-Z]{2,6}\s*$"
                  r"|minute\s+no|these minutes|chair'?s opening|apologies for absence\s*$|declarations? of interest"
                  r"|welcome|the (?:chair|mayor|meeting|board|committee)\b|description/decision)", re.I)
_ROLE_LINE = re.compile(r"\b(?:leader|council\b|mayor of|deputy mayor|mayor\s*$|member of|chair (?:of|,)|chair$|vice[- ]chair of"
                        r"|director|officer|executive|manager|head of|governance|authority|lep\b|board|committee"
                        r"|commissioner|secretary|solicitor|clerk|advis[eo]r|lead\b|partnership|university|college)",
                        re.I)
_OFFICER_ROLE = re.compile(r"\bofficer\b|chief executive|director|manager|head of|clerk|solicitor|secretary"
                           r"|returning|governance|section 73|\bhr\b", re.I)
_TITLE = re.compile(r"^(?:the\s+)?(?:(?:deputy|elected|city)\s+)?(?:councill?ors?|cllrs?\.?|mayor(?!\s+of\b))\s+", re.I)
_PLURAL = re.compile(r"^(?:councill?ors|cllrs)\.?\s+", re.I)
_NOT_NAME = {"none", "nil", "no", "apologies", "members", "officers", "present", "the", "and", "all", "of", "for",
             "were", "was", "received", "absence", "attendance", "minutes", "meeting", "chair", "vice", "noted"}


def _split(block: str) -> list[tuple[str, bool]]:
    """A list in sentences into (token, ends a "Councillors ..." run): split at commas, semicolons, "and" and full
    stops, outside brackets. A token after "and", or before a full stop, ends a run of names under "Councillors"."""
    tokens: list[tuple[str, bool]] = []
    depth, cur = 0, ""
    flat = re.sub(r"\s*\n\s*", " ", block)
    i = 0
    after_and = False
    while i < len(flat):
        ch = flat[i]
        depth += ch == "("
        depth -= ch == ")"
        if depth <= 0:
            m = re.match(r"\s+(?:and|&)\s+", flat[i:])
            if m and not _TITLE.match(cur.strip()) and _is_body(re.split(r"[,;]|\.\s", flat[i + m.end():])[0]):
                m = None           # "Redcar and Cleveland Borough Council": one body, not two names
            if ch in ",;" or (ch == "." and (i + 1 == len(flat) or flat[i + 1] == " ")
                              and not re.search(r"(?:^|\s)[A-Z]$", cur)) or m:
                if cur.strip(" ,;."):
                    tokens.append((cur.strip(" ,;."), after_and or ch == "."))
                after_and = bool(m)
                cur = ""
                i += m.end() if m else 1
                continue
        cur += ch
        i += 1
    if cur.strip(" ,;."):
        tokens.append((cur.strip(" ,;."), True))
    return tokens


# words of a body or an office, never of a person's name: "Darlington Borough Council", "Tees Valley Mayor"
_BODY = re.compile(r"\b(?:council|councils|authority|combined|borough|county|district|board|committee|partnership"
                   r"|commissioner|lep|mayor|university|college|chamber|police|limited|ltd|plc|nhs|trust|group"
                   r"|enterprise|leader|chair|officer|director|executive|manager|head|member|representative)\b", re.I)


def _is_body(text: str) -> bool:
    return bool(_BODY.search(_TITLE.sub("", re.sub(r"\([^)]*\)", " ", text)).strip()))


def _looks_like_name(name: str, titled: bool) -> bool:
    words = name.replace("’", "'").split()
    if not words or len(words) > 5 or re.search(r"\d", name) or (len(words) == 1 and not titled):
        return False
    if _BODY.search(name):
        return False
    if any(w.lower().strip(".,") in _NOT_NAME for w in words):
        return False
    return all(re.match(r"^[A-Z][\w'’.-]*$", w) or w.lower() in {"de", "van", "von", "der", "le", "la", "du", "di"}
               for w in words)


def _person(token: str, attendance: str, section_role: str, titled_run: bool) -> Attendee | None:
    """One name in the list, with what is written beside it: "Councillor Ian Blades (Middlesbrough Council) (Chair)",
    "Tock (substituting for Councillor Dad)", "J. Evison (Humberside Police and Crime Commissioner)"."""
    token = token.replace("’", "'").strip(" .:-–")
    role, representing = section_role, ""
    sub = re.search(r"\s+(?:as\s+(?:a\s+)?substitute\s+for|substituting\s+for|on\s+behalf\s+of)\b.*$", token, re.I)
    if sub:
        role, token = "Substitute", token[:sub.start()]
    for p in re.findall(r"\(([^)]*)\)", token):
        if re.search(r"substitut", p, re.I):
            role = "Substitute"
        elif re.fullmatch(r"\s*(?:the\s+)?(?:chair(?:man|woman|person)?|in the chair)\s*", p, re.I):
            role = "Chair"
        elif re.fullmatch(r"\s*vice[-\s]+chair(?:man|woman|person)?\s*", p, re.I):
            role = "Vice Chair"
        elif re.search(r"[A-Za-z]{3}", p) and not re.search(r"\bminute", p, re.I):
            representing = representing or p.strip()
    name = _clean(re.sub(r"\([^)]*\)?", " ", token))
    name = re.sub(r"\s+in\s+the\s+chair$", "", name, flags=re.I)
    titled = bool(_TITLE.match(name)) or titled_run
    if _TITLE.match(name):
        title = "Mayor" if re.match(r"^(?:the\s+)?(?:elected\s+)?mayor\b", name, re.I) else "Councillor"
        rest = _TITLE.sub("", name).strip()
    else:
        title, rest = ("Councillor" if titled_run else ""), name
    if not _looks_like_name(rest, titled):
        return None
    return Attendee(f"{title} {rest}".strip(), role, attendance, representing)


def _section(header: str) -> tuple[str, str] | None:
    """(attendance, role) for a section of the list, or None for officers, whose names aren't kept."""
    h = re.sub(r"\s+", " ", header.lower())
    if re.match(r"apolog|absent", h):
        return "Apologies", ""
    if re.match(r"officer|official|observer", h) or "in attendance" in h or h.startswith("also"):
        return "In attendance", ""
    if re.match(r"substitute", h):
        return "Present", "Substitute"
    m = re.match(r"(associate|advisory|non[- ]constituent|co-?opted|independent|non[- ]voting)", h)
    if m:
        return "Present", {"co-opted": "Co-opted member", "coopted": "Co-opted member"}.get(
            m.group(1).replace(" ", "-"), f"{m.group(1).capitalize()} member")
    return "Present", ""


def _is_role_line(line: str, block: list[str]) -> bool:
    """A line of the column of roles printed beside the names ("Leader, Hartlepool Borough Council", "Tees Valley
    Mayor", "Member of Tees Valley LEP"), not a name or the rest of a sentence the line before began."""
    if _TITLE.match(line) or re.search(r"[()]", line):
        return False
    if block and (block[-1].rstrip().endswith((",", "(", "and", "&")) or block[-1].count("(") > block[-1].count(")")
                  or ("," in "".join(block) and not block[-1].rstrip().endswith("."))):
        return False                          # the rest of a sentence the lines before began
    if re.match(r"^(?:and|&)\s", line):
        return False
    if "," in line and not re.match(r"^(?:deputy\s+)?(?:leader|chair|vice[- ]chair|member|chief|director|head)\b", line,
                                    re.I):
        return False
    return bool(_ROLE_LINE.search(line))


def _sentences(body: str) -> bool:
    """A block written as a sentence ("Councillors Adams-King (Chair), Bacon, ... and Pitt.") rather than a name a
    line: commas, semicolons or "and" outside brackets."""
    return bool(re.search(r"[,;]|\s(?:and|&)\s", re.sub(r"\([^)]*\)", " ", body)))


def attendees(text: str) -> list[Attendee]:
    """Who attended, from the list at the top of a meeting's minutes. Members, associate and other members, and
    apologies are kept; under "In attendance" or "Officers", only councillors (those written as councillors), so
    officers and guests aren't stored. A column of roles printed beside the members' names ("Leader, Hartlepool
    Borough Council"), which comes out of the PDF after the names, is matched to them in order where it has at least
    as many lines as there are members."""
    lines = [ln.strip() for ln in text[:9000].replace("\r", "").split("\n")]
    start = next((n for n, ln in enumerate(lines) if _START.match(ln)), None)
    if start is None:
        return []
    out: list[Attendee] = []
    roles: list[str] = []
    attendance, section_role = "Present", ""
    block: list[str] = []

    def flush() -> None:
        if not block:
            return
        body = "\n".join(block)
        block.clear()
        tokens = _split(body) if _sentences(body) else [(ln, True) for ln in body.split("\n")]
        run = False
        added: list[Attendee] = []
        for tok, ends in tokens:
            if _PLURAL.match(tok):
                run, tok = True, _PLURAL.sub("", tok)
            elif _TITLE.match(tok) or re.match(r"^[A-Z]\.\s", tok):
                run = False
            if _is_body(tok):
                # the body or office written after a name: "Councillor Ian Haszeldine, (Chair) Darlington Borough
                # Council", "Mayor Ben Houchen, Tees Valley Mayor"
                if added and not added[-1].representing:
                    prev = added[-1]
                    role = next((r for r in ("Vice Chair", "Chair") if re.search(rf"\({r.replace(' ', '[- ]')}\)", tok,
                                                                                  re.I)), prev.role)
                    body_text = _clean(re.sub(r"\([^)]*\)", " ", tok))
                    added[-1] = Attendee(prev.name, role, prev.attendance, body_text)
                    if out and out[-1] is prev:
                        out[-1] = added[-1]
                if run and ends:
                    run = False
                continue
            p = _person(tok, attendance, section_role, run)
            if run and ends:
                run = False
            if p is None:
                continue
            added.append(p)
            if attendance == "In attendance" and not p.name.startswith(("Councillor ", "Mayor ")):
                continue           # officers and guests aren't stored (decision 9)
            out.append(p)

    first = _START.match(lines[start])
    todo = ([first.group(1)] if first and first.group(1) else []) + lines[start + 1:]
    read, stop = 0, len(todo)
    for n, line in enumerate(todo):
        read += len(line) + 1
        if read > 6000:
            stop = n
            break
        if not line:
            flush()
            continue
        sec = _SECTION.match(line)
        if sec and (sec.group("rest") == "" or re.match(r"^[^:]{0,60}(?::-|:|–)", line)):
            flush()
            attendance, section_role = _section(sec.group("h"))
            if sec.group("rest"):
                block.append(sec.group("rest"))
            continue
        if _END.match(line) and not (block and block[-1].count("(") > block[-1].count(")")):
            stop = n
            break
        if re.search(r"\d", line):
            continue                           # page numbers, times, addresses
        if _is_role_line(line, block):
            flush()
            roles.append(_clean(line))
            continue
        block.append(line)
    flush()
    if not roles:                              # the column of roles may come after the list ("TVCA 01/22", then roles)
        for line in todo[stop:stop + 60]:
            if not line or re.search(r"\d", line) or _END.match(line):
                if roles and line and not re.search(r"\d", line):
                    break
                continue
            if _is_role_line(line, []):
                roles.append(_clean(line))
            elif roles:
                break
    seen, unique = set(), []
    for a in out:                              # one person listed twice: keep the first
        k = a.name.lower()
        if k not in seen:
            seen.add(k)
            unique.append(a)
    members = [a for a in unique if a.attendance == "Present"]
    # only a column of members' roles: officers' roles under "In attendance" (Cumbria's) aren't the members'
    if members and len(roles) >= len(members) and not any(a.representing for a in members) \
            and not any(_OFFICER_ROLE.search(r) for r in roles[:len(members)]):
        unique = [Attendee(a.name, a.role, a.attendance, roles[members.index(a)]) if a in members else a
                  for a in unique]
    return unique


def representing_council(text: str) -> str:
    """The council in a role written beside a name: "Leader, Hartlepool Borough Council" -> "Hartlepool Borough
    Council"; "Mayor of Middlesbrough" -> "Middlesbrough"."""
    t = re.sub(r"^(?:deputy\s+)?(?:leader|mayor|elected mayor|cabinet member|portfolio holder)\b,?\s*(?:of\s+)?", "",
               text.strip(), flags=re.I)
    return t.strip(" ,")


# Transport ------------------------------------------------------------------------------------------------------

class Client:
    """One authority's website: polite, cached requests."""

    _locks: dict[str, threading.Lock] = {}

    def __init__(self, settings: Settings, gss: str):
        cfg = settings.modgov
        self.authority = gss
        self.cache = settings.raw_dir / "docsite" / gss
        self.store = settings.parquet_dir      # the member councils' records (authority.find_member)
        self.user_agent = cfg.get("user_agent", "WhereCouncilsStand")
        self.interval = float(cfg.get("min_interval_seconds", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self.refetch_days = int(cfg.get("refetch_days", 120))
        self.http = httpx.Client(headers={"User-Agent": self.user_agent},
                                 timeout=float(cfg.get("timeout_seconds", 40)), follow_redirects=True)
        self._last = 0.0
        self._lock = self._locks.setdefault(gss, threading.Lock())
        self.requests = 0

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def _get(self, url: str) -> httpx.Response:
        if not robots.allowed(url, self.user_agent):
            raise Refused(f"robots.txt forbids crawling: {url}")
        interval = max(self.interval, robots.crawl_delay(url, self.user_agent))
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries):
                wait = interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = self.http.get(url)
                    self._last = time.monotonic()
                    self.requests += 1
                    if r.status_code in (401, 403, 429) or (
                            r.status_code == 200 and not r.content.startswith(b"%PDF")
                            and "html" in r.headers.get("content-type", "") and _REFUSAL.search(r.text[:5000])):
                        raise Refused(f"{self.authority}: the site refused the request (HTTP {r.status_code}): {url}")
                    if r.status_code == 200:
                        return r
                    last_error = SiteError(f"{self.authority}: HTTP {r.status_code}: {url}")
                    if r.status_code in (400, 404, 410):
                        break
                except httpx.HTTPError as e:
                    self._last = time.monotonic()
                    last_error = SiteError(f"{self.authority}: {type(e).__name__}: {url}")
                    last_error.__cause__ = e
                time.sleep(2 * (attempt + 1))
            raise last_error or SiteError(url)

    def _path(self, kind: str, url: str, suffix: str) -> Path:
        return self.cache / kind / f"{hashlib.sha1(url.encode()).hexdigest()[:20]}{suffix}.gz"

    def page(self, url: str, max_age_days: float | None = None) -> str:
        """A page, from the cache unless it isn't cached or is older than ``max_age_days``. If fetching again fails,
        the cached copy is used: a server that is down mustn't lose what is already known."""
        path = self._path("pages", url, ".html")
        fresh = path.exists() and (max_age_days is None or time.time() - path.stat().st_mtime <= max_age_days * 86_400)
        if fresh:
            return gzip.decompress(path.read_bytes()).decode("utf-8")
        try:
            r = self._get(url)
        except SiteError as e:
            if path.exists() and not isinstance(e, Refused):
                log.warning("%s; using the cached copy", e)
                return gzip.decompress(path.read_bytes()).decode("utf-8")
            raise
        _write(path, gzip.compress(r.text.encode("utf-8")))
        return r.text

    def document(self, url: str) -> bytes | None:
        """A document, cached by its address (a new version of a document is published at a new address); None if it
        isn't a PDF."""
        path = self._path("documents", url, ".pdf")
        if path.exists():
            return gzip.decompress(path.read_bytes())
        r = self._get(url)
        if not r.content.startswith(b"%PDF"):
            return None
        _write(path, gzip.compress(r.content))
        return r.content


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


# Reading an authority -------------------------------------------------------------------------------------------

def list_meetings(client: Client, committee: Committee, start: date, end: date) -> list[Meeting]:
    """The committee's meetings from its pages, with their documents, oldest first. Lists are fetched again if over
    a day old, and a meeting's own page if it is also within ``refetch_days`` (minutes are added after the meeting,
    and drafts replaced by approved minutes)."""
    age = 0.9
    found: dict[date, Meeting] = {}
    if committee.layout == "sections":
        for url in committee.pages:
            for m in parse_sections(client.page(url, max_age_days=age), url):
                had = found.setdefault(m.date, m)
                if had is not m:
                    had.documents += [d for d in m.documents if all(d.url != x.url for x in had.documents)]
    elif committee.layout == "listing":
        todo, seen = list(committee.pages), set()
        refs: dict[str, date] = {}
        while todo and len(seen) < 60:
            url = todo.pop(0)
            if url in seen:
                continue
            seen.add(url)
            got, more = parse_listing(client.page(url, max_age_days=age), url, committee.title)
            for d, link in got:
                refs.setdefault(link, d)
            todo += [u for u in more if u not in seen]
        for link, d in sorted(refs.items(), key=lambda x: x[1]):
            if d < start or d > end:
                continue
            recent = (date.today() - d).days < client.refetch_days
            text = client.page(link, max_age_days=age if recent else None)
            m = found.setdefault(d, Meeting(d, link))
            m.documents += [x for x in parse_meeting_page(text, link) if all(x.url != y.url for y in m.documents)]
    else:
        raise SiteError(f"unknown layout {committee.layout!r}")
    return sorted(found.values(), key=lambda m: m.date)


def fetch(settings: Settings, council: Council, start: date, end: date, update: bool = False):
    """``(Result, meetings, items, attendance)``, rows as the Modern.gov path makes them (sources/meeting.py). The
    attendance isn't classified yet: ingest does that, as for an authority on Modern.gov (authority.classify)."""
    from councils.ingest import Result

    res = Result(council.gss)
    committees = sites().get(council.gss)
    if not committees:
        res.error = "no website pages listed in data_static/document_sites.csv"
        return res, [], [], []
    start = max(start, _created(council) or start)
    meetings: list[dict] = []
    items: list[dict] = []
    attendance: list[dict] = []
    with Client(settings, council.gss) as client:
        for c in committees:
            kind = committee_kinds.kind(c.title, council.gss)
            if not kind:
                continue
            res.committees[c.id] = (c.title, kind)
            try:
                listed = list_meetings(client, c, start, end)
            except Refused as e:
                res.error = f"refused: {e}"
                return res, [], [], []
            except SiteError as e:
                # not an authority with a committee missing: nothing is stored, so the next load tries again
                res.error = f"committee {c.title}: {e}"
                return res, [], [], []
            listed = [m for m in listed if m.date <= date.today()]
            for n, m in enumerate(listed):
                if m.date < start or m.date > end:
                    continue
                try:
                    row, its, att = _meeting(client, council, c, kind, m, listed[n + 1:], res)
                except Refused as e:
                    res.error = f"refused: {e}"
                    return res, [], [], []
                meetings.append(row)
                items += its
                attendance += att
    res.meetings = len(meetings)
    return res, meetings, items, attendance


def _created(council: Council) -> date | None:
    """The day the authority was created, where the registry gives a whole date ("24 February 2026")."""
    m = _LEADING_DATE.match(council.created or "")
    return leading_date(council.created) if m else None


def _meeting(client: Client, council: Council, committee: Committee, kind: str, m: Meeting, later: list[Meeting],
             res) -> tuple[dict, list[dict], list[dict]]:
    gss = council.gss
    key = f"{gss}:{committee.id}-{m.date:%Y%m%d}"
    texts, used = [], []
    for doc in choose_minutes(m, later):
        try:
            data = client.document(doc.url)
        except Refused:
            raise
        except SiteError as e:
            log.warning("%s minutes: %s", key, e)
            res.failed.append(key)
            continue
        text = cmis.pdf_text(data) if data else ""
        if len(text.strip()) < 200:
            continue                           # a scanned document, or no text: not read (there is no OCR)
        res.documents_read += 1
        texts.append(text)
        used.append(doc.url)
    text = "\n\n".join(t.strip() for t in texts)
    items = []
    if text:
        items.append({"item_id": f"{key}:minutes", "meeting_id": key, "gss": gss, "date": m.date,
                      "year": m.date.year, "position": 0, "number": "", "title": "Minutes", "agenda_text": "",
                      "minutes_text": text, "minutes_source": "document", "vote_tables": "", "is_decision": False,
                      "is_restricted": False, "is_call_in": False, "declaration_count": 0, "documents": len(used),
                      "url": used[0]})
    attendance = []
    mayor = mayor_on(gss, m.date)
    for a in _attending(texts):
        name, representing, member_id = a.name, a.representing, ""
        is_mayor = mayor is not None and _surname(name) == _surname(mayor.name)
        if not is_mayor and name.startswith(("Councillor ", "Mayor ")):
            found = authority.find_member(client.store, gss, name, m.date)
            if found:
                home, mid, full = found
                representing = representing or councils()[home].name
                name = f"{'Mayor' if name.startswith('Mayor ') else 'Councillor'} {full}"
                member_id = f"{home}:{mid}"
            elif representing:
                representing = representing_council(representing)
        attendance.append({
            "meeting_id": key, "gss": gss, "date": m.date, "year": m.date.year,
            "member_id": member_id or cmis.slug(re.sub(r"^(?:Mayor|Councillor)\s+", "", name)), "member_type": "",
            "name": name, "role": a.role, "attendance": a.attendance, "party_label": "", "ward": "",
            "representing": representing,
        })
    meeting = {
        "meeting_id": key, "gss": gss, "council": council.name, "committee_id": committee.id,
        "committee_title": committee.title, "kind": kind, "date": m.date, "year": m.date.year,
        "status": "", "location": "", "webcast": False, "minutes_published": bool(text), "items": len(items),
        "items_with_minutes": len(items), "earlier_minutes": "", "minutes_document": used[0] if used else "",
        "attendees": len(attendance), "url": m.url,
    }
    return meeting, items, attendance


def _attending(texts: list[str]) -> list[Attendee]:
    """The attendance of the first minutes document that has a list (an annual meeting's and an ordinary meeting's
    held the same day list the same members)."""
    for t in texts:
        if found := attendees(t):
            return found
    return []


def _surname(name: str) -> str:
    words = re.sub(r"^(?:mayor|councill?or|cllr)\.?\s+", "", name.strip(), flags=re.I).split()
    return words[-1].lower() if words else ""

