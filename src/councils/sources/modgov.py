"""Client for Civica Modern.gov's public web service, ``<site>/mgWebService.asmx``.

The service is undocumented; what it returns was read from its WSDL and responses (docs/DATA.md). It needs no key.
Every response is cached under ``raw/modgov/<council>/``, so a council is fetched once and parsed as often as
needed. Requests to one council are spaced at least ``min_interval_seconds`` apart.

Dates in requests and responses are day/month/year.
"""

from __future__ import annotations

import html
import logging
import re
import threading
import time
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

import httpx
from lxml import etree

from councils.config import Settings

log = logging.getLogger(__name__)

_PARSER = etree.XMLParser(recover=True, huge_tree=True, resolve_entities=False, no_network=True)


@dataclass(frozen=True)
class Committee:
    id: int
    title: str
    expired: bool
    deleted: bool


@dataclass(frozen=True)
class MeetingRef:
    id: int
    committee_id: int
    date: date
    status: str


class ModgovError(RuntimeError):
    pass


def ddmmyyyy(d: date) -> str:
    return d.strftime("%d/%m/%Y")


def parse_date(text: str | None) -> date | None:
    text = (text or "").strip()
    for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M:%S"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def xml(text: str) -> etree._Element:
    """Parse a web service response. Some councils' responses carry stray control characters."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    root = etree.fromstring(cleaned.encode("utf-8"), _PARSER)
    if root is None:
        raise ModgovError("unreadable response")
    return root


def _t(el: etree._Element, path: str) -> str:
    found = el.find(path)
    return (found.text or "").strip() if found is not None and found.text else ""


class Client:
    """One council's Modern.gov web service."""

    _locks: dict[str, threading.Lock] = {}

    def __init__(self, settings: Settings, council: str, base_url: str):
        cfg = settings.modgov
        self.council = council
        self.base = base_url.rstrip("/") + "/mgWebService.asmx"
        self.cache = settings.raw_dir / "modgov" / council
        self.interval = float(cfg.get("min_interval_seconds", 1.0))
        self.retries = int(cfg.get("retries", 3))
        self.refetch_days = int(cfg.get("refetch_days", 120))
        self.http = httpx.Client(
            headers={"User-Agent": cfg.get("user_agent", "WhereCouncilsStand")},
            timeout=float(cfg.get("timeout_seconds", 40)),
            follow_redirects=True,
        )
        self._last = 0.0
        self._lock = self._locks.setdefault(council, threading.Lock())

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> Client:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # Transport -----------------------------------------------------------------
    def _get(self, op: str, **params: str | int) -> str:
        with self._lock:
            last_error: Exception | None = None
            for attempt in range(self.retries):
                wait = self.interval - (time.monotonic() - self._last)
                if wait > 0:
                    time.sleep(wait)
                try:
                    r = self.http.get(f"{self.base}/{op}", params=params)
                    self._last = time.monotonic()
                    if r.status_code == 200:
                        return r.text
                    last_error = ModgovError(f"{self.council} {op}: HTTP {r.status_code}")
                    if r.status_code in (400, 403, 404):
                        break
                except httpx.HTTPError as e:
                    self._last = time.monotonic()
                    last_error = e
                time.sleep(2 * (attempt + 1))
            raise ModgovError(str(last_error))

    def _cached(self, name: str, op: str, refresh: bool = False, **params: str | int) -> str:
        path = self.cache / name
        if path.exists() and not refresh:
            return path.read_text(encoding="utf-8")
        text = self._get(op, **params)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
        return text

    # Operations ----------------------------------------------------------------
    def committees(self, refresh: bool = False) -> list[Committee]:
        root = xml(self._cached("committees.xml", "GetCommittees", refresh=refresh))
        out = []
        for c in root.iter("committee"):
            cid = _t(c, "committeeid")
            if not cid.isdigit():
                continue
            out.append(Committee(
                id=int(cid),
                title=html.unescape(_t(c, "committeetitle")),
                expired=_t(c, "committeeexpired").lower() == "true",
                deleted=_t(c, "committeedeleted").lower() == "true",
            ))
        return out

    def meetings(self, committee_id: int, start: date, end: date, refresh: bool = False) -> list[MeetingRef]:
        name = f"meetings/{committee_id}_{start:%Y%m%d}_{end:%Y%m%d}.xml"
        text = self._cached(name, "GetMeetings", refresh=refresh, lCommitteeId=committee_id,
                            sFromDate=ddmmyyyy(start), sToDate=ddmmyyyy(end))
        out = []
        for m in xml(text).iter("meeting"):
            mid, d = _t(m, "meetingid"), parse_date(_t(m, "meetingdate"))
            if mid.isdigit() and d:
                out.append(MeetingRef(int(mid), committee_id, d, _t(m, "meetingstatus")))
        return out

    def document(self, url: str) -> bytes | None:
        """A document (usually a PDF) linked from a meeting, cached by its Modern.gov id; None if the site refuses
        to serve documents to automated requests (many do, behind a browser check)."""
        doc_id = re.search(r"ID=(\d+)", url) or re.search(r"/s(\d+)/", url)
        name = doc_id.group(1) if doc_id else re.sub(r"\W+", "_", url)[-80:]
        path = self.cache / "documents" / f"{name}.pdf"
        if path.exists():
            return path.read_bytes()
        with self._lock:
            wait = self.interval - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            try:
                r = self.http.get(url)
            except httpx.HTTPError as e:
                raise ModgovError(f"{self.council} document: {e}") from e
            finally:
                self._last = time.monotonic()
        if r.status_code in (401, 403, 429, 503) or not r.content.startswith(b"%PDF"):
            return None
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(r.content)
        return r.content

    def meeting(self, meeting_id: int, meeting_date: date | None = None, refresh: bool = False) -> etree._Element:
        """The whole meeting: agenda items with their minutes, attendance and documents. Recent meetings are fetched
        again until their minutes have had time to be approved."""
        recent = meeting_date is not None and (date.today() - meeting_date).days < self.refetch_days
        path = self.cache / "meeting" / f"{meeting_id}.xml"
        stale = recent and path.exists() and (time.time() - path.stat().st_mtime) > 86_400
        text = self._cached(f"meeting/{meeting_id}.xml", "GetMeeting", refresh=refresh or stale,
                            lMeetingId=meeting_id)
        return xml(text)


def probe(settings: Settings, council: str, base_url: str) -> tuple[str, int]:
    """("ok", number of committees), ("blocked", HTTP status), ("unreachable", 0) when the connection fails, or
    ("none", HTTP status) when the site answers without a Modern.gov web service. Not cached."""
    cfg = settings.modgov
    try:
        r = httpx.get(base_url.rstrip("/") + "/mgWebService.asmx/GetCommittees",
                      headers={"User-Agent": cfg.get("user_agent", "WhereCouncilsStand")},
                      timeout=float(cfg.get("timeout_seconds", 40)), follow_redirects=True)
    except httpx.ConnectError:
        return "unreachable", 0
    except httpx.HTTPError:
        return "unreachable", 0
    if r.status_code == 200 and "<committees" in r.text:
        m = re.search(r"<committeescount>\s*(\d+)", r.text)
        return "ok", int(m.group(1)) if m else 0
    if r.status_code in (401, 403, 429, 503):
        return "blocked", r.status_code
    return "none", r.status_code


def cached_meeting(cache_root: Path, council: str, meeting_id: int) -> etree._Element | None:
    path = cache_root / "modgov" / council / "meeting" / f"{meeting_id}.xml"
    return xml(path.read_text(encoding="utf-8")) if path.exists() else None
