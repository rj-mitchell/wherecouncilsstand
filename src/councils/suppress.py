"""Names and phrases the owner has removed by hand: the suppression list.

The rules in parse/redact.py remove most names of people who aren't councillors, but not all (docs/PILOT.md). When a
reader asks for a name to be taken down, or the owner finds one, it goes on this list, for one council and, if
wanted, for one meeting or agenda item only:

    councils suppress add "North Somerset" "Lucy Byrne" --note "takedown request 41"
    councils suppress add E07000216 "Steve Dally" --item E07000216:1234:5678

The list is the file ``suppress.csv`` in the data folder (``/data`` on the server), beside ``settings.local.toml``.
It is never in the repository, which is public: the list is itself a list of people's names. The state database
(src/councils/state.py) holds only the shared package's tables, so the list isn't there either.

Each entry is applied wherever minutes text or an agenda item's title is shown or given to the model, as the page is
served or the briefing written, so an entry takes effect at once: the sources of a briefing, the pages of named
votes, and saved and cached briefings. The search index still holds the words until the council is indexed again
(``councils index <council>``), which takes them out of what can be searched for; ``councils suppress add`` says so.

Matching ignores case, runs of spaces and the kind of apostrophe, and only whole words are matched ("Ann Lee" is not
found in "Joann Leeds"). Each match is replaced with "[name removed]", as parse/redact.py does.
"""

from __future__ import annotations

import csv
import re
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date
from functools import cached_property
from pathlib import Path

from councils.parse.redact import REMOVED

FILE = "suppress.csv"
COLUMNS = ("council", "item", "text", "added", "note")


@dataclass(frozen=True)
class Entry:
    council: str            # a GSS code
    item: str               # "" for the whole council, else an agenda item's id or a meeting's (its prefix)
    text: str               # the name or phrase
    added: str = ""         # YYYY-MM-DD
    note: str = ""          # why, for the owner (a report's number, say); never shown

    def covers(self, gss: str, item_id: str = "") -> bool:
        if gss != self.council:
            return False
        return not self.item or item_id == self.item or item_id.startswith(self.item + ":")

    @cached_property
    def pattern(self) -> re.Pattern:
        words = [re.escape(w).replace("'", "['’]") for w in self.text.replace("’", "'").split()]
        return re.compile(r"(?<!\w)" + r"\s+".join(words) + r"(?!\w)", re.I)


class Suppressions:
    def __init__(self, entries: Iterable[Entry] = ()):
        self.entries = [e for e in entries if e.text.strip() and e.council]
        self.councils = {e.council for e in self.entries}

    def __bool__(self) -> bool:
        return bool(self.entries)

    def apply(self, text: str, gss: str, item_id: str = "") -> str:
        """``text`` with every entry for this council (and this item, where an entry is for one) removed."""
        if not text or gss not in self.councils:
            return text
        for e in self.entries:
            if e.covers(gss, item_id):
                text = e.pattern.sub(REMOVED, text)
        return text

    def apply_any(self, text: str, councils: Iterable[str]) -> str:
        """``text`` with the entries of any of these councils removed, whatever their item: for a briefing's own
        words, which aren't from one item."""
        if not text:
            return text
        wanted = set(councils) & self.councils
        for e in self.entries:
            if e.council in wanted:
                text = e.pattern.sub(REMOVED, text)
        return text


def path(data_dir: Path) -> Path:
    return Path(data_dir) / FILE


_cache: dict[Path, tuple[float, Suppressions]] = {}
_lock = threading.Lock()


def stamp(data_dir: Path) -> float:
    """When the list last changed (0 if there is none): part of what says the record has changed."""
    p = path(data_dir)
    return p.stat().st_mtime if p.exists() else 0.0


def load(data_dir: Path) -> Suppressions:
    """The list as it is now: read again whenever the file has changed."""
    p = path(data_dir)
    when = stamp(data_dir)
    with _lock:
        held = _cache.get(p)
        if held and held[0] == when:
            return held[1]
    entries = []
    if when:
        with p.open(newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                entries.append(Entry(council=(row.get("council") or "").strip().upper(),
                                     item=(row.get("item") or "").strip(), text=(row.get("text") or "").strip(),
                                     added=row.get("added") or "", note=row.get("note") or ""))
    out = Suppressions(entries)
    with _lock:
        _cache[p] = (when, out)
    return out


def add(data_dir: Path, council: str, text: str, item: str = "", note: str = "", today: date | None = None) -> Entry:
    """Add an entry to the list (made with its header if there is none yet)."""
    text = " ".join(text.split())
    if len(text) < 2:
        raise ValueError("Give the name or phrase to remove.")
    entry = Entry(council=council.upper(), item=item.strip(), text=text, added=(today or date.today()).isoformat(),
                  note=note)
    p = path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    new = not p.exists()
    with p.open("a", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        if new:
            w.writerow(COLUMNS)
        w.writerow([entry.council, entry.item, entry.text, entry.added, entry.note])
    return entry
