"""The topic briefings' pages as the server writes them (decision 35): ``/topics``, each topic's own page and the
home page's list of topics. Everything a reader or a search engine needs is in the HTML: on a topic's page the whole
checked briefing, in the family's markup (``api/checked.py``), with the date it was prepared and the records it was
written from. The page's script (web/src/topic.tsx) only adds the record beside the briefing, or the sheet a chip
opens on a phone, from the sources written into the page as data. Plain HTML, every value escaped."""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from html import escape as e
from typing import Any
from urllib.parse import quote

from wts_core.checks import check_counts
from wts_core.dates import long_date

from councils.api import checked, titles
from councils.topics import Topic

TOPICS_ROOT = '<div id="topics"></div>'
EARLIER_SHOWN = 8   # earlier versions listed on a topic's page, newest first
ABOUT = ("Each topic briefing is written by AI from councils’ own minutes over the past twelve months, checked "
         "against them like every briefing on the site, and written afresh every week.")


@dataclass
class Shown:
    """A topic as its pages show it: its current briefing as a reader is shown it (``view``: its id, when it was
    prepared, the answer, the sources and the search's own figures), or the note that stands in its place while a
    concern is decided (``instead``), and its earlier versions."""

    topic: Topic
    view: dict[str, Any] | None = None
    instead: str | None = None
    earlier: list[dict[str, Any]] = field(default_factory=list)

    @property
    def written(self) -> bool:
        return self.view is not None and self.instead is None

    @property
    def prepared(self) -> str:
        return str(self.view["at"])[:10] if self.view else ""


def records_words(view: dict[str, Any]) -> str:
    """"24 records from 15 councils at 20 meetings, from 21 November 2025 to 21 November 2026"."""
    found = checked.found_words(view.get("evidence"), len(view.get("sources") or []))
    f = (view.get("plan") or {}).get("filters") or {}
    if f.get("date_from") and f.get("date_to"):
        found += f", from {long_date(f['date_from'])} to {long_date(f['date_to'])}"
    return found


def title(t: Topic) -> str:
    return f"{t.title}: briefing from council minutes"


def description(s: Shown) -> str:
    if not s.written:
        return titles.shorten(f"{s.topic.description} A topic briefing written by AI from councils’ own minutes, "
                              "checked against them, every week.", titles.DESCRIPTION_MAX)
    return titles.shorten(f"{s.topic.description} Written by AI from councils’ own minutes over the past twelve "
                          f"months and checked against them, prepared {long_date(s.prepared)}.",
                          titles.DESCRIPTION_MAX)


def card_alt(s: Shown) -> str:
    from councils.cards import RECORD, counts_in_words

    counts = check_counts(s.view["answer"])  # type: ignore[index]
    return (f"{s.topic.question} A briefing written by AI, checked against {RECORD}. {counts_in_words(counts)}. "
            f"Prepared {long_date(s.prepared)}. Where Councils Stand.")


# /topics


def _status_line(s: Shown) -> str:
    if s.instead:
        return "Hidden for now, while a concern about it is decided."
    if not s.written:
        return "Not written yet: it is written with the next weekly run."
    return f"Prepared {long_date(s.prepared)}, from {records_words(s.view)}."  # type: ignore[arg-type]


def index_text(shown: Sequence[Shown]) -> str:
    """The list of topics: each one's title linking to its page, its question, what it covers and when its current
    briefing was prepared."""
    items = "".join(
        f'<li><h2><a href="{e(s.topic.path)}">{e(s.topic.title)}</a></h2><p class="topic-q">{e(s.topic.question)}</p>'
        f'<p>{e(s.topic.description)}</p><p class="meta">{e(_status_line(s))}</p></li>' for s in shown)
    return ("<h1>Topics</h1>"
            f'<p class="lede">Briefings on what councils across the UK keep returning to. {e(ABOUT)}</p>'
            '<p class="small">Each briefing asks the same neutral question every week, of every council the site '
            "reads, and its evidence is balanced across councils run by different parties. "
            '<a href="/methodology#ai-briefings">How the briefings are checked</a>. For anything else, '
            '<a href="/">ask a question of your own</a>.</p>'
            f'<ul class="topic-list">{items}</ul>')


# The home page


def home_text(shown: Sequence[Shown]) -> str:
    """The home page's list: each topic with a briefing, linking to its page, and a link to them all."""
    written = [s for s in shown if s.written]
    if not written:
        return ""
    items = "".join(f'<li><a href="{e(s.topic.path)}">{e(s.topic.title)}</a><p class="meta">Prepared '
                    f'<time datetime="{e(s.prepared)}">{e(long_date(s.prepared))}</time></p></li>' for s in written)
    return ('<section class="home-topics" aria-labelledby="home-topics-heading">'
            '<h2 id="home-topics-heading">Topics</h2>'
            f"<p>Briefings on what councils keep returning to. {e(ABOUT)}</p>"
            f'<ul class="topic-links">{items}</ul>'
            '<p><a href="/topics">Every topic, with the question each one asks</a></p></section>')


def with_home_topics(page: str, shown: Sequence[Shown]) -> str:
    if TOPICS_ROOT not in page:
        return page
    return page.replace(TOPICS_ROOT, f'<div id="topics">{home_text(shown)}</div>', 1)


# A topic's page


def _data(view: dict[str, Any]) -> str:
    """What the page's script needs to show the record beside the briefing: the answer as shown and the sources,
    as data ("</" escaped, so it cannot end the script)."""
    body = json.dumps({"answer": view["answer"], "sources": view.get("sources") or []}, ensure_ascii=False)
    safe = body.replace("</", "<\\/")
    return f'<script type="application/json" id="topic-data">{safe}</script>'


def _earlier(s: Shown) -> str:
    if not s.earlier:
        return ""
    items = "".join(f'<li><a href="/b/{e(v["briefing_id"])}">Prepared {e(long_date(v["prepared_at"][:10]))}</a></li>'
                    for v in s.earlier[:EARLIER_SHOWN])
    return ('<section class="topic-earlier" aria-labelledby="earlier-heading"><h2 id="earlier-heading">Earlier '
            "briefings on this topic</h2><p>Each week’s briefing is kept at its own address, as it was written.</p>"
            f"<ul>{items}</ul></section>")


def topic_text(s: Shown, base: str) -> str:
    """A topic's page: its title and question, what it is, and its current briefing in full (the strip, the text
    with its marks and chips, how it was checked, and the sources), or the note in its place, or that it has not been
    written yet; then its earlier versions."""
    t = s.topic
    head = (f'<p class="meta"><a href="/topics">Topics</a></p><h1>{e(t.title)}</h1>'
            f'<p class="lede topic-q">{e(t.question)}</p>')
    if s.instead:
        return head + f'<p class="notice">{e(s.instead)}</p>' + _earlier(s)
    if not s.written:
        return (head + f"<p>{e(ABOUT)}</p><p>This topic’s first briefing has not been written yet. It is written with "
                "the next weekly run.</p>")
    view = s.view
    assert view is not None
    answer, sources = view["answer"], view.get("sources") or []
    link = f"{base}/b/{view['id']}"
    return (head
            + f'<p class="topic-about">{e(ABOUT)} This one was prepared on {e(long_date(s.prepared))}, from '
              f"{e(records_words(view))}.</p>"
            + f'<article class="briefing briefing--checked wts-cloth--councils" aria-label="The briefing, prepared '
              f'{e(long_date(s.prepared))}"><div class="result-grid" id="topic-grid"><div class="result-main">'
              '<p class="ai-label">Briefing written by AI</p>'
            + checked.check_strip(answer)
            + f'<div class="briefing-text" id="topic-text">{checked.briefing_text(answer.get("segments") or [], sources)}'
              "</div>"
            + checked.loaded_notice(answer)
            + checked.check_details(answer, len(sources))
            + f'<p class="small">This week’s briefing at its own address: <a href="/b/{e(view["id"])}">{e(link)}</a></p>'
              f'<p class="small"><a href="/corrections?page={e(quote(link, safe=""))}">Report a problem with this '
              "briefing</a></p>"
              "</div></div></article>"
            + checked.sources_list(sources)
            + _earlier(s)
            + _data(view))
