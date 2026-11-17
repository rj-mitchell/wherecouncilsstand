"""Minutes published only as a document.

Some councils put a meeting's minutes in a PDF instead of the web service's minutes text. Modern.gov attaches a
meeting's minutes to the agenda of the committee's next meeting, at the item that approves them ("Minutes",
"Confirmation of the minutes of the last meeting"), so that is where they are found. The document chosen is the one
whose title carries the meeting's date ("02 Minutes 011123", "Minutes 17 January 2024"); a single undated document is
taken only if no other meeting of the committee fell between the two.

The text is split into the meeting's agenda items by finding each item's title in it, in order. Where fewer than
half the titles are found, the whole text is kept as one item, so it can still be searched and cited.
"""

from __future__ import annotations

import contextlib
import io
import json
import logging
import re
from datetime import date

log = logging.getLogger(__name__)

MONTHS = {m: i for i, m in enumerate(["january", "february", "march", "april", "may", "june", "july", "august",
                                      "september", "october", "november", "december"], 1)}
MONTHS |= {m[:3]: i for m, i in list(MONTHS.items())} | {"sept": 9}


def dates_in(title: str) -> set[date]:
    """Dates written in a document title, in the forms councils use."""
    t = title.lower().replace("_", " ")
    out: set[date] = set()

    def add(y: int, m: int, d: int) -> None:
        if y < 100:
            y += 2000
        with contextlib.suppress(ValueError):   # not a real date
            out.add(date(y, m, d))

    for d, m, y in re.findall(r"\b(\d{1,2})[./-](\d{1,2})[./-](\d{2}|\d{4})\b", t):
        add(int(y), int(m), int(d))
    for y, m, d in re.findall(r"\b(\d{4})[./-](\d{1,2})[./-](\d{1,2})\b", t):
        add(int(y), int(m), int(d))
    # a lookahead, so "03-01 minutes 15 may 2024" isn't read as "01 minutes 15" and the real date missed
    for d, mon, y in re.findall(r"\b(?=(\d{1,2})(?:\s?(?:st|nd|rd|th))?\s+([a-z]{3,9})\.?,?\s+(\d{4}|\d{2})\b)", t):
        if mon in MONTHS:
            add(int(y), MONTHS[mon], int(d))
    for run in re.findall(r"(?<!\d)(\d{6}|\d{8})(?!\d)", t):   # "011123", "17012024", "20240117"
        if len(run) == 8 and run[:2] in ("19", "20"):
            add(int(run[:4]), int(run[4:6]), int(run[6:]))
        elif len(run) == 8:
            add(int(run[4:]), int(run[2:4]), int(run[:2]))
        else:
            add(int(run[4:]), int(run[2:4]), int(run[:2]))
    return out


def choose(meeting_date: date, later_meetings: list[dict]) -> dict | None:
    """This meeting's minutes document, from the earlier-minutes documents on the committee's following meetings
    (nearest first). Each meeting dict has ``date`` and ``earlier_minutes`` (JSON)."""
    for n, later in enumerate(later_meetings[:3]):
        docs = json.loads(later["earlier_minutes"]) if later.get("earlier_minutes") else []
        dated = [d for d in docs if meeting_date in dates_in(d["title"])]
        if dated:
            return dated[0]
        undated = [d for d in docs if not dates_in(d["title"])]
        if n == 0 and len(docs) == 1 and undated:
            return undated[0]   # the very next meeting approves one set of minutes, with no date given
    return None


def pdf_text(data: bytes) -> str:
    from pdfminer.high_level import extract_text

    try:
        return extract_text(io.BytesIO(data)) or ""
    except Exception as e:  # damaged or encrypted documents
        log.warning("unreadable document: %s", e)
        return ""


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()


def split_into_items(text: str, items: list[dict]) -> dict[str, str] | None:
    """{item_id: text} by finding each agenda item's title in the document, in order; None if under half are found."""
    flat = re.sub(r"[ \t ]+", " ", text)
    lowered = flat.lower()
    starts = []
    pos = 0
    for it in items:
        title = _norm(it["title"])[:60]
        if len(title) < 4:
            starts.append(None)
            continue
        words = title.split()
        pattern = r"\W+".join(re.escape(w) for w in words)
        m = re.search(pattern, lowered[pos:])
        if m:
            starts.append(pos + m.start())
            pos += m.end()
        else:
            starts.append(None)
    found = [s for s in starts if s is not None]
    if len(found) * 2 < len([it for it in items if len(_norm(it["title"])) >= 4]) or not found:
        return None
    out = {}
    marks = [(s, it["item_id"]) for s, it in zip(starts, items, strict=True) if s is not None]
    for n, (s, item_id) in enumerate(marks):
        end = marks[n + 1][0] if n + 1 < len(marks) else len(flat)
        out[item_id] = re.sub(r"\n{2,}", "\n", flat[s:end]).strip()
    return out
