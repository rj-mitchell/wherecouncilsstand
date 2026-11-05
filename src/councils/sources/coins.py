"""Reader for Northgate's CoINS committee system (Glasgow, Falkirk, Shetland, West Lothian).

CoINS has no web service, so its public pages are read (docs/DATA.md, "CoINS"):

* ``allCommittees.asp?sort=1``: every committee, linking to ``committee.asp?bodyid=N&bodytitle=...``.
* ``allBodyMeetings.asp?bodyid=N&bodytitle=...&MeetingYear=YYYY``: a committee's meetings in a year, linking to
  ``Agenda.asp?meetingid=N``. The page is paged; ``page=0`` shows them all. The ``bodytitle`` must be the
  committee's own, or the list comes back empty.
* ``Agenda.asp?meetingid=N``: the agenda items ("Number / Item"), each item's papers
  (``submissiondocuments.asp?submissionid=N``), and the meeting's packs: "Public Agenda", "Public Minutes".
* ``allMembers.asp`` and ``political.asp`` (then ``partyMembers.asp``): the current members, wards and parties.

The minutes are PDFs. A pack or document link (``viewPack.asp``, ``viewDoc.asp``) opens a page that shows the PDF in
a frame (``viewSelectedPack.asp``, ``viewSelectedDocument.asp``); some sites serve the pack page only to a request
that says which agenda page it came from, as a browser does. Where a meeting has no minutes pack (Falkirk), its
minutes are the "Minute of meeting ... held on <date>" paper on the committee's next agenda, as on Modern.gov.

Meeting pages don't list attendance, so it is read from the sederunt at the top of the minutes ("Present: ...").
Members are matched to the members pages by name; a party is given only to a current councillor, and only at
meetings since the last ordinary election, when the members pages' party is theirs. Former councillors' parties
are left blank: they are never guessed.

Every response is cached under ``raw/coins/<council>/``. Requests to a site are spaced at least
``min_interval_seconds`` apart, with the crawler's own user agent, and robots.txt is checked before each one.
"""

from __future__ import annotations

import hashlib
import html as html_lib
import json
import logging
import re
import threading
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote_plus, urljoin

import httpx
from lxml import html as lxml_html

from councils import committees
from councils.config import Settings
from councils.registry import Council
from councils.sources import documents, robots

log = logging.getLogger(__name__)

# Scottish councils' ordinary elections. A current councillor's party on the members pages is theirs since the last
# one; before it they may have stood for another party, or not been a councillor.
SCOTTISH_ELECTIONS = [date(2012, 5, 3), date(2017, 5, 4), date(2022, 5, 5), date(2027, 5, 6)]


class CoinsError(RuntimeError):
    pass


class Refused(CoinsError):
    """The site refused the request (401, 403, 429 or a bot check). Not retried, and never worked around."""


_REFUSAL = re.compile(r"has been blocked|request rejected|connection denied|incapsula|access denied|captcha"
                      r"|just a moment|attention required|bot (?:check|protection)", re.I)


def _decode(content: bytes) -> str:
    try:
        return content.decode("utf-8")
    except UnicodeDecodeError:
        return content.decode("cp1252", errors="replace")


class Client:
    """One council's CoINS site."""

    _locks: dict[str, threading.Lock] = {}

    def __init__(self, settings: Settings, council: str, base_url: str):
        cfg = settings.modgov
        self.council = council
        self.base = base_url.rstrip("/") + "/"
        self.cache = settings.raw_dir / "coins" / council
        self.user_agent = cfg.get("user_agent", "WhereCouncilsStand")
        self.interval = float(cfg.get("min_interval_seconds", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self.refetch_days = int(cfg.get("refetch_days", 120))
        self.http = httpx.Client(headers={"User-Agent": self.user_agent},
                                 timeout=float(cfg.get("timeout_seconds", 40)), follow_redirects=True)
        self._last = 0.0
        self._lock = self._locks.setdefault(council, threading.Lock())

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def url(self, rel: str) -> str:
        return urljoin(self.base, rel)

    def allowed(self, url: str) -> bool:
        return robots.allowed(url, self.user_agent)

    # Transport -----------------------------------------------------------------
    def _get(self, url: str, referer: str | None = None) -> httpx.Response:
        if not self.allowed(url):
            raise Refused(f"robots.txt forbids {url}")
        headers = {"Referer": referer} if referer else {}
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries):
                wait = self.interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = self.http.get(url, headers=headers)
                    self._last = time.monotonic()
                    if r.status_code in (401, 403, 429):
                        raise Refused(f"{self.council} {url}: HTTP {r.status_code}")
                    if r.status_code == 200:
                        if not r.content.startswith(b"%PDF") and _REFUSAL.search(_decode(r.content[:5000])):
                            raise Refused(f"{self.council} {url}: refused by a bot check")
                        return r
                    last_error = CoinsError(f"{self.council} {url}: HTTP {r.status_code}")
                    if r.status_code in (400, 404, 410):
                        break
                except httpx.HTTPError as e:
                    self._last = time.monotonic()
                    last_error = e
                time.sleep(2 * (attempt + 1))
            raise CoinsError(str(last_error))

    def page(self, rel: str, name: str, max_age_days: float | None = None, refresh: bool = False) -> str:
        """A page, from the cache unless it isn't cached, ``refresh``, or it is older than ``max_age_days``. If
        fetching again fails, the cached copy is used: a server that is down mustn't lose what is already known."""
        path = self.cache / name
        if path.exists() and max_age_days is not None:
            refresh = refresh or (time.time() - path.stat().st_mtime) > max_age_days * 86_400
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")
        try:
            r = self._get(self.url(rel))
        except Refused:
            raise
        except CoinsError as e:
            if not path.exists():
                raise
            log.warning("%s: %s; using the copy cached %s", self.council, e,
                        datetime.fromtimestamp(path.stat().st_mtime).date())
            return path.read_text(encoding="utf-8")
        if "/err.asp" in str(r.url).lower():
            raise CoinsError(f"{self.council} {rel}: the site's error page")
        text = _decode(r.content)
        _write(path, text.encode("utf-8"))
        return text

    def document(self, rel: str, referer: str, max_age_days: float | None = None) -> bytes | None:
        """A PDF linked from a page (a pack or a paper), cached by its address. The link opens a page that shows the
        PDF in a frame, which is followed. None if the site doesn't serve it."""
        url = self.url(rel)
        path = self.cache / "documents" / (hashlib.sha1(url.encode()).hexdigest()[:20] + ".pdf")
        if path.exists() and max_age_days is not None and (time.time() - path.stat().st_mtime) > max_age_days * 86_400:
            path.unlink()
        if path.exists():
            return path.read_bytes()
        r = self._get(url, referer=referer)
        if not r.content.startswith(b"%PDF"):
            frame = viewer_frame(_decode(r.content))
            if not frame or "/err.asp" in str(r.url).lower():
                return None
            r = self._get(urljoin(str(r.url), frame), referer=str(r.url))
            if not r.content.startswith(b"%PDF"):
                return None
        _write(path, r.content)
        return r.content


def _write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    tmp.replace(path)


# Pages -----------------------------------------------------------------------------------------------------------
def _doc(text: str):
    return lxml_html.fromstring(text or "<html></html>")


def _text(el) -> str:
    """An element's text, with line breaks kept."""
    el = lxml_html.fromstring(lxml_html.tostring(el))     # a copy: the <br> tails are changed
    for br in el.iter("br"):
        br.tail = "\n" + (br.tail or "")
    return re.sub(r"[ \t\xa0]+", " ", el.text_content()).strip()


def _id(href: str, key: str) -> str:
    m = re.search(rf"[?&](?:amp;)?{key}=(\d+)", href, re.I)
    return m.group(1) if m else ""


def _show_all(text: str, page: str) -> str | None:
    """The "Show All" link of a paged list, if it has one."""
    for a in _doc(text).iter("a"):
        href = a.get("href", "")
        if page.lower() in href.lower() and re.search(r"[?&]page=0\b", href) and "rec=" in href:
            return href
    return None


@dataclass(frozen=True)
class Body:
    id: int
    title: str


def parse_committees(text: str) -> list[Body]:
    out, seen = [], set()
    for a in _doc(text).iter("a"):
        href = a.get("href", "")
        if re.match(r"(?:\./)?committee\.asp\?", href, re.I) and (bid := _id(href, "bodyid")):
            title = re.sub(r"\s+", " ", a.text_content()).strip()
            if int(bid) not in seen and title:
                seen.add(int(bid))
                out.append(Body(int(bid), title))
    return out


@dataclass(frozen=True)
class MeetingRef:
    id: int
    date: date
    location: str


def parse_date(text: str) -> date | None:
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", text or "")
    if not m:
        return None
    try:
        return date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
    except ValueError:
        return None


def parse_meetings(text: str) -> list[MeetingRef]:
    """The meetings in a committee's year list."""
    out, seen = [], set()
    for tr in _doc(text).iter("tr"):
        links = [a for a in tr.iter("a") if re.search(r"agenda\.asp\?meetingid=\d+", a.get("href", ""), re.I)]
        if not links:
            continue
        mid, d = int(_id(links[0].get("href", ""), "meetingid")), parse_date(links[0].text_content())
        if not d or mid in seen:
            continue
        cells = [re.sub(r"\s+", " ", td.text_content()).strip() for td in tr.findall("td")]
        seen.add(mid)
        out.append(MeetingRef(mid, d, cells[2] if len(cells) > 2 else ""))
    return out


@dataclass
class AgendaItem:
    position: int
    number: str
    title: str
    text: str
    submissions: list[str]
    restricted: bool


@dataclass
class Agenda:
    title: str
    location: str
    packs: dict[str, str] = field(default_factory=dict)     # "Public Minutes" -> link
    items: list[AgendaItem] = field(default_factory=list)
    cancelled: bool = False


_EXEMPT = re.compile(r"exempt|private|press and public|public (?:are|is|be|may be) excluded|not (?:open )?to the public"
                     r"|confidential", re.I)
_PUBLIC = re.compile(r"^public (?:session|items|business)", re.I)


def parse_agenda(text: str) -> Agenda:
    doc = _doc(text)
    h4 = doc.xpath('//div[@id="content"]//h4') or doc.xpath("//h4")
    title = re.sub(r"\s+", " ", h4[0].text_content()).strip() if h4 else ""
    details = " ".join(_text(d) for d in doc.xpath('//div[@id="AgendaDetails"]'))
    loc = re.search(r"held (?:at|in|within) (.+?) at \d{1,2}[:.]\d{2}", details)
    agenda = Agenda(title, loc.group(1).strip() if loc else "",
                    cancelled=bool(re.search(r"\bcancelled\b|\bpostponed\b", title + " " + details, re.I)))
    for a in doc.xpath('//div[@id="docPacks"]//a'):
        label = re.sub(r"\(\s*[\d.]+\s*[KMG]?B\s*\)", "", a.text_content(), flags=re.I).strip()
        if a.get("href") and label:
            agenda.packs[label] = a.get("href")
    restricted = False
    parent = ""
    tables = doc.xpath('//table[contains(@class,"agendaItems")]')
    rows = tables[0].xpath(".//tr[td]") if tables else []
    for tr in rows:
        tds = tr.findall("td")
        if len(tds) >= 2:
            number, cell = re.sub(r"\s+", " ", tds[0].text_content()).strip(), tds[1]
        else:
            number, cell = "", tds[0]
        subs = [_id(a.get("href", ""), "submissionid") for a in cell.iter("a")
                if "submissiondocuments" in a.get("href", "").lower()]
        subs = [s for s in subs if s]
        body = re.sub(r"\s*View Papers\s*$", "", _text(cell)).strip()
        lines = [ln.strip() for ln in body.split("\n") if ln.strip()]
        if not lines:
            continue
        if not number:
            if _PUBLIC.search(lines[0]):
                restricted = False
            elif _EXEMPT.search(body) and not subs:
                restricted = True
            if not subs:
                continue           # a heading ("Chief Executive.", "Public Session"), not an item
        if re.fullmatch(r"\(?[a-z]{1,4}\)?\.?", number, re.I):
            if parent:       # "(a)" under item 4: "4(a)"
                number = f"{parent}{number if number.startswith('(') else f'({number})'}"
        elif number:
            parent = number.rstrip(".")
        agenda.items.append(AgendaItem(len(agenda.items), number, lines[0], "\n".join(lines[1:]), subs, restricted))
    return agenda


def parse_submission(text: str) -> list[tuple[str, str]]:
    """A paper's documents: (name, link)."""
    out = []
    for tr in _doc(text).iter("tr"):
        links = [a.get("href", "") for a in tr.iter("a")
                 if re.search(r"view(?:Selected)?Doc(?:ument)?\.asp", a.get("href", ""), re.I)]
        cells = tr.findall("td")
        if links and cells:
            out.append((re.sub(r"\s+", " ", cells[0].text_content()).strip(), links[0]))
    return out


def viewer_frame(text: str) -> str | None:
    """The PDF inside a document viewer page: the frame's source, or its "View PDF in Full Window" link."""
    doc = _doc(text)
    for el in doc.iter("iframe", "embed", "object"):
        src = el.get("src") or el.get("data")
        if src and re.search(r"viewSelected", src, re.I):
            return src
    for a in doc.iter("a"):
        if re.search(r"viewSelected(?:Pack|Document)\.asp", a.get("href", ""), re.I):
            return a.get("href")
    return None


@dataclass(frozen=True)
class Member:
    id: str
    name: str
    ward: str
    party: str = ""


def parse_members(text: str) -> list[tuple[str, str, str]]:
    """(member id, name, ward) from a members list."""
    out, seen = [], set()
    for tr in _doc(text).iter("tr"):
        links = [a for a in tr.iter("a") if re.match(r"(?:\./)?member\.asp\?", a.get("href", ""), re.I)]
        if not links or not (mid := _id(links[0].get("href", ""), "id")) or mid in seen:
            continue
        cells = [re.sub(r"\s+", " ", td.text_content()).strip() for td in tr.findall("td")]
        seen.add(mid)
        out.append((mid, re.sub(r"\s+", " ", links[0].text_content()).strip(), cells[1] if len(cells) > 1 else ""))
    return out


def parse_parties(text: str) -> list[tuple[str, str]]:
    """(link, party name) from the political parties page."""
    out = []
    for a in _doc(text).iter("a"):
        href = a.get("href", "")
        if re.match(r"(?:\./)?partyMembers\.asp\?", href, re.I):
            out.append((href, re.sub(r"\s+", " ", a.text_content()).strip()))
    return out


# Names -----------------------------------------------------------------------------------------------------------
_TITLES = re.compile(
    r"^(?:(?:the|councill?ors?|cllrs?\.?|mr|mrs|ms|miss|dr|rev(?:d)?|sir|dame|prof|"
    r"(?:right\s+hon(?:ourable)?\s+)?(?:(?:lord|depute|deputy|vice)[\s-]+)*provost|"
    r"(?:depute\s+|deputy\s+|vice[- ])?conven[eo]r|(?:depute\s+|deputy\s+)?leader(?:\s+of\s+the\s+council)?|"
    r"bailie|baillie|lord\s+dean\s+of\s+guild|ex\s+officio)\b\.?,?\s*)+", re.I)
_ROLE_TITLE = re.compile(r"^(?:the\s+)?((?:(?:lord|depute|deputy|vice)[\s-]+)*provost|(?:depute\s+|deputy\s+)?conven[eo]r|"
                         r"(?:depute\s+|deputy\s+)?leader|bailie|baillie)\b", re.I)
_NOT_NAME = {"of", "the", "and", "for", "council", "committee", "city", "chambers", "meeting", "hybrid", "remote",
             "remotely", "link", "present", "via", "officers", "officer", "attendance", "apologies", "guild", "dean",
             "chair", "chairperson", "convener", "provost", "leader", "page", "minute", "minutes", "agenda", "item",
             "held", "director", "convenor", "deacon", "executive", "manager", "head", "services", "service", "clerk", "chief", "depute",
             "deputy", "substitute", "member", "members", "councillors", "councillor", "teams", "microsoft", "video",
             "external", "co-optees", "optees", "co-opted", "representative", "representatives",
             "by", "with", "at", "in", "on", "to", "as", "was", "were", "is", "elected", "absent", "none", "nil"}
_PARTICLES = {"de", "da", "van", "von", "der", "le", "la", "du", "di", "del", "st", "mc", "mac", "o'"}


def _fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.replace("’", "'").replace("‘", "'"))
    return "".join(c for c in s if not unicodedata.combining(c))


def name_key(name: str) -> str:
    """A name for matching: lower case, without titles, accents or punctuation other than hyphens."""
    n = _TITLES.sub("", _fold(name).strip())
    n = re.sub(r"[^a-z' -]", " ", n.lower()).replace("'", "")
    return re.sub(r"\s+", " ", n).strip()


def slug(name: str) -> str:
    return re.sub(r"[^a-z]+", "-", name_key(name)).strip("-")


def _pretty(name: str) -> str:
    """"FRANK McAVEETY" -> "Frank McAveety"; names already in mixed case are kept."""
    def word(w: str) -> str:
        if not w.isupper() and not re.match(r"^(?:Mc|Mac)[A-Z]{2,}$", w):
            return w
        out = re.sub(r"[^\W\d_]+", lambda m: m.group(0).capitalize(), w.lower())
        out = re.sub(r"^(Ma?c)([a-z])", lambda m: m.group(1) + m.group(2).upper(), out)
        return out
    return " ".join(word(w) for w in name.split())


def looks_like_name(name: str) -> bool:
    words = name.replace("’", "'").split()
    if not 2 <= len(words) <= 5 or re.search(r"\d", name):
        return False
    if any(w.lower().strip(".,") in _NOT_NAME for w in words):
        return False
    letters = [w for w in words if re.sub(r"[^A-Za-z]", "", w)]
    if len(letters) != len(words) or not any(len(re.sub(r"[^A-Za-z]", "", w)) >= 2 for w in words):
        return False
    return all(re.match(r"^[A-ZÀ-Þ][\w'’.-]*$", w) or w.lower() in _PARTICLES for w in words)


class Members:
    """The council's current members, to match names written in minutes."""

    def __init__(self, members: list[Member]):
        self.members = members
        self.by_full: dict[str, list[Member]] = {}
        self.by_surname: dict[str, list[Member]] = {}
        for m in members:
            k = name_key(m.name)
            self.by_full.setdefault(k, []).append(m)
            if k:
                self.by_surname.setdefault(k.split()[-1], []).append(m)

    def match(self, written: str) -> Member | None:
        k = name_key(written)
        if not k:
            return None
        if len(hit := self.by_full.get(k, [])) == 1:
            return hit[0]
        words = k.split()
        same = self.by_surname.get(words[-1], [])
        if not same or len(words) < 2:
            return None
        given = words[:-1]
        if all(len(w) == 1 for w in given):      # initials: "R W Thomson"
            hits = [m for m in same if "".join(w[0] for w in name_key(m.name).split()[:-1]).startswith("".join(given))]
        else:                                     # a first name: "Willie Boyle" matches no "William Boyle"
            hits = [m for m in same if name_key(m.name).split()[0] == given[0]]
        return hits[0] if len(hits) == 1 else None


# The sederunt --------------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Attendee:
    name: str          # as written, tidied: "Richard Bell"
    role: str          # "Chair", "Provost", "Substitute", "Member", ...
    attendance: str    # "Present", "In attendance", "Apologies"


_HEADER = re.compile(
    r"^\s*(?P<h>present(?:\s+(?:via|by)\s+(?:remote\s+link|video\s+(?:link|conference)|microsoft\s+teams)|\s+remotely"
    r"|\s+in\s+person)?|sederunt|members\s+present|councill?ors\s+also\s+(?:attending|present)|councill?ors(?:\s+present)?|elected\s+members(?:\s+present)?"
    r"|also\s+present|also\s+in\s+attendance|also\s+attending|in\s+attendance(?:\s*\([^)]*\))?(?:\s*\([^)]*\))?"
    r"|apolog(?:y|ies)(?:\s+for\s+absence)?(?:\s+(?:were\s+)?received\s+from)?|absent|attending"
    r"|officers?(?:\s+in\s+attendance|\s+present)?|officials|religious\s+representatives?"
    r"|(?:external\s+)?co-?opt(?:ed|ees?)(?:\s+members?)?"
    r"|church\s+representatives?|non[- ]voting\s+members?|observers?|chairperson)"
    r"\s*(?::-|:|–|—|-(?=\s))\s*", re.I)
# A job title: a block of the sederunt naming one lists officers, whatever its header says.
_STAFF = re.compile(r"\b(?:director|clerk|chief executive|chief officer|executive manager|manager|head of|solicitor"
                    r"|secretary|advis[eo]r|team leader|committee officer|officer|governance|for the chief"
                    r"|representative|co-?opt\w*)\b", re.I)
_PRESENT = re.compile(r"^(?:present|sederunt|members present|councill?ors|elected members)", re.I)
_ALSO = re.compile(r"^(?!.*officer)(?:.*\balso\b|in attendance)", re.I)
_APOLOGIES = re.compile(r"^(?:apologies|absent)", re.I)


def _two_names(line: str) -> list[str]:
    """Two names on one line, set apart by a wide space ("JACQUELINE MCLAREN  MARTHA WARDROP"), but not one name
    with a wide space in it ("LEÒDHAS  MASSIE")."""
    parts = re.split(r"\s{2,}", line.strip())
    if len(parts) > 1 and all(len(p.split()) >= 2 for p in parts):
        return parts
    return [line]


def _upper(line: str) -> bool:
    """A line in capitals, allowing "MacLEOD" and "McAVEETY"."""
    return re.sub(r"\bMa?c(?=[A-Z])", "", line).isupper()


def _split(block: str) -> list[str]:
    """A block of the sederunt into names. A block with commas or semicolons is a list in sentences (lines wrap
    inside names); one without is a name a line."""
    block = re.sub(r"-\s*\n\s*", "-", block)
    if re.search(r"[,;]", block):
        parts, depth, cur = [], 0, ""
        for ch in re.sub(r"\s*\n\s*", " ", block):
            depth += ch == "("
            depth -= ch == ")"
            if ch in ",;" and depth <= 0:
                parts.append(cur)
                cur = ""
            else:
                cur += ch
        parts.append(cur)
    else:
        parts = [p for line in block.split("\n") for p in _two_names(line)]
    out = []
    for p in parts:
        out += re.split(r"\s+(?:and|&)\s+(?![^(]*\))", p)
    return [re.sub(r"\s+", " ", p).strip(" .:") for p in out if p.strip(" .:")]


def _attendee(token: str, attendance: str) -> Attendee | None:
    role = "Member"
    paren = re.findall(r"\(([^)]*)\)", token)
    token = re.sub(r"\([^)]*\)?", " ", token).strip(" .,")
    for p in paren:
        if re.search(r"\b(?:chair|chairperson|chairman|convener|presiding)\b", p, re.I) and not re.search(r"vice|depute|deputy", p, re.I):
            role = "Chair"
        elif re.search(r"vice[- ]chair|depute convener|deputy convener|vice[- ]convener", p, re.I):
            role = "Vice Chair"
        elif re.search(r"substitut", p, re.I):
            role = "Substitute"
    if role == "Member" and (t := _ROLE_TITLE.match(token)):
        role = re.sub(r"\s+", " ", t.group(1)).title()
    name = _TITLES.sub("", token.replace("’", "'")).strip(" .,")
    if not looks_like_name(name):
        return None
    return Attendee(_pretty(name), role, attendance)


def _caps_run(text: str) -> list[Attendee]:
    """A sederunt whose "Present:" didn't come out of the PDF (one of Glasgow's): a run of at least ten names a line
    in capitals near the top, before anything else."""
    run: list[Attendee] = []
    for raw in text[:6000].split("\n"):
        line = raw.strip()
        if not line or re.search(r"\d", line):
            continue
        found = [a for p in _two_names(line) if (a := _attendee(p, "Present"))] if _upper(line) else []
        if found:
            run += found
        elif len(run) >= 10:
            return run
        elif _upper(line):
            continue                    # "LORD DEAN OF GUILD", "MINUTES", "OF"
        else:
            run = []
    return run if len(run) >= 10 else []


def sederunt(text: str) -> list[Attendee]:
    """Who attended, from the sederunt at the top of a meeting's minutes: "Present: Councillor X (Chair), ...". The
    first sederunt is read (a meeting that resumes may take it again). Officers and other people who aren't members
    are left out (docs/DECISIONS.md, 9): their sections end the list, a block naming job titles is dropped whatever
    its header, and names under "In attendance" are kept only if they are matched to a councillor later.

    Headers printed beside their lists come out of the PDF one after another, before the lists ("Present:",
    "Apologies:", "Attending:", then the names): headers with nothing between them are queued, and the lists that
    follow are given to them in order."""
    out: list[Attendee] = []
    queue: list[str] = []           # sections awaiting names: "Present", "In attendance", "Apologies", "" (others)
    block: list[str] = []
    since_header = 0                # lines read since the last header
    read = 0

    def flush() -> bool:
        """Read the lines gathered; False if they show the sederunt is over."""
        b = "\n".join(block).strip()
        block.clear()
        if not b or not queue:
            return True
        tokens = _split(b)
        if any(_STAFF.search(t) for t in tokens):        # officers, whatever the header says
            if len(queue) > 1:
                queue.pop(0)
            return True
        found = [a for t in tokens if (a := _attendee(t, queue[0]))]
        if found:
            if queue[0]:
                out.extend(found)
            if len(queue) > 1:
                queue.pop(0)
            return True
        # text that isn't names: the end of the sederunt, unless headers are still waiting for their lists
        return not (tokens and len(b) > 60 and len(queue) == 1)

    head = re.sub(r"(?<=\w)-[ \t]*\n\s*(?=\w)", "-", text[:20000].replace("\r", ""))   # "External Co-\nOptees:"
    head = re.sub(r"\b(also)[ \t]*\n\s*(?=(?:attending|present)\b)", r"\1 ", head, flags=re.I)  # "Councillors Also\nAttending:"
    for raw in head.split("\n"):
        line = raw.strip()
        if queue:
            read += len(line) + 1
            if read > 6000:
                break
        m = _HEADER.match(line + " ") if line else None
        if m and (queue or _PRESENT.match(m.group("h"))):
            if not flush():
                break
            h = re.sub(r"\s+", " ", m.group("h").lower())
            section = ("In attendance" if _ALSO.match(h) else "Present" if _PRESENT.match(h)
                       else "Apologies" if _APOLOGIES.match(h) else "")
            if queue and since_header == 0:
                queue.append(section)           # a header straight after another: its list comes later
            else:
                queue[:] = [section]
            since_header = 0
            line = line[m.end():].strip()
            if not line:
                continue
        if not queue:
            continue
        if re.fullmatch(r"\d+\.|\d+\.\s+\S.*|[A-Z]{1,3}\d+\.?\s+\S.*", line):
            break                       # the first numbered item ("1.", "FC71. Sederunt"): the sederunt is over
        if re.search(r"\d", line):
            continue                    # page numbers, addresses, footers: names never have digits
        if not line:
            if not flush():
                break
            continue
        if queue == [""] and re.search(r"\bpresided\b|\bsederunt\b|^the (?:meeting|council|committee)\b", line, re.I):
            break
        since_header += 1
        block.append(line)
    flush()
    if not out:
        out = _caps_run(head)
    # one person listed twice (across a page break, or as present and as a substitute): keep the first
    seen, unique = set(), []
    for a in out:
        k = name_key(a.name)
        if k not in seen:
            seen.add(k)
            unique.append(a)
    return unique


# Fetching a council -------------------------------------------------------------------------------------------
def _members(client: Client) -> tuple[Members, date]:
    """The current members with their parties, and the date the members pages were read."""
    age = 7.0
    text = client.page("allMembers.asp?sort=0&page=0&rec=1000", "members.html", max_age_days=age)
    rows = parse_members(text)
    if not rows:                                  # an older version without "Show All"
        rows = parse_members(client.page("allMembers.asp?sort=0", "members_1.html", max_age_days=age))
    party: dict[str, str] = {}
    try:
        parties = parse_parties(client.page("political.asp", "political.html", max_age_days=age))
    except CoinsError as e:
        log.warning("%s political parties: %s", client.council, e)
        parties = []
    for href, label in parties:
        pid = _id(href, "id") or re.sub(r"\W+", "_", label)
        rel = re.sub(r"&amp;", "&", href)
        rel += "" if "page=" in rel else "&page=0&rec=1000"
        try:
            ptext = client.page(rel, f"party/{pid}.html", max_age_days=age)
        except CoinsError as e:
            log.warning("%s party %s: %s", client.council, label, e)
            continue
        for mid, _, _ in parse_members(ptext):
            party[mid] = re.sub(r"\s*\([A-Za-z ]{1,8}\)$", "", label)   # "Scottish Green Party (SGP)"
    path = client.cache / "members.html"
    read_on = datetime.fromtimestamp(path.stat().st_mtime).date() if path.exists() else date.today()
    return Members([Member(mid, name, ward, party.get(mid, "")) for mid, name, ward in rows]), read_on


def _term_start(on: date) -> date:
    return max((e for e in SCOTTISH_ELECTIONS if e <= on), default=date.min)


def _year_list(client: Client, body: Body, year: int) -> list[MeetingRef]:
    today = date.today()
    final = (today - date(year, 12, 31)).days > 31          # a list read over a month after its year is final
    name = f"meetings/{body.id}_{year}.html"
    path = client.cache / name
    if path.exists() and final:
        final = datetime.fromtimestamp(path.stat().st_mtime).date() > date(year + 1, 1, 31)
    rel = (f"allBodyMeetings.asp?bodyid={body.id}&bodytitle={quote_plus(body.title)}&MeetingYear={year}"
           f"&page=0&rec=1000")
    text = client.page(rel, name, max_age_days=None if final else 0.9)
    refs = parse_meetings(text)
    if (more := _show_all(text, "allBodyMeetings")) and len(refs) <= 10:
        refs = parse_meetings(client.page(html_lib.unescape(more), f"meetings/{body.id}_{year}_all.html",
                                          max_age_days=None if final else 0.9))
    return refs


MINUTE_OF = re.compile(r"^\W*(?:\(?[a-z0-9]{1,3}[.)]\s*)?(?:draft\s+)?minutes?\s+(?:of|from)\b", re.I)
_PAPER = re.compile(r"\bminutes?\b|\bheld on\b", re.I)


@dataclass(frozen=True)
class Sitting:
    ref: MeetingRef
    agenda: Agenda
    body: Body


def _stem(title: str) -> str:
    """A committee's name as its minutes papers give it: "Executive (2013 - June 2024)" -> "executive"."""
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", " ", title)).strip().lower()


def _minutes_paper(client: Client, sitting: Sitting, later: list[Sitting]) -> str | None:
    """Where a meeting has no minutes pack, its minutes are a paper on a later agenda ("Minute of Meeting of the
    Executive held on 11 June 2024", or "Minute" with that line under it), found by the meeting's date. The
    committee's own next agendas are searched first, then the other committees' in scope, whose papers must name the
    committee: Falkirk's Executive approves its minutes at whichever sitting of it comes next, under another title."""
    own = [s for s in later if s.body.id == sitting.body.id][:3]
    others = [s for s in later if s.body.id != sitting.body.id][:6]
    stem = _stem(sitting.body.title)
    for s in own + others:
        for it in s.agenda.items:
            words = f"{it.title}\n{it.text}"
            if not it.submissions or not _PAPER.search(it.title) or sitting.ref.date not in documents.dates_in(words):
                continue
            if s.body.id != sitting.body.id and stem not in re.sub(r"\s+", " ", words.lower()):
                continue
            text = client.page(f"submissiondocuments.asp?submissionid={it.submissions[0]}",
                               f"submission/{it.submissions[0]}.html")
            docs = parse_submission(text)
            named = [link for name, link in docs if re.search(r"minute", name, re.I)
                     and not re.search(r"item minute", name, re.I)]
            chosen = named[0] if named else (docs[0][1] if len(docs) == 1 else None)
            if chosen:
                return chosen
    return None


def _clean_title(title: str) -> str:
    """An agenda title as the minutes head it: without "- Report by ...", "(herewith)"."""
    t = re.split(r"\s+[-–]\s+(?:joint\s+)?report\s+by\b|\s*[.;]?\s+report\s+by\b|\(herewith\)|\s+[-–]\s+report\b"
                 r"|\s+[-–]\s+(?:members|councillors)\s+(?:are|must|should|will)\b", title, maxsplit=1, flags=re.I)[0]
    return t.strip(" .;:-–")


def fetch(settings: Settings, council: Council, start: date, end: date, update: bool = False):
    """``(Result, meetings, items, attendance)``, rows as the Modern.gov path makes them (sources/meeting.py)."""
    from councils.ingest import Result

    res = Result(council.gss)
    meetings: list[dict] = []
    items: list[dict] = []
    attendance: list[dict] = []
    if not council.modgov_url:
        res.error = "no CoINS site"
        return res, [], [], []
    with Client(settings, council.gss, council.modgov_url) as client:
        if not client.allowed(client.url("allCommittees.asp?sort=1")):
            res.error = "robots.txt forbids crawling"
            return res, [], [], []
        try:
            text = client.page("allCommittees.asp?sort=1&page=0&rec=1000", "committees.html",
                               max_age_days=7 if update else None)
            bodies = parse_committees(text)
            if (more := _show_all(text, "allCommittees")) and len(bodies) <= 10:
                bodies = parse_committees(client.page(html_lib.unescape(more), "committees_all.html",
                                                      max_age_days=7 if update else None))
            members, read_on = _members(client)
        except Refused as e:
            res.error = f"refused: {e}"
            return res, [], [], []
        except CoinsError as e:
            res.error = str(e)
            return res, [], [], []
        for b in bodies:
            k = committees.kind(b.title, council.gss)
            if k:
                res.committees[b.id] = (b.title, k)
        term = _term_start(read_on)
        sittings: list[Sitting] = []
        for bid, (title, _) in sorted(res.committees.items()):
            body = Body(bid, title)
            refs: list[MeetingRef] = []
            try:
                for year in range(start.year, end.year + 1):
                    refs += _year_list(client, body, year)
            except CoinsError as e:
                log.warning("%s committee %s: %s", council.gss, bid, e)
                if update:
                    res.error = f"committee {bid}: {e}"
                    return res, [], [], []
                continue
            for ref in sorted({r.id: r for r in refs}.values(), key=lambda r: (r.date, r.id)):
                if ref.date < start or ref.date > end:
                    continue
                recent = (date.today() - ref.date).days < client.refetch_days
                try:
                    agenda = parse_agenda(client.page(f"Agenda.asp?meetingid={ref.id}", f"agenda/{ref.id}.html",
                                                      max_age_days=0.9 if recent else None))
                except CoinsError as e:
                    log.warning("%s meeting %s: %s", council.gss, ref.id, e)
                    res.failed.append(ref.id)
                    continue
                sittings.append(Sitting(ref, agenda, body))
        sittings.sort(key=lambda s: (s.ref.date, s.ref.id))
        for n, sitting in enumerate(sittings):
            later = [s for s in sittings[n + 1:] if (s.ref.date - sitting.ref.date).days <= 250]
            try:
                m, its, att = _meeting(client, council, sitting, res.committees[sitting.body.id][1], later, members,
                                       term, res)
            except CoinsError as e:
                log.warning("%s meeting %s: %s", council.gss, sitting.ref.id, e)
                res.failed.append(sitting.ref.id)
                continue
            meetings.append(m)
            items += its
            attendance += att
    attendance = _councillors_only(meetings, attendance)
    res.meetings = len(meetings)
    return res, meetings, items, attendance


def _councillors_only(meetings: list[dict], attendance: list[dict]) -> list[dict]:
    """Names in a committee's sederunt that aren't current councillors are kept only if full council's sederunts
    list them too, so they were councillors: a committee may list others who aren't, such as the religious
    representatives who sit on committees for education business (docs/DECISIONS.md, 9)."""
    kinds = {m["meeting_id"]: m["kind"] for m in meetings}
    council = {a["member_id"] for a in attendance if kinds.get(a["meeting_id"]) == "council"}
    kept = [a for a in attendance if a["member_id"].isdigit() or kinds.get(a["meeting_id"]) == "council"
            or a["member_id"] in council]
    counts: dict[str, int] = {}
    for a in kept:
        counts[a["meeting_id"]] = counts.get(a["meeting_id"], 0) + 1
    for m in meetings:
        m["attendees"] = counts.get(m["meeting_id"], 0)
    return kept


def _meeting(client: Client, council: Council, sitting: Sitting, kind: str, later: list[Sitting], members: Members,
             term: date, res) -> tuple[dict, list, list]:
    ref, agenda, body = sitting.ref, sitting.agenda, sitting.body
    gss = council.gss
    key = f"{gss}:{ref.id}"
    agenda_url = client.url(f"Agenda.asp?meetingid={ref.id}")
    rows = []
    earlier = []
    for it in agenda.items:
        iid = it.submissions[0] if it.submissions else f"n{it.number or it.position}"
        if MINUTE_OF.search(it.title) and it.submissions:
            earlier.append({"title": it.title,
                            "url": client.url(f"submissiondocuments.asp?submissionid={it.submissions[0]}")})
        rows.append({
            "item_id": f"{key}:{iid}", "meeting_id": key, "gss": gss, "date": ref.date, "year": ref.date.year,
            "position": it.position, "number": it.number, "title": it.title, "agenda_text": it.text,
            "minutes_text": "", "minutes_source": "", "vote_tables": "", "is_decision": False,
            "is_restricted": it.restricted, "is_call_in": False, "declaration_count": 0,
            "documents": len(it.submissions),
            "url": client.url(f"submissiondocuments.asp?submissionid={it.submissions[0]}") if it.submissions
            else agenda_url,
        })
    seen_ids: set[str] = set()
    for r in rows:                                       # one paper can serve two items: keep ids unique
        while r["item_id"] in seen_ids:
            r["item_id"] += "+"
        seen_ids.add(r["item_id"])

    # The minutes: the meeting's own "Public Minutes" pack, or the paper on a following agenda.
    text, doc_url = "", ""
    if ref.date <= date.today():
        link = next((href for label, href in agenda.packs.items()
                     if re.search(r"minute", label, re.I) and not re.search(r"exempt|private|login", label, re.I)
                     and "login" not in href.lower()), None)
        recent = (date.today() - ref.date).days < client.refetch_days
        data = None
        try:
            link = link or _minutes_paper(client, sitting, later)
            data = client.document(link, agenda_url, max_age_days=0.9 if recent else None) if link else None
        except Refused as e:          # not worked around: the meeting is kept without its minutes
            log.warning("%s minutes: %s", key, e)
            res.documents_refused = True
        except CoinsError as e:       # kept without its minutes, but an update won't replace what is stored
            log.warning("%s minutes: %s", key, e)
            res.failed.append(ref.id)
        if link and data:
            text = documents.pdf_text(data)
            doc_url = client.url(link)
            if len(text) >= 200:
                res.documents_read += 1
            else:
                text = ""          # a scanned document, or no text
    extra = []
    if text:
        public = [r for r in rows if not r["is_restricted"]]
        parts = documents.split_into_items(text, [{**r, "title": _clean_title(r["title"])} for r in public]) \
            if public else None
        if parts:
            for r in rows:
                if r["item_id"] in parts:
                    r["minutes_text"], r["minutes_source"] = parts[r["item_id"]], "document"
        else:      # the items couldn't be found in the minutes: keep them whole, as ingest does
            extra.append({"item_id": f"{key}:minutes", "meeting_id": key, "gss": gss, "date": ref.date,
                          "year": ref.date.year, "position": -1, "number": "", "title": "Minutes",
                          "agenda_text": "", "minutes_text": text.strip(), "minutes_source": "document",
                          "vote_tables": "", "is_decision": False, "is_restricted": False, "is_call_in": False,
                          "declaration_count": 0, "documents": 0, "url": doc_url})

    attendance = []
    for a in sederunt(text) if text else []:
        m = members.match(a.name)
        if a.attendance == "In attendance" and not m:
            continue             # under "In attendance", only names that are councillors
        current = m is not None and ref.date >= term
        attendance.append({
            "meeting_id": key, "gss": gss, "date": ref.date, "year": ref.date.year,
            "member_id": m.id if m else slug(a.name), "member_type": "",
            "name": m.name if m else a.name, "role": a.role, "attendance": a.attendance,
            "party_label": m.party if current and m else "", "ward": m.ward if current and m else "",
        })

    all_items = rows + extra
    meeting = {
        "meeting_id": key, "gss": gss, "council": council.name, "committee_id": body.id,
        "committee_title": body.title, "kind": kind, "date": ref.date, "year": ref.date.year,
        "status": "Cancelled" if agenda.cancelled else "", "location": ref.location or agenda.location,
        "webcast": False, "minutes_published": bool(text), "items": len(rows),
        "items_with_minutes": sum(1 for r in rows if len(r["minutes_text"]) > 40) or (1 if extra else 0),
        "earlier_minutes": json.dumps(earlier) if earlier else "", "minutes_document": doc_url,
        "attendees": len(attendance), "url": agenda_url,
    }
    return meeting, all_items, attendance
