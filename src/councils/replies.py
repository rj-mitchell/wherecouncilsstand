"""Readers' reports, statements under the right of reply, the corrections log and hiding an item while a concern is
decided (the charity's impartiality policy, section 7; docs/DECISIONS.md, 9, 22 and 24), kept by the Where They
Stand sites' shared package (wts-core, ``wts_core.replies``; its docs/adr/0008).

The package owns the rules and the rows: what a statement may be, its life (waiting, then published or declined; a
published one withdrawn by its author or removed by us), the log of every decision, the deleting of email addresses
in time, reports and how each ended, and what is hidden. This file is what the site passes in:

* ``Items``: where a statement may sit on this site. A council's (or strategic authority's) page, a named vote, or a
  saved briefing. Councillors have no page of their own; a councillor's statement goes beside a vote, a briefing or
  their council's page.
* ``RULES``: this site's limits (a statement of up to 150 words and 1,500 characters, a report of 5 to 5,000), and
  the kinds of report its form sends.
* ``MESSAGES``: every word a sender can be shown.

How a statement looks on the pages, and where it is placed, is in src/councils/api/plaintext.py and the web pages.
A statement is never part of the record: nothing here is read by the search index, the briefing engine or the AI
model (src/councils/rag, engine.py, index/), and tests/test_statements.py checks that it never reaches the model.
Nothing about a visitor is passed to the package: the site counts nobody's reports or statements.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import replace
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from wts_core import replies as core
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Item, Refused, Replies, ReplyMessages, ReplyRules
from wts_core.state import StateDB
from wts_core.usage import SavedBriefings

from councils.config import SITE

MAX_WORDS = 150
# the longest a 150-word statement could reasonably be, so a wall of text without spaces is refused too
MAX_CHARS = 1500
NOT_ENDORSED = "In their own words. Not checked or endorsed by Where Councils Stand."
# the items a statement can sit beside: a council's (or strategic authority's) page, a named vote, a saved briefing
_ITEM = re.compile(r"^/(councils|votes|b)/([^/\s]+)$")

RULES = ReplyRules(
    min_words=1, max_words=MAX_WORDS, max_chars=MAX_CHARS,
    name_max=200, role_max=200, link_max=500, email_max=300,      # what the form's fields take (api/app.py)
    # the package can limit how many one visitor sends in a day; this site passes it no visitor, so these never apply
    daily_statements=5, daily_reports=10,
    about_required=False,              # a statement beside a briefing belongs to no one council until the owner says
    # the policy's routes (impartiality policy 7.1): "error" is "Something is wrong", "unfair" is "You've been
    # characterised unfairly"; "takedown" is a request about someone who isn't a councillor, dealt with first
    report_kinds={"error": "error", "unfair": "unfair", "takedown": core.TAKEDOWN, "other": "other"},
    report_kind_required=True,
    report_min=5, report_max=5000, page_max=500, contact_max=300,
    email_kept_months=3,               # after a statement is withdrawn, declined or removed (the privacy page)
)

MESSAGES = ReplyMessages(
    too_few_words="Write the statement.",
    too_many_words="A statement can be up to {max} words; this one is {n}.",
    too_many_chars="A statement can be up to {words} words ({max:,} characters).",
    name_missing="Give your name, as it should be shown.",
    name_too_long="Your name, as it should be shown can be up to {max} characters.",
    role_missing="Give your role, such as Councillor, Barnsley Metropolitan Borough Council.",
    role_too_long="Your role, such as Councillor, Barnsley Metropolitan Borough Council can be up to {max} "
                  "characters.",
    bad_link="The link to the record must be a web address starting https:// (or leave it empty).",
    link_too_long="The link to the record can be up to {max} characters.",
    bad_email="Give an email address we can use to confirm who you are.",
    item_not_shown="There's no page at that address on this site. Copy the address from the page the statement is "
                   "about.",
    # never shown: no visitor is counted (see RULES)
    daily_statements="We have several statements from you today. Email us if there is more to add.",
    daily_reports="We have several reports from you today. Email us if there is more to add.",
    # the form sends a kind and stops at these lengths, so only a post made some other way meets these
    report_kind="Say what kind of problem it is.",
    report_too_short="Say what is wrong, in a few words.",
    report_too_long="A report can be up to {max:,} characters; this one is {n:,}.",
    contact_too_long="The contact address can be up to {max} characters.",
    # the reason recorded for a statement nobody decided in three months; its sender is told if they ask
    lapsed="No decision was made in time; please send it again.",
    # the family glossary's heading and disclaimer
    heading="Statement from {name}, {date}",
    disclaimer="In their own words. Not checked or endorsed by {site}.",
    record_link="The record they point to",
    site=SITE.name,
)
# as the owner's commands say them, of a name or role the owner typed
OWNERS_MESSAGES = replace(MESSAGES, name_missing="Give a name.", name_too_long="A name can be up to {max} characters.",
                          role_missing="Give a role.", role_too_long="A role can be up to {max} characters.")


class Record(Protocol):
    """What ``Items`` asks of the record (api/data.py): whether a council or a named vote is on the site."""

    def council(self, gss: str) -> Mapping[str, Any] | None: ...

    def vote(self, vote_id: str) -> Mapping[str, Any] | None: ...


class Items:
    """Where a statement may sit on this site (``wts_core.replies.Items``)."""

    def __init__(self, record: Callable[[], Record], briefings: SavedBriefings) -> None:
        self._record, self._briefings = record, briefings

    def resolve(self, pasted: str, hosts: tuple[str, ...] = SITE.hosts) -> Item:
        """The item a statement is about, from what someone pasted (a full address or a path): its path on this
        site, and the council it belongs to (a briefing has none until the owner gives one)."""
        a = (pasted or "").strip()
        if not a:
            raise Refused("Give the address of the page the statement is about.", "bad_item")
        parts = urlsplit(a if "://" in a or a.startswith("/") else "https://" + a)
        if parts.scheme not in ("http", "https", "") or (parts.hostname and parts.hostname.lower() not in hosts):
            raise Refused("The address must be a page on wherecouncilsstand.com.", "bad_item")
        m = _ITEM.match(unquote(parts.path).rstrip("/"))
        if not m:
            raise Refused("The address must be a council's page, a named vote or a briefing on this site, such as "
                          "https://wherecouncilsstand.com/votes/…", "bad_item")
        kind, key = m.groups()
        if kind == "councils":
            key = key.upper()
            return Item(address=f"/councils/{key}", about=key)
        if kind == "votes":
            gss, _, rest = key.partition(":")
            key = f"{gss.upper()}:{rest}" if rest else gss.upper()
            return Item(address=f"/votes/{key}", about=gss.upper())
        return Item(address=f"/b/{key}")

    def shown(self, item: Item) -> bool:
        """Whether the item is on the site: a council or a named vote in the record, or a briefing that has not
        been withdrawn (a withdrawn briefing has no page to stand beside)."""
        kind, key = item.address.split("/")[1:3]
        if kind == "councils":
            return self._record().council(key) is not None
        if kind == "votes":
            return self._record().vote(key) is not None
        saved = self._briefings.get(key)
        return saved is not None and saved.withdrawn_at is None


def open_replies(db: StateDB, record: Callable[[], Record], briefings: SavedBriefings, clock: Clock = SYSTEM_CLOCK, *,
                 messages: ReplyMessages = MESSAGES) -> Replies:
    """Reports and statements, for the site's endpoints, its pages and the owner's commands alike."""
    return Replies(db, items=Items(record, briefings), rules=RULES, messages=messages, clock=clock)


def as_shown(statement: Mapping[str, Any]) -> dict[str, Any]:
    """A published statement under the names this site's pages and its API have for its fields: never its author's
    email address or the owner's notes (the package gives only what the public may see)."""
    return {"id": statement["id"], "page": statement["item"], "council": statement["about"],
            "name": statement["name"], "role": statement["role"], "text": statement["text"],
            "link": statement["link"] or "", "shown_on": statement["date"]}


def published(replies: Replies, page: Item | None = None, council: str | None = None) -> list[dict[str, Any]]:
    """What the public sees: the published statements beside one item, or all of one council's (on its page), by
    the date shown and then in the order they came. A statement beside an item that is hidden while a concern is
    decided is hidden with it."""
    rows = replies.published(items=[page]) if page else replies.published(about=council)
    if page and council:
        rows = [r for r in rows if r["about"] == council]
    return sorted((as_shown(r) for r in rows), key=lambda r: (r["shown_on"], r["id"]))
