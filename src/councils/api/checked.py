"""A checked briefing written by the server, in the family's markup (the charity's family/BRIEFINGS.md, with the kit's
/family/briefing.css): the check strip, the text with the record's own words set apart, a chip after each cited
passage naming the council, the meeting and the date, every passage with no source marked in words, "How this
briefing was checked", and the numbered sources. For the topic pages (decision 35), which search engines and readers
without scripts read as everyone else does.

It is the server's copy of the web app's ``web/src/checked.ts`` and ``components/Briefing.tsx`` (``BriefingText``,
``CheckStrip``, ``CheckDetails``) and ``components/Sources.tsx``, line for line, so that a briefing reads the same
however it is drawn: ``tests/test_topics.py`` writes this module's HTML for the renderer's own test answer
(``web/src/__tests__/fixtures/shown-briefing.json``) into ``shown-briefing.html``, and the web app's test
(``web/src/__tests__/topic.test.tsx``) checks that the app draws the same words and marks. A change to one is made to
the other in the same commit. Plain HTML, every value escaped.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from html import escape
from typing import Any

from wts_core.checks import check_counts
from wts_core.dates import long_date

KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee", "board": "Board",
              "mayor": "Mayor’s decisions", "scrutiny": "Overview and scrutiny"}

# quotations, as the verifier finds them (wts-core checks.verify)
QUOTE = re.compile(r"[\"“]([^\"“”\n]{6,}?)[\"”]|‘([^‘’\n]{6,}?)’(?![a-z])")
_NOT_WORD = re.compile(r"[^a-z0-9]+")

SAID_CHECKED = " (quotation, found word for word in the minutes of source {n})"
SAID_NOSOURCE = " (no source)"
SAID_INVALID = " (its citation did not match the minutes and was removed)"
WORD_JOINER = "⁠"


def e(text: Any) -> str:
    return escape(str(text), quote=True)


def said_missing(n: int | None) -> str:
    return f" (quotation not found word for word in the minutes cited for it{f', source {n}' if n else ''})"


def words_in(s: str) -> list[str]:
    return [w for w in _NOT_WORD.split(s.lower().replace("’", "").replace("'", "")) if w]


def flagged(seg: Mapping[str, Any]) -> bool:
    """Text with no source: none was given, or every citation it gave failed and was removed."""
    return seg.get("status") in ("unsupported", "invalid")


def _blank(seg: Mapping[str, Any]) -> bool:
    return seg.get("status") == "connective" and not str(seg.get("text") or "").strip()


@dataclass
class QuoteAt:
    start: int
    end: int
    quote: str
    missing: bool
    ends_here: bool
    sources: list[int]


def quotations(segments: Sequence[Mapping[str, Any]]) -> list[list[QuoteAt]]:
    """Each segment's quotations (``checked.ts``'s ``quotations``): a quotation's sources are those of the passages
    it is part of, or of the cited passage straight after it, within three characters; it is missing where the
    verifier recorded it as not found."""
    starts, pos = [], 0
    for s in segments:
        starts.append(pos)
        pos += len(str(s.get("text") or ""))
    full = "".join(str(s.get("text") or "") for s in segments)
    out: list[list[QuoteAt]] = [[] for _ in segments]
    for m in QUOTE.finditer(full):
        quote = m.group(1) or m.group(2)
        if len(words_in(quote)) < 3:
            continue
        a, b = m.start(), m.end()
        sources: list[int] = []
        for i, s in enumerate(segments):
            s0 = starts[i]
            s1 = s0 + len(str(s.get("text") or ""))
            if (s0 < b and a < s1) or (s0 >= b and s0 - b <= 3 and s.get("sources")):
                for n in s.get("sources") or []:
                    if n not in sources:
                        sources.append(n)
        for i, s in enumerate(segments):
            s0 = starts[i]
            s1 = s0 + len(str(s.get("text") or ""))
            if not (s0 < b and a < s1):
                continue
            start, end = max(a, s0) - s0, min(b, s1) - s0
            missing = any(x["start"] < end and start < x["end"] for x in s.get("misquotes") or [])
            out[i].append(QuoteAt(start, end, quote, missing, b <= s1, sources))
    return out


def other_misquotes(seg: Mapping[str, Any], found: Sequence[QuoteAt]) -> list[QuoteAt]:
    """A quotation the verifier did not find that the pattern above does not see: each of the segment's misquotes
    not already covered."""
    text = str(seg.get("text") or "")
    return [QuoteAt(x["start"], min(x["end"], len(text)), x.get("text", ""), True, x["end"] <= len(text),
                    list(seg.get("sources") or []))
            for x in seg.get("misquotes") or [] if not any(q.start < x["end"] and x["start"] < q.end for q in found)]


def firsts(answer: Mapping[str, Any]) -> dict[str, str | None]:
    """Where the strip's "Show the first" links go."""
    segs = answer.get("segments") or []
    nosource = next((i for i, s in enumerate(segs) if flagged(s)), -1)
    invalid = next((i for i, s in enumerate(segs) if s.get("status") == "invalid"), -1)
    missing = None
    for i, qs in enumerate(quotations(segs)):
        hit = next((q for q in [*qs, *other_misquotes(segs[i], qs)] if q.missing), None)
        if hit is not None:
            missing = f"misquote-{i}-{hit.start}"
            break
    return {"nosource": None if nosource < 0 else f"nosource-{nosource}",
            "invalid": None if invalid < 0 else f"nosource-{invalid}", "missing": missing}


def chips_shown(segments: Sequence[Mapping[str, Any]]) -> list[bool]:
    """Which passages show their chips: two runs next to each other from the same sources show one, after the
    second."""
    out = []
    for i, seg in enumerate(segments):
        if seg.get("status") != "cited" or not seg.get("sources"):
            out.append(False)
            continue
        j = i + 1
        while j < len(segments) and _blank(segments[j]):
            j += 1
        nxt = segments[j] if j < len(segments) else None
        out.append(not (nxt is not None and nxt.get("status") == "cited"
                        and list(nxt.get("sources") or []) == list(seg.get("sources") or [])))
    return out


def meeting_label(s: Mapping[str, Any]) -> str:
    if s.get("kind") == "council":
        return "full council"
    if s.get("kind") == "cabinet":
        return "cabinet"
    return str(s.get("committee") or KIND_LABEL.get(str(s.get("kind")), ""))


def chip_label(s: Mapping[str, Any] | None) -> str:
    if not s:
        return ""
    return ", ".join(x for x in (s.get("council_name"), meeting_label(s), long_date(s.get("date"))) if x)


def cited_sources(answer: Mapping[str, Any]) -> list[int]:
    return sorted({n for s in answer.get("segments") or [] if s.get("status") == "cited" for n in s.get("sources") or []})


# ---------- the text ----------


def chip(n: int, source: Mapping[str, Any] | None, seg: int) -> str:
    label = chip_label(source)
    return (f'<button type="button" class="wts-chip" data-source="{n}" data-seg="{seg}" '
            'data-wts-conversion="source_opened"><span class="wts-chip__in">'
            f'<span class="wts-chip__n"><span class="wts-vh">Source</span> {n}</span>'
            + (f"<span>{e(label)}</span>" if label else "") + "</span></button>")


class _Ctx:
    def __init__(self, segments: Sequence[Mapping[str, Any]]):
        self.missing_ids: set[str] = set()
        self.first_no_source = next((i for i, s in enumerate(segments) if flagged(s)), -1)


def _quote(q: QuoteAt, seg: Mapping[str, Any], i: int, inner: str, ctx: _Ctx) -> str:
    n = q.sources[0] if q.sources else None
    if q.missing:
        qid = f"misquote-{i}-{q.start}"
        fresh = qid not in ctx.missing_ids
        ctx.missing_ids.add(qid)
        own = f' id="{qid}"' if fresh else ""
        return (f'<span class="wts-quote wts-quote--missing"{own} data-seg="{i}">{inner}'
                + ('<span class="wts-quote__tick" aria-hidden="true">Not found word for word</span>'
                   f'<span class="wts-vh">{e(said_missing(n))}</span>' if q.ends_here else "") + "</span>")
    if not n or flagged(seg):
        return inner
    return (f'<span class="wts-quote wts-quote--checked" data-seg="{i}" data-source="{n}">{inner}'
            + ('<span class="wts-quote__tick" aria-hidden="true">✓ word for word</span>'
               f'<span class="wts-vh">{e(SAID_CHECKED.format(n=n))}</span>' if q.ends_here else "") + "</span>")


_BOLD = re.compile(r"\*\*([^*]+)\*\*")


def _piece(seg: Mapping[str, Any], i: int, start: int, end: int, quotes: Sequence[QuoteAt], ctx: _Ctx) -> str:
    """One piece of a segment's text, with its quotations and bold."""
    text = str(seg.get("text") or "")[start:end]
    drop: set[int] = set()
    bold: list[tuple[int, int]] = []
    for m in _BOLD.finditer(text):
        bold.append((m.start() + 2, m.start() + 2 + len(m.group(1))))
        drop.update((m.start(), m.start() + 1, m.end() - 2, m.end() - 1))
    qs = [(q, (max(q.start, start) - start, min(q.end, end) - start)) for q in quotes if q.start < end and start < q.end]
    cuts = {0, len(text)}
    for a, b in [*bold, *(r for _, r in qs)]:
        cuts.add(max(0, a))
        cuts.add(min(len(text), b))
    at = sorted(cuts)
    runs: list[tuple[str, int, bool]] = []
    for k in range(len(at) - 1):
        a, b = at[k], at[k + 1]
        t = "".join(text[x] for x in range(a, b) if x not in drop)
        if not t:
            continue
        q = next((n for n, (_, r) in enumerate(qs) if r[0] <= a and b <= r[1]), -1)
        runs.append((t, q, any(s <= a and b <= f for s, f in bold)))
    out: list[str] = []
    k = 0
    while k < len(runs):
        q = runs[k][1]
        j = k
        while j < len(runs) and runs[j][1] == q:
            j += 1
        inner = "".join(f"<strong>{e(t)}</strong>" if b else e(t) for t, _, b in runs[k:j])
        out.append(inner if q < 0 else _quote(qs[q][0], seg, i, inner, ctx))
        k = j
    return "".join(out)


def _lines(segments: Sequence[Mapping[str, Any]]) -> list[list[tuple[int, int, int] | tuple[int, list[int]]]]:
    """The briefing as lines of pieces: (segment, start, end) for a span of text, or (segment, sources) where a
    cited passage's chips go (after its last words, on the line they are on)."""
    out: list[list[Any]] = [[]]
    shows = chips_shown(segments)
    for i, seg in enumerate(segments):
        off = 0
        last: list[Any] | None = None
        for k, part in enumerate(str(seg.get("text") or "").split("\n")):
            if k > 0:
                out.append([])
            if part:
                out[-1].append((i, off, off + len(part)))
                last = out[-1]
            off += len(part) + 1
        if shows[i]:
            (last if last is not None else out[-1]).append((i, list(seg.get("sources") or [])))
    return out


_LEAD = re.compile(r"^\s*(?:[-*•]|#+)\s+")


def briefing_text(segments: Sequence[Mapping[str, Any]], sources: Sequence[Mapping[str, Any]]) -> str:
    """The briefing's text (``BriefingText``): paragraphs, lists and headings, the "In brief" section on a panel."""
    by_n = {s.get("n"): s for s in sources}
    quotes = [[*qs, *other_misquotes(segments[i], qs)] for i, qs in enumerate(quotations(segments))]
    ctx = _Ctx(segments)
    lines = _lines(segments)
    last_piece: dict[int, tuple[int, int]] = {}
    for li, line in enumerate(lines):
        for pi, p in enumerate(line):
            if len(p) == 3:
                last_piece[p[0]] = (li, pi)
    seen: set[int] = set()

    def inline(line: list[Any], li: int) -> str:
        out: list[str] = []
        for pi, p in enumerate(line):
            if len(p) == 2:
                out.append(WORD_JOINER + "".join(chip(n, by_n.get(n), p[0]) for n in p[1]))
                continue
            i, start, end = p
            seg = segments[i]
            text = str(seg.get("text") or "")
            if pi == 0:
                lead = _LEAD.match(text[start:end])
                if lead:
                    start += len(lead.group(0))
            if not flagged(seg):
                out.append(_piece(seg, i, start, end, quotes[i], ctx))
                continue
            piece = text[start:end]
            a = start + (len(piece) - len(piece.lstrip()))
            b = max(a, end - (len(piece) - len(piece.rstrip())))
            first = i not in seen
            seen.add(i)
            last = last_piece.get(i) == (li, pi)
            out.append(e(text[start:a]))
            if b > a:
                own = f' id="nosource-{i}"' if first else ""
                out.append(f'<span class="wts-nosource"{own} data-seg="{i}">{_piece(seg, i, a, b, quotes[i], ctx)}'
                           + ('<span class="wts-nosource__tag" aria-hidden="true">No source</span>'
                              if last and i == ctx.first_no_source else "")
                           + (f'<span class="wts-vh">{e(SAID_INVALID if seg.get("status") == "invalid" else SAID_NOSOURCE)}'
                              "</span>" if last else "") + "</span>")
            out.append(e(text[b:end]))
        return "".join(out)

    blocks: list[tuple[str, Any]] = []
    items: list[str] | None = None
    for li, line in enumerate(lines):
        plain = "".join("" if len(p) == 2 else str(segments[p[0]].get("text") or "")[p[1]:p[2]] for p in line).strip()
        cites = any(len(p) == 2 for p in line)
        if not plain and not cites:
            items = None
            continue
        if not cites and (re.match(r"^#{1,4}\s", plain) or re.match(r"^\*\*[^*]+\*\*:?$", plain)):
            title = re.sub(r":$", "", re.sub(r"^#+\s*", "", plain).replace("**", "")).strip()
            blocks.append(("h", title))
            items = None
            continue
        if re.match(r"^[-*•]\s", plain):
            if items is None:
                items = []
                blocks.append(("ul", items))
            items.append(inline(line, li))
            continue
        items = None
        blocks.append(("p", inline(line, li)))
    sections: list[tuple[str | None, list[tuple[str, Any]]]] = [(None, [])]
    for kind, body in blocks:
        if kind == "h":
            sections.append((body, []))
        else:
            sections[-1][1].append((kind, body))
    html = []
    for title, body in sections:
        inner = (f"<h2>{e(title)}</h2>" if title else "") + "".join(
            "<ul>" + "".join(f"<li>{it}</li>" for it in b) + "</ul>" if k == "ul" else f"<p>{b}</p>" for k, b in body)
        if title and re.fullmatch(r"in brief", title, re.I):
            html.append(f'<section class="resolved" aria-label="In brief">{inner}</section>')
        else:
            html.append(inner)
    return f'<div class="answer">{"".join(html)}</div>'


# ---------- the strip, and the check details at the end ----------


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _strip_item(shown: int, total: int | None, words: str, problem: bool, first: str | None) -> str:
    return ('<li class="wts-check__item"><span class="wts-check__count">'
            f'<span class="wts-check__glyph" aria-hidden="true">{"!" if problem else "✓"}</span>'
            f'<span class="wts-check__num">{shown}</span>' + (f"<span>of {total}</span>" if total is not None else "")
            + ('<span class="wts-check__badge">To check</span>' if problem else "") + "</span>"
            f"<span>{e(words)}"
            + (f'. <a class="wts-check__first" href="#{e(first)}">Show the first</a>' if problem and first else "")
            + "</span></li>")


def check_strip(answer: Mapping[str, Any]) -> str:
    """The check strip (``CheckStrip``): the three counts in words, under the title that names the record."""
    c = check_counts(answer)  # type: ignore[arg-type]
    f = firsts(answer)
    return ('<section class="wts-check" aria-labelledby="check-title" id="check">'
            '<div class="wts-check__head"><h2 class="wts-check__title" id="check-title">Checked against the council '
            'minutes</h2><a class="wts-check__more" href="#check-details">How it was checked</a></div>'
            '<ul class="wts-check__list">'
            + _strip_item(c.citations_matched, c.citations_total, _plural(c.citations_total, "citation matched to the "
                          "record", "citations matched to the record"), c.citations_matched < c.citations_total,
                          f["invalid"])
            + _strip_item(c.quotes_found, c.quotes_total, _plural(c.quotes_total, "quotation found word for word",
                          "quotations found word for word"), c.quotes_found < c.quotes_total, f["missing"])
            + _strip_item(c.no_source, None, _plural(c.no_source, "sentence without a source",
                          "sentences without a source"), c.no_source > 0, f["nosource"])
            + "</ul></section>")


def check_details(answer: Mapping[str, Any], found: int, briefing: str | None = None) -> str:
    """"How this briefing was checked" (``CheckDetails``): the verifier's own counts, and what each mark means. It
    ends a finished briefing, so it carries the family kit's mark for a briefing read to the end (``briefing_read``,
    once for each ``briefing``; docs/DECISIONS.md, 36)."""
    total, invalid = int(answer.get("citations_total") or 0), int(answer.get("citations_invalid") or 0)
    quotes, missing = int(answer.get("quotes_total") or 0), int(answer.get("quotes_unverified") or 0)
    unsupported = int(answer.get("unsupported_segments") or 0)
    beside = sum(1 for s in answer.get("segments") or [] if s.get("beside"))
    p = _plural
    points = [
        f"The AI was given only the {found} {p(found, 'passage', 'passages')} of minutes found for the question, "
        "listed under Sources, and may use nothing else." if found else None,
        f"Each of the {total} {p(total, 'citation', 'citations')} was checked against the minutes it cites: "
        + (f"{invalid} did not match, so {p(invalid, 'it was', 'they were')} removed, and the words "
           f"{p(invalid, 'it was', 'they were')} attached to are marked “No source”. Check the minutes before relying "
           "on them." if invalid else "all matched."),
        f"Each of the {quotes} {p(quotes, 'quotation', 'quotations')} was looked for word for word in the minutes "
        "cited for it: " + (f"{missing} could not be found and {p(missing, 'is', 'are')} marked “Not found word for "
                            f"word” with a wavy underline. Check the minutes before relying on {p(missing, 'it', 'them')}."
                            if missing else "all were found, and each is marked “✓ word for word”.") if quotes else None,
        f"{unsupported} {p(unsupported, 'sentence', 'sentences')} that no cited source supports "
        f"{p(unsupported, 'is', 'are')} marked with a dotted underline, and the first with “No source”. Short joining "
        "phrases are not counted." if unsupported
        else "No sentence was found without a source. Short joining phrases are not counted.",
        (f"{'A quotation' if beside == 1 else f'{beside} quotations'} found word for word in the minutes cited "
         f"straight after {'it is' if beside == 1 else 'them are'} shown as those minutes’ "
         f"{p(beside, 'quotation', 'quotations')}; the words around {'it keep' if beside == 1 else 'them keep'} their "
         "marks.") if beside else None,
        "Minutes are summaries of each meeting written by council officers, so a quotation is the minutes’ words, not "
        "a councillor’s own.",
        "Some errors can still get through: check the minutes before relying on a point.",
    ]
    return ('<section class="check-details" id="check-details" aria-labelledby="check-details-head" '
            'data-wts-conversion="briefing_read"' + (f' data-wts-briefing="{e(briefing)}"' if briefing else "") + ">"
            '<h2 id="check-details-head">How this briefing was checked</h2><ul>'
            + "".join(f"<li>{e(x)}</li>" for x in points if x)
            + '</ul><p><a href="/methodology#ai-briefings">How every briefing is checked, on the methodology page</a>'
              "</p></section>")


def loaded_notice(answer: Mapping[str, Any]) -> str:
    n = int(answer.get("loaded_words") or 0)
    if n <= 0:
        return ""
    return (f'<p class="notice">{"One word" if n == 1 else f"{n} words"} in the briefing’s own voice may be loaded. '
            "Briefings are meant to report what the minutes record, in neutral words.</p>")


# ---------- the sources ----------


def sources_list(sources: Sequence[Mapping[str, Any]]) -> str:
    """The sources the briefing drew on (``Sources``): numbered as it cites them, grouped as the evidence was
    balanced, each with the people its passage names (with their party on the date) and the passage itself."""
    if not sources:
        return ""
    groups: list[tuple[str, list[Mapping[str, Any]]]] = []
    for s in sources:
        g = next((x for x in groups if x[0] == s.get("group")), None)
        if g is None:
            groups.append((str(s.get("group") or ""), [s]))
        else:
            g[1].append(s)
    heading = "h4" if len(groups) > 1 else "h3"
    parts = ['<section aria-labelledby="sources-heading" class="briefing">'
             f'<h2 id="sources-heading">Sources: the councils’ own minutes ({len(sources)})</h2>']
    for name, items in groups:
        parts.append("<div>" + (f'<h3 class="group-heading">{e(name)}</h3>' if len(groups) > 1 else "")
                     + '<ol class="sources">')
        for s in items:
            kind = str(s.get("kind") or "")
            number = f"{s.get('item_number')} " if s.get("item_number") else ""
            named = s.get("named") or []
            votes = s.get("votes") or []
            parts.append(
                f'<li id="source-{e(s.get("n"))}" class="source {e(kind)}"><span class="source-n">{e(s.get("n"))}</span>'
                f'<div><{heading}><a href="{e(s.get("url") or "")}" rel="noreferrer" data-wts-conversion="source_opened">'
                f'{e(number)}{e(s.get("item_title") or "")}'
                f"</a></{heading}>"
                f'<p class="meta"><a href="/councils/{e(s.get("gss") or "")}">{e(s.get("council_name") or "")}</a>, '
                f'{e(KIND_LABEL.get(kind) or s.get("committee") or "")} ({e(s.get("committee") or "")}), '
                f'{e(long_date(s.get("date")))}</p>'
                + (f'<p class="small named">People in this passage, with their party on the date: '
                   f'{e("; ".join(named))}.</p>' if named else "")
                + f'<details><summary>The passage</summary><blockquote>{e(s.get("text") or "")}</blockquote></details>'
                + ('<p class="small">' + ", ".join(
                    f'<a href="/votes/{e(v.get("vote_id"))}">Named vote{f" {k + 1}" if len(votes) > 1 else ""}: who '
                    "voted which way</a>" for k, v in enumerate(votes)) + "</p>" if votes else "")
                + "</div></li>")
        parts.append("</ol></div>")
    parts.append("</section>")
    return "".join(parts)


def found_words(evidence: Mapping[str, Any] | None, total: int) -> str:
    """What was found, in words, from the search's own figures ("24 records from 11 councils at 18 meetings"), as
    the wait sums it up (``checked.ts``'s ``foundWords``, without the meetings' kinds)."""
    ev = evidence or {}
    records, councils, meetings = ev.get("records"), ev.get("councils"), ev.get("meetings")
    if not records or not councils:
        return f"{total} {_plural(total, 'record', 'records')}"
    kinds = ev.get("kinds") or {}
    authority = any(k in ("board", "mayor", "scrutiny") for k in kinds)
    bodies = _plural(councils, "council or authority", "councils and authorities") if authority \
        else _plural(councils, "council", "councils")
    return (f"{records} {_plural(records, 'record', 'records')} from {councils} {bodies}"
            + (f" at {meetings} {_plural(meetings, 'meeting', 'meetings')}" if meetings else ""))
