"""The goldens as the site gives them since the family kit 2.0 (17 November 2026).

The goldens beside this file were recorded from the code before the move onto wts-core (record.py), and that code
can no longer be run. When the pages took on the family's design and wording, the goldens were brought up to date
by applying the changes listed here, and only these, to the goldens as recorded (commit cb698fd):

    uv run python tests/golden/kit_two.py

Each change is a regular expression and its replacement, applied to every string in every golden file. The tests
then compare what the site gives with the rewritten goldens exactly, so any other difference still fails. Run it
once, on the goldens as recorded: it refuses goldens that have already been rewritten.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).parent))

import shared  # noqa: E402

# sentences of the site's own that now have curly apostrophes, as written in the code (and as escaped in a page)
APOSTROPHES = [
    "What has Barnsley's full council decided about libraries?",
    "The site has reached today's limit on new briefings, which keeps its costs down.",
    "The site has reached this month's limit on new briefings, which keeps its costs down.",
    "Sourced briefings on what councils across the UK have discussed, decided and voted on. Every point cites the council's own minutes.",
    " principal councils in the UK and England's ",
    " authorities are covered, from when, and which party is in overall control (or, for an authority, its mayor's party).",
    '<h1>Named vote not found</h1><p>There is no named vote at this address. Each council\'s named votes are listed on its page: see the <a href="/councils">list of councils</a>.</p>',
    "Mayor's decisions",
    "Its meetings site couldn't be reached.",
    "It doesn't publish its minutes through a system we can read yet.",
    "Its meetings site answers, but it hasn't been loaded yet or failed to load.",
    "No attendance records, so votes can't be matched to councillors.",
    "% of meetings (often published only as documents the site wouldn't serve, or not yet).",
    "% of attendance, so votes can't all be read by party.",
    ", from the authority's own minutes. ",
    ", with each member's role and party on the date.",
    "</ul><p>Each with the party they were elected for. A mayor's party is shown in place of a party in control: a strategic authority isn't run by a party.</p>",
    ", with each councillor's party on the date.",
    ", read from the authority's ",
    "this authority's minutes",
    ", read from the council's ",
    "this council's minutes",
    "<p>Only one side of this vote could be read from the minutes. The others may be recorded in a form that couldn't be read, or not at all.</p>",
    ". Names are matched to the councillors listed at the meeting. The names of people who aren't councillors are removed.</p>",
    ", from the council's own minutes. ",
    "<p>This strategic authority isn't covered yet. ",
    ", with each member's role, and their party on the date from their home council's record where the site has it. Appointed members who aren't councillors aren't named.</p><ul>",
    "home council's record",
    "the authority's record",
    "<p>This council isn't covered yet. ",
    "<p>The authority's mayor on the date: ",
    " (a strategic authority isn't run by a party). Each member's party is the one their home council recorded for them at the time, where the site has it.</p>",
    ". Each councillor's party is the one the council recorded for them at the time.</p>",
    " of England's ",
    " strategic authorities (combined authorities, combined county authorities and the Greater London Authority) are covered: their boards and overview and scrutiny committees. Each is shown with its mayor's party, which isn't control of the authority or its councils.</p><ul>",
    ', since May 2018. Asking a question needs JavaScript; every council\'s page, with its named votes, can be read without it, from the <a href="/councils">list of councils</a>.</p><h2>Questions to try</h2><ul>',
    " of the mayor's decisions",
    "The item in the council's own minutes",
    "There's no page at that address on this site. Copy the address from the page the statement is about.",
    "The address must be a council's page, a named vote or a briefing on this site, such as https://wherecouncilsstand.com/votes/…",
]


def curly(text: str) -> str:
    return re.sub(r"(?<=[A-Za-z])'(?=[A-Za-z])", "\u2019", text)


CHANGES: list[tuple[str, str]] = [
    # page titles: "Page | Site name"
    (" \u2014 Where Councils Stand", " | Where Councils Stand"),
    # details separated by commas; the council's type and region under its name
    ('<p class="meta"><a href="/councils">Councils</a> \u00b7 (<a href="/councils/[^"]+">[^<]+</a>)</p>',
     r'<p class="meta">\1</p>'),
    ('<p class="meta"><a href="/councils">Councils</a> \u00b7 Strategic authority \u00b7 ([^<]*)</p>(<h1>[^<]*</h1>)',
     r'<p class="meta"><a href="/councils">All councils</a></p>\2<p class="meta">Strategic authority, \1</p>'),
    ('<p class="meta"><a href="/councils">Councils</a> \u00b7 ([^<]*) \u00b7 ([^<]*)</p>(<h1>[^<]*</h1>)',
     r'<p class="meta"><a href="/councils">All councils</a></p>\3<p class="meta">\1, \2</p>'),
    # a council's figures as a list of terms and values, worded as on the page once its script runs
    (r"<ul><li>In overall control: ([^<]*)</li><li>([\d,]+) meetings?: ([^<]*)</li>"
     r"<li>([\d,]+) named votes? recorded in the minutes</li></ul>",
     r'<dl class="facts"><dt>In overall control</dt><dd>\1</dd><dt>Meetings</dt><dd>\2: \3</dd>'
     r"<dt>Named votes</dt><dd>\4 recorded in the minutes</dd></dl>"),
    # the home page: a heading that is not a question, and the family's words about the briefings
    ("<h1>What has your council decided\\?</h1>", "<h1>Council decisions, from the minutes</h1>"),
    (r"Answers only from the official record, every point linked and checked. "
     r'<a href="/methodology#why">Why use this rather than a chatbot\?</a>',
     "Briefings are written by AI from the official record only, and every citation is checked. "
     '<a href="/methodology#ai-briefings">How the briefings are checked</a>'),
    ("<h2>For example</h2>", "<h2>Questions to try</h2>"),
    ('<p><a href="/methodology">How it works</a></p>', '<p><a href="/methodology">Methodology</a></p>'),
    # each correction headed by what it was
    ('<li><p class="corrections-when">(<time [^>]*>[^<]*</time>) \u00b7 <strong>([^<]*)</strong></p>',
     r'<li><h3>\2</h3><p class="corrections-when">\1</p>'),
] + [(re.escape(old.replace("'", quote)), curly(old).replace("\\", "\\\\"))
     for old in APOSTROPHES for quote in ("'", "&#x27;")]


# text that is itself JSON, written with non-ASCII characters escaped: structured data in a page, and the events of a
# briefing as they are streamed
ENCODED = re.compile(r'<script type="application/ld\+json">.*?</script>|^data: .*$', re.S | re.M)


def change(text: str, counts: list[int], encoded: bool) -> str:
    for i, (pattern, to) in enumerate(CHANGES):
        if encoded:
            to = to.replace("\u2019", "\\\\u2019")
        text, n = re.subn(pattern, to, text)
        counts[i] += n
    return text


def rewrite(value: Any, counts: list[int]) -> Any:
    if isinstance(value, str):
        out, at = [], 0
        for m in ENCODED.finditer(value):
            out += [change(value[at:m.start()], counts, False), change(m.group(0), counts, True)]
            at = m.end()
        return "".join(out + [change(value[at:], counts, False)])
    if isinstance(value, list):
        return [rewrite(v, counts) for v in value]
    if isinstance(value, dict):
        return {k: rewrite(v, counts) for k, v in value.items()}
    return value


def main(folder: Path) -> None:
    counts = [0] * len(CHANGES)
    for path in sorted(folder.glob("*.json")):
        before = shared.read(path.name) if folder == shared.GOLDEN else json.loads(path.read_text(encoding="utf-8"))
        after = rewrite(before, counts)
        if after != before:
            shared.write(folder, path.name, after)
            print(f"{path.name}: rewritten")
    if not counts[0]:
        raise SystemExit("no page title was changed: these goldens have been rewritten already")
    for (pattern, _), n in zip(CHANGES, counts, strict=True):
        print(f"{n:4} {pattern[:90]}")


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else shared.GOLDEN)
