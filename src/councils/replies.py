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
* ``hideable``: hiding by the address the owner pastes, filed under the item's own address, so that what is
  hidden in the database is what the pages ask about; and ``Hidden``, what is hidden now, as the pages, the lists
  and the search are told it.

How a statement looks on the pages, and where it is placed, is in src/councils/api/plaintext.py and the web pages.
A statement is never part of the record: nothing here is read by the search index, the briefing engine or the AI
model (src/councils/rag, engine.py, index/), and tests/test_statements.py checks that it never reaches the model.
Nothing about a visitor is passed to the package: the site counts nobody's reports or statements.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from typing import Any, Protocol
from urllib.parse import unquote, urlsplit

from wts_core import replies as core
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies import Item, NotDone, Refused, Replies, ReplyMessages, ReplyRules
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
    item_not_shown="There’s no page at that address on this site. Copy the address from the page the statement is "
                   "about.",
    # never shown: no visitor is counted (see RULES)
    daily_statements="We have several statements from you today. Email us if there is more to add.",
    daily_reports="We have several reports from you today. Email us if there is more to add.",
    # the form sends a kind and stops at these lengths, so only a post made some other way meets these; the first
    # two are the family's words, the same on every Where They Stand site (owner, 16 November 2026)
    report_kind="Please choose what the report is about.",
    report_too_short="Please say what is wrong, in a few words.",
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
            raise Refused("The address must be a council’s page, a named vote or a briefing on this site, such as "
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


# What a reader is shown in a hidden item's place: this sentence, then the note the owner gave when hiding it
# (the impartiality policy, 7.3: "the item can be hidden meanwhile, with a note").
HIDDEN_LEAD = "This page is hidden while a concern about it is decided."
# The corrections log's heading for each kind of entry: a briefing withdrawn, or a report closed with a public note.
LOG_WITHDRAWN, LOG_CORRECTION = "Briefing withdrawn", "Correction"


def hideable(items: Items) -> Callable[[str], str]:
    """This site's one spelling for an item that can be hidden while a concern about it is decided
    (``wts_core.replies.Replies(hideable=…)``). The owner gives the page's address as a reader would copy it (a
    full address or a path, in any case, with or without a slash on the end); it is filed under the item's own
    address, which is what the pages ask about. Only what has an address of its own can be hidden: a council's
    (or strategic authority's) page, a named vote, or a saved briefing; and only one that is on the site."""

    def filed(typed: str) -> str:
        try:
            found = items.resolve(typed)
        except Refused:
            raise NotDone("only a council's page, a named vote or a briefing can be hidden: give its address on "
                          "this site, such as /votes/… or /councils/…") from None
        if not items.shown(found):
            raise NotDone(f"there is no page at {found.address} on this site")
        return found.address

    return filed


@dataclass(frozen=True)
class Hidden:
    """What is hidden now, while a concern is decided: each item's address and the note to show in its place.

    * A council's page hidden: the note stands in place of its page and of each of its named votes' pages; it is
      left out of the list of councils and the sitemap, and its minutes are left out of search, so of the sources
      of every briefing written meanwhile.
    * A named vote hidden: the note stands in place of its page; it is left out of its council's list of votes
      and the sitemap, and is not given with its agenda item's minutes as a source (the minutes themselves, which
      are the council's words, still are).
    * A briefing hidden: the note stands in place of the briefing, and it is not replayed to a reader who asks
      the same question.
    * A briefing saved before a council or a vote was hidden, with that council's minutes or that vote among its
      sources: the council's or the vote's note stands in place of the briefing too, until it is shown again.

    Statements beside a hidden item are hidden with it."""

    notes: Mapping[str, str]

    def _of(self, kind: str) -> frozenset[str]:
        return frozenset(a.split("/")[2] for a in self.notes if a.startswith(f"/{kind}/"))

    @property
    def councils(self) -> frozenset[str]:
        return self._of("councils")

    @property
    def votes(self) -> frozenset[str]:
        return self._of("votes")

    def note(self, address: str) -> str | None:
        """The note to show in place of the page at ``address``: its own, or, for a named vote, its council's."""
        own = self.notes.get(address)
        if own is None and address.startswith("/votes/"):
            own = self.notes.get(f"/councils/{address.split('/')[2].split(':')[0]}")
        return own

    def instead(self, address: str) -> str | None:
        """What a reader is shown in place of the page at ``address``, or None if it is not hidden."""
        note = self.note(address)
        return None if note is None else f"{HIDDEN_LEAD} {note}"

    def vote_hidden(self, vote_id: str) -> bool:
        return self.note(f"/votes/{vote_id}") is not None

    def instead_of_briefing(self, briefing_id: str, events: Any) -> str | None:
        """What a reader is shown in place of a saved briefing, or None if it may be shown: its own note if the
        briefing itself is hidden; otherwise the note of the first hidden council or named vote among the sources
        it was written from. A briefing written before a page was hidden carries that page's words (its minutes
        among the sources, a vote's sides in a source and perhaps in the briefing's own text), so while the page
        is hidden the briefing is too."""
        own = self.instead(f"/b/{briefing_id}")
        if own is not None or not self.notes:
            return own
        for event in events or ():
            if not isinstance(event, Mapping) or event.get("type") != "sources":
                continue
            for card in event.get("sources") or ():
                if card.get("gss") in self.councils:
                    return self.instead(f"/councils/{card['gss']}")
                for vote in card.get("votes") or ():
                    cited = self.instead(f"/votes/{vote.get('vote_id')}")
                    if cited is not None:
                        return cited
        return None


def hidden_now(replies: Replies) -> Hidden:
    return Hidden({h["item"]: h["note"] for h in replies.all_hidden()})


def corrections(replies: Replies, briefings: SavedBriefings) -> list[dict[str, Any]]:
    """The public corrections log (the impartiality policy, 7.1: "a public note saying what changed and when"),
    newest first, every entry there is: each briefing that was withdrawn, with the reason given, and each report
    closed with a note for this log. Each entry is a ``date``, a ``heading`` and the ``note``, and nothing else.

    Left out on purpose. A withdrawn briefing's question: on this site a briefing may be withdrawn because its
    question names someone who is not a councillor, and the log must not repeat it. Anything a reporter wrote or
    pasted, and the page or briefing a report was about (the package gives none of it: a saved briefing is listed
    nowhere, and the log must not be the list): where readers should know which page was put right, the owner
    says so in the public note. The reason a statement was removed: that is said to its author."""
    withdrawn = [{"date": b.withdrawn_at, "note": (b.withdrawn_reason or "").strip() or None}
                 for b in briefings.withdrawn()]
    return [{"date": entry["date"],
             "heading": LOG_WITHDRAWN if entry["kind"] == "withdrawn" else LOG_CORRECTION,
             "note": entry["note"] or ""}
            for entry in replies.corrections(withdrawn=withdrawn)]      # the whole log: no limit is given


def open_replies(db: StateDB, record: Callable[[], Record], briefings: SavedBriefings, clock: Clock = SYSTEM_CLOCK, *,
                 messages: ReplyMessages = MESSAGES) -> Replies:
    """Reports and statements, for the site's endpoints, its pages and the owner's commands alike."""
    items = Items(record, briefings)

    def hidden_with(item: Item) -> bool:
        """Whether an item a statement sits beside is hidden now because another is (``Replies(hidden_with=…)``,
        asked by ``Replies.published`` of each item once): a named vote of a council whose page is hidden, and a
        saved briefing shown as hidden because of a council or a named vote it was written from. A statement
        beside such an item is hidden with it, as one beside an item hidden by its own address always is."""
        now = hidden_now(replies)
        if not now.notes:
            return False
        kind, key = item.address.split("/")[1:3]
        if kind == "votes":
            return now.vote_hidden(key)
        if kind == "b":
            saved = briefings.get(key)
            return saved is not None and now.instead_of_briefing(saved.id, saved.events) is not None
        return False

    replies = Replies(db, items=items, rules=RULES, messages=messages, clock=clock, hideable=hideable(items),
                      hidden_with=hidden_with)
    return replies


def as_shown(statement: Mapping[str, Any]) -> dict[str, Any]:
    """A published statement under the names this site's pages and its API have for its fields: never its author's
    email address or the owner's notes (the package gives only what the public may see)."""
    return {"id": statement["id"], "page": statement["item"], "council": statement["about"],
            "name": statement["name"], "role": statement["role"], "text": statement["text"],
            "link": statement["link"] or "", "shown_on": statement["date"]}


def published(replies: Replies, page: Item | None = None, council: str | None = None) -> list[dict[str, Any]]:
    """What the public sees: the published statements beside one item, or all of one council's (on its page), by
    the date shown and then in the order they came. A statement beside an item that is hidden while a concern is
    decided is hidden with it, and so is one beside an item hidden because another is (``open_replies``,
    ``hidden_with``): the package leaves both out."""
    rows = replies.published(items=[page]) if page else replies.published(about=council)
    if page and council:
        rows = [r for r in rows if r["about"] == council]
    return sorted((as_shown(r) for r in rows), key=lambda r: (r["shown_on"], r["id"]))
