"""Statements under the right of reply (the charity's impartiality policy, section 7.2; decision 22): a councillor, a
council or someone acting for them adds a short statement, in their own words, beside an item on the site.

A statement is stored in the site's own database (api/state.py) and shown beside the item and on the council's page,
headed "Statement from [name], [date]" and followed by "In their own words. Not checked or endorsed by Where Councils
Stand." It is never part of the record: nothing here is read by the search index, the briefing engine or the AI model
(src/councils/rag, engine.py, index/), and tests/test_statements.py checks that it never reaches the model.
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urlsplit

MAX_WORDS = 150
# the longest a 150-word statement could reasonably be, so a wall of text without spaces is refused too
MAX_CHARS = 1500
SITE_HOSTS = ("wherecouncilsstand.com", "www.wherecouncilsstand.com")
# the items a statement can sit beside: a council's (or strategic authority's) page, a named vote, a saved briefing.
# Councillors have no page of their own; a councillor's statement goes beside a vote, a briefing or their council's page.
_ITEM = re.compile(r"^/(councils|votes|b)/([^/\s]+)$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
NOT_ENDORSED = "In their own words. Not checked or endorsed by Where Councils Stand."


def word_count(text: str) -> int:
    return len(text.split())


def item_address(address: str, hosts: tuple[str, ...] = SITE_HOSTS) -> tuple[str, str | None]:
    """The item a statement is about, as a path on this site, and the council it belongs to (a briefing has none until
    the owner gives one). Accepts a full address or a path; raises ValueError, with words for the reader, otherwise."""
    a = (address or "").strip()
    if not a:
        raise ValueError("Give the address of the page the statement is about.")
    parts = urlsplit(a if "://" in a or a.startswith("/") else "https://" + a)
    if parts.scheme not in ("http", "https", "") or (parts.hostname and parts.hostname.lower() not in hosts):
        raise ValueError("The address must be a page on wherecouncilsstand.com.")
    m = _ITEM.match(unquote(parts.path).rstrip("/"))
    if not m:
        raise ValueError("The address must be a council's page, a named vote or a briefing on this site, such as "
                         "https://wherecouncilsstand.com/votes/…")
    kind, key = m.groups()
    if kind == "councils":
        key = key.upper()
        return f"/councils/{key}", key
    if kind == "votes":
        gss, _, rest = key.partition(":")
        key = f"{gss.upper()}:{rest}" if rest else gss.upper()
        return f"/votes/{key}", gss.upper()
    return f"/b/{key}", None


def check_text(text: str) -> str:
    """The statement's words, as written (never edited: policy 7.2), or ValueError if they are too long or missing."""
    t = (text or "").strip()
    if not t:
        raise ValueError("Write the statement.")
    if word_count(t) > MAX_WORDS:
        raise ValueError(f"A statement can be up to {MAX_WORDS} words; this one is {word_count(t)}.")
    if len(t) > MAX_CHARS:
        raise ValueError(f"A statement can be up to {MAX_WORDS} words ({MAX_CHARS:,} characters).")
    return t


def check_line(value: str, what: str, longest: int = 200) -> str:
    """A name or role, on one line (as Where Countries Stand): never blank or only spaces."""
    v = " ".join((value or "").split())
    if len(v) < 2:
        raise ValueError(f"Give {what}.")
    if len(v) > longest:
        raise ValueError(f"{what[0].upper()}{what[1:]} can be up to {longest} characters.")
    return v


def check_link(link: str) -> str:
    link = (link or "").strip()
    if link and (urlsplit(link).scheme not in ("http", "https") or not urlsplit(link).hostname or " " in link):
        raise ValueError("The link to the record must be a web address starting https:// (or leave it empty).")
    return link


def check_email(email: str) -> str:
    email = (email or "").strip()
    if not _EMAIL.match(email):
        raise ValueError("Give an email address we can use to confirm who you are.")
    return email
