"""The changes made for search engines in November 2026, set aside so the parity tests can compare the rest of each
page and answer exactly with what the site gave before (tests/golden/). Each change is asserted where it is made
(test_titles.py, test_pages.py); here it is only removed from both sides, and nothing else is.

1. A named vote has a label among its item's votes, a heading, a title and a description of its own
   (api/titles.py), and its page links to the other votes near it: the API gives the new fields, and the pages'
   titles, descriptions and structured data (now with breadcrumbs) differ. A council's description is shorter.
2. A council's page lists every named vote by year, and its budget and council tax votes.
3. A saved briefing's page always asks search engines not to list it, and the home page's structured data gives
   the charity's id."""

from __future__ import annotations

import re
from typing import Any

# what the API gives for a named vote that it didn't before
NEW_VOTE_KEYS = {"label", "n", "of", "derived", "heading", "title", "budget", "description", "siblings",
                 "same_meeting", "earlier", "later"}
_HEAD = re.compile(r'\s*<(?:title>[^<]*</title|meta name="(?:description|robots)"[^>]*|'
                   r'meta property="og:(?:title|description)"[^>]*)>|\s*<script type="application/ld\+json">.*?</script>',
                   re.S)
_NEW_SECTIONS = re.compile(
    r"<h2>Budget and council tax votes, year by year</h2>.*?(?=<h2>Named votes)"
    r"|<p>The latest \d+, then every named vote by year\.</p>"
    r"|<h2>Every named vote, by year</h2>(?:<details.*?</details>)+"
    r"|<h2>Other named votes (?:on this item|at this meeting)</h2><ul[^>]*>.*?</ul>"
    r"|<nav class=\"vote-steps\".*?</nav>", re.S)


def _vote(v: Any) -> Any:
    return {k: x for k, x in v.items() if k not in NEW_VOTE_KEYS} if isinstance(v, dict) else v


def comparable(entry: Any) -> Any:
    """One page or endpoint read (tests/golden/shared.py, ``page_read``), without what changed for search engines."""
    if not isinstance(entry, dict) or "case" not in entry:
        return entry
    entry = dict(entry)
    case, body = entry["case"], entry.get("json")
    if isinstance(body, dict) and case.startswith("/api/councils/") and "votes" in body:
        entry["json"] = {**body, "votes": [_vote(v) for v in body["votes"]]}
    elif isinstance(body, dict) and case.startswith("/api/votes/"):
        entry["json"] = _vote(body)
    if isinstance(entry.get("text"), str) and re.match(r"/(?:councils/|votes/|b/|$)", case):
        entry["text"] = _NEW_SECTIONS.sub("", _HEAD.sub("", entry["text"]))
    return entry


def set_aside(now: Any, golden: Any) -> tuple[Any, Any]:
    """Both sides, each page or answer without what changed for search engines (a list of reads, or a dict of them
    by case)."""
    if isinstance(now, dict) and "case" not in now:
        return ({k: comparable(v) for k, v in now.items()}, {k: comparable(v) for k, v in golden.items()})
    return [comparable(x) for x in now], [comparable(x) for x in golden]
