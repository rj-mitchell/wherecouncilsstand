"""What a named vote is called on the site: a short label for each vote on an agenda item ("Amendment 7", "Substantive
motion", "Amendment by Cllr Webb"), and the titles, headings and descriptions made from it.

Many agenda items hold more than one named vote (a budget and its amendments), and the item's title alone gave
them all the same title and heading. The label is read as each page is served, from what is already stored: the
words just before the vote in the item's minutes (or, where the minutes can't be found, in the vote's own extract),
and the vote's place among the item's named votes. It is read conservatively: only a pattern that says plainly what
was voted on gives a label ("Amendment 7 – It was MOVED by Cllr G.B. Lyon", "A recorded vote on Councillor Webb's
amendment was taken", "For the substantive motion"); otherwise the vote is called by its place, "Vote 2 of 4 on this
item". Two votes on one item never share a label. Nothing here changes the record.
"""

from __future__ import annotations

import re
from typing import Any

from wts_core.dates import long_date

from councils.parse.votes import HEADING, flatten

MOTION_OR_AMENDMENT = "motion or amendment"
TITLE_MAX = 70            # characters of a page's title before " | Where Councils Stand"
DESCRIPTION_MAX = 155     # characters of a page's description
ITEM_MIN = 20             # the fewest characters of an item's title kept in a vote's page title
CONTEXT = 1500            # how far back before a vote the words that say what it was on are looked for

_NAME = r"(?:[A-Z][\w'’.-]*\s+){0,3}[A-Z][\w'’-]*[a-z][\w'’-]*"
_CLLR = r"(?:Councillor|Cllr\.?)\s+"
_ID = r"(\d{1,2}|[A-H])"
# "Amendment 7", "Amendment No. 3", "Amendment (B)"; not "Amendments 2 and 3" or "(Amendment) Regulations"
_NUMBERED = re.compile(rf"\bAmendment\s+(?:No\.?\s*)?\(?{_ID}\)?(?![\w)])"
                       r"(?!\s*(?:,|and\b|&|or\b|to\b)\s*\(?(?:\d|[A-H]\b))", re.I)
_PAIR = re.compile(rf"\bAmendments\s+{_ID}\s*(?:and|&)\s*{_ID}\b(?!\s*(?:,|and\b|&))", re.I)
_ORDINAL = re.compile(r"\b(first|second|third|fourth|fifth|sixth|seventh|eighth|ninth|tenth)\s+amendment\b", re.I)
_OWNED = re.compile(rf"\b{_CLLR}({_NAME})['’]s?\s+(?:(?:first|second|third|fourth|fifth|revised|further)\s+)?"
                    r"(amendment|motion)\b", re.I)
_NOUN_BY = re.compile(rf"\b(amendment|motion)\s+(?:(?:as\s+)?(?:moved|proposed|submitted|tabled)\s+)?(?:by|in\s+the\s+name\s+of)\s+"
                      rf"{_CLLR}({_NAME})", re.I)
_MOVED = re.compile(rf"\b(?:(?:moved|proposed|submitted|tabled)\s+by|(?:amendment|motion)\s+(?:by|in\s+the\s+name\s+of))"
                    rf"\s+{_CLLR}({_NAME})", re.I)
_SUBSTANTIVE = re.compile(r"\b(substantive|original|amended|budget)\s+motion\b", re.I)
# a motion, an amendment or recommendations, as the subject of a sentence: "the amendment", "this motion", "the
# Recommendations at (i)"; not "Notice of Motion" or "(Amendment) Regulations"
_NOUN = re.compile(r"(?:\b(?:the|this|that|an|a|his|her|their|its|proposed|revised|above|substantive|original|"
                   r"amended|budget)|['’]s)\s+(amendment|motion|recommendations?|resolutions?)\b"
                   r"(?!\s*\)?\s*Regulations)", re.I)
# a sentence giving a vote's result: "the Amendment was DECLARED LOST", "which was defeated", "the motion FELL"; not
# "whether full costings had been carried out"
_OUTCOME_WORDS = re.compile(r"\b(?:was|were|been|being|is|be|declared|duly|therefore|thereby)\s+(?:declared\s+|duly\s+|then\s+)?"
                            r"(?:carried|lost|defeated|agreed|approved|rejected|withdrawn|not\s+carried|not\s+moved)\b"
                            r"(?!\s+(?:out|forward|over|through|on)\b)|\b(?:amendment|motion|recommendations?)\s+fell\b",
                            re.I)
_VOTING = re.compile(r"\b(?:vot\w*|recorded|follows|divided|division)\b", re.I)
# a sentence ends at a full stop after a word, not after an initial ("Cllr G.B. Lyon") or a title ("Cllr. Lyon")
_SENTENCES = re.compile(r"(?:(?<=[A-Za-z]{2}[.;!?])|(?<=[\d)\"”’'][.;!?])|(?<=\s[.;!?]))(?<!\bCllr\.)(?<!\bMr\.)(?<!\bMrs\.)"
                        r"(?<!\bDr\.)(?<!\bNo\.)(?<!\bSt\.)\s+(?=[\"“‘'(]?[A-Z0-9])|\s+[–—-]\s+(?=It\b)")
_NOT_NAME = {"MOVED", "SECONDED", "AND", "THAT", "THE", "WAS", "PROPOSED", "MOTION", "AMENDMENT", "LEADER", "DEPUTY",
             "PORTFOLIO", "CABINET", "MEMBER", "CHAIR", "CHAIRMAN", "MAYOR", "EXECUTIVE", "OF", "ON", "FOR", "IN"}
_QUESTION_LABEL = {"motion": "Motion", "amendment": "Amendment", "recommendation": "Recommendation",
                   "recommendations": "Recommendations", "resolution": "Resolution", "resolutions": "Resolutions",
                   "budget": "Budget", "proposal": "Proposal", "proposals": "Proposals", "report": "Report"}


def before_vote(excerpt: str) -> str:
    """The words in a vote's extract before its first list of names: what the minutes say the vote was on."""
    flat = flatten(excerpt or "")
    if flat.endswith("members)") and " | " in flat:
        return ""                                   # a vote set out as a table: its extract has no words
    head = next((m for m in HEADING.finditer(flat) if m.lastgroup != "none"), None)
    return flat[:head.start()] if head else flat[:200]


def headings(excerpt: str) -> str:
    """A vote's headings, as the reader of votes found them ("For the Motion ... For Amendment 1")."""
    return " ".join(m.group(0) for m in HEADING.finditer(flatten(excerpt or "")))


def minutes_context(minutes: str, excerpts: list[str]) -> list[str | None]:
    """For each named vote on an item, in order, the words before it in the item's whole minutes, from just after
    the vote before it, up to ``CONTEXT`` characters; None where the vote's extract can't be found in them (names
    removed from it since, or the minutes read again), when its own extract is used instead."""
    flat = flatten(minutes or "")
    flat = re.sub(r"\b(For|Against)(?=(?:Amendment|Motion)\b)", r"\1 ", flat)     # as the reader of votes does
    out: list[str | None] = []
    after = 0
    for excerpt in excerpts:
        pre = before_vote(excerpt).rstrip()
        # the longest stretch of the words before the list that has had no name removed from it
        piece = max(pre.split("[name removed]"), key=len).strip() if pre else ""
        at = flat.find(piece, after) if flat and len(piece) >= 30 else -1
        if at < 0 or not pre.endswith(piece):
            out.append(None)
            continue
        start = at + len(piece)                     # where the vote's first list of names begins
        out.append(flat[max(after, start - CONTEXT):start])
        after = start
    return out


def _name(text: str) -> str | None:
    words = []
    for w in text.split():
        if w.strip(".,").upper() in _NOT_NAME:
            break
        words.append(w)
    return " ".join(words) if words and words[-1][-1:].isalpha() and len(words[-1]) > 1 else None


def _specific(s: str, nouns: list[str]) -> tuple[str, str, int] | None:
    """What a sentence says plainly about which motion or amendment: (its kind, the label, how sure: 2 for a number,
    1 for who moved it)."""
    pair = _PAIR.search(s)
    if pair:
        return "amendment", f"Amendments {pair.group(1).upper()} and {pair.group(2).upper()}", 2
    numbered = _NUMBERED.search(s)
    if numbered:
        return "amendment", f"Amendment {numbered.group(1).upper()}", 2
    ordinal = _ORDINAL.search(s)
    if ordinal:
        return "amendment", f"{ordinal.group(1).capitalize()} amendment", 2
    direct = _NOUN_BY.search(s)
    if direct and (who := _name(direct.group(2))):
        kind = direct.group(1).lower()
        return kind, f"{kind.capitalize()} by Cllr {who}", 1
    owned = _OWNED.search(s)
    if owned and (who := _name(owned.group(1))):
        kind = owned.group(2).lower()
        return kind, f"{kind.capitalize()} by Cllr {who}", 1
    moved = _MOVED.search(s)
    kinds = {n.rstrip("s") for n in nouns} | ({"amendment"} if re.search(r"\bamendment\b", s, re.I) else set()) | \
        ({"motion"} if re.search(r"\bmotion\b", s, re.I) else set())
    if moved and len(kinds) == 1 and kinds <= {"amendment", "motion"} and (who := _name(moved.group(1))):
        kind = kinds.pop()                          # "the amendment to the motion moved by": whose? not said plainly
        return kind, f"{kind.capitalize()} by Cllr {who}", 1
    return None


def _kind(noun: str) -> str:
    return noun if noun in ("recommendations", "resolutions") else noun.rstrip("s")


def derive_label(before: str, question: str = "", heads: str = "") -> str | None:
    """What the vote was on, from the words before it, or None where they don't say so plainly.

    The sentences are read backwards from the vote. One of the last three that names a motion, an amendment or
    recommendations says what was voted on ("the amendment was put to the vote"); earlier sentences are then read for
    that amendment's number or who moved it ("Amendment 7 – It was MOVED by Cllr G.B. Lyon"), back to the last
    sentence that gives an earlier vote's result or turns to something else, and no more than ``CONTEXT``
    characters. A number is preferred to a mover, who may have moved several."""
    if question == MOTION_OR_AMENDMENT:
        # a Scottish division: "For the motion ... For Amendment 1"
        n = _NUMBERED.search(heads or "")
        return f"Motion or amendment {n.group(1).upper()}" if n else None
    sentences = [s for s in _SENTENCES.split(flatten(before or "").replace("’", "'")) if s.strip()][::-1]
    if sentences and len(sentences[0].split()) <= 2:
        sentences = sentences[1:]                   # "Those" of "Those Members voting for ..."
    asked = _QUESTION_LABEL.get(question or "")
    noun: str | None = None
    found: tuple[str, str, int] | None = None
    found_at = 0
    read = 0
    for i, s in enumerate(sentences):
        read += len(s)
        if read > CONTEXT:
            break
        last = False
        if i > 0 and _OUTCOME_WORDS.search(s):
            # an earlier vote's result ("...and the Amendment was DECLARED LOST"); but "The motion was CARRIED. The
            # voting was as follows:" is this vote's
            if i == 1 and noun is None and _VOTING.search(sentences[0]):
                last = True
            else:
                break
        nouns = [n.lower() for n in _NOUN.findall(s)]
        spec = _specific(s, nouns)
        sub = _SUBSTANTIVE.search(s)
        if noun is None:
            if sub and (not nouns or _kind(nouns[-1]) == "motion") and not (spec and spec[0] == "amendment"):
                return f"{sub.group(1).capitalize()} motion"
            if spec:
                noun = spec[0]                      # "Amendment 7 – It was MOVED by ..." before the debate on it
            elif nouns and i < 3:
                noun = _kind(nouns[-1])
            elif nouns:
                break                               # far back, and about something else
        elif nouns and any(_kind(n) != noun for n in nouns) and not (spec and spec[0] == noun):
            break                                   # turns to something else: what came before isn't this vote
        if spec and spec[0] == noun and (found is None or spec[2] > found[2]):
            found, found_at = spec, i
            if spec[2] == 2:
                break
        if last or (found and i >= found_at + 2):
            break                                   # a number is looked for only just before who moved it
    label = found[1] if found else _QUESTION_LABEL.get(noun or "")
    # the heading's own word, where it is plain ("For the amendment"), wins over a motion read for an amendment
    if label and asked and {_kind(label.split()[0].lower()), question} <= {"motion", "amendment"} and \
            _kind(label.split()[0].lower()) != question:
        return asked
    return label or asked


# what a vote alone on its item is taken to be on: no need to say so
_PLAIN = {"Motion", "Recommendation", "Recommendations", "Resolution", "Resolutions", "Report", "Budget", "Proposal",
          "Proposals", "Budget motion"}


def item_labels(votes: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """For the named votes on one agenda item (each with ``vote_id`` and the ``label`` read for it, or None), in
    their order in the minutes: each vote's label as shown, its place (``n``) and how many there are (``of``).
    Labels that would be shared are told apart by place; a vote with no label, on an item with others, is
    "Vote 2 of 4 on this item"; a vote alone on its item has none unless it says more than the item's title
    ("Amendment", "Substantive motion", "Amendment by Cllr Webb"; not "Motion" or "Recommendations")."""
    of = len(votes)
    if of == 1 and votes[0].get("label") in _PLAIN:
        votes = [{**votes[0], "label": None}]
    counts: dict[str, int] = {}
    for v in votes:
        if v.get("label"):
            counts[v["label"]] = counts.get(v["label"], 0) + 1
    out = {}
    for n, v in enumerate(votes, 1):
        label = v.get("label")
        if label and counts[label] > 1:
            label = f"{label} (vote {n} of {of})"
        elif not label and of > 1:
            label = f"Vote {n} of {of} on this item"
        out[v["vote_id"]] = {"label": label, "n": n, "of": of, "derived": bool(v.get("label"))}
    return out


# Titles

_ACRONYMS = {"UK", "NHS", "HRA", "CIL", "SEND", "SEN", "LGR", "MTFS", "MTFP", "CCTV", "ASB", "LGA", "HMO", "HMOS", "EV",
             "ICT", "GLA", "COVID", "COVID-19", "VAT", "PFI", "LEP", "LTP", "BCF", "DSG", "CPO", "ULEZ", "LTN", "LTNS",
             "HMRC", "DWP", "MP", "MPS", "MEP", "FOI", "GDPR", "EU", "SME", "SMES", "PCC", "LEA", "MHCLG", "DLUHC",
             "PSPO", "SPD", "CPZ", "TFL", "UKSPF", "S106", "S151", "HS2", "A&E", "CQC", "ICB", "ICS", "LLP", "PLC",
             "CIC", "CEO", "OBE", "MBE", "CBE", "LGBT", "LGBTQ", "LGBTQ+", "BAME", "RAAC", "SFA", "MRP", "CFR",
             "TMSS", "QC", "KC", "CA", "CCA", "MCA", "SYMCA", "WMCA", "GMCA", "WYCA", "LCR", "TVCA", "NECA",
             "PCN", "GP", "GPS", "SUDS", "SSSI", "AONB", "HGV", "RSL", "CPRE", "DBS", "ESFA", "HAF", "SCR",
             "PSED", "EQIA", "EIA", "LDP", "LDF", "LP", "NPPF", "CMA", "BID", "BIDS"}
_ROMAN = re.compile(r"^(?:I{1,3}|IV|V|VI{1,3}|IX|X)$")


def sentence_case(title: str, keep: str = "") -> str:
    """An agenda item written all in capitals, in sentence case: "2026/27 REVENUE BUDGET AND MTFS" -> "2026/27
    revenue budget and MTFS". Acronyms the site knows, words with a digit and the words of ``keep`` (the
    council's name) keep their capitals. A title that isn't in capitals is left as the council wrote it."""
    letters = [c for c in title if c.isalpha()]
    if len(letters) < 6 or sum(c.isupper() for c in letters) < 0.85 * len(letters):
        return title
    kept = {w.lower() for w in re.findall(r"[A-Za-z]+", keep) if len(w) > 2 and w.lower() not in
            ("council", "borough", "district", "county", "city", "metropolitan", "and", "the", "of")}
    out = []
    for word in re.split(r"(\s+|/|-|–|\(|\))", title):
        bare = re.sub(r"[^\w&+-]", "", word)
        if not bare or bare.upper() in _ACRONYMS or _ROMAN.match(bare) or re.search(r"\d", bare) or \
                not re.search(r"[AEIOUY]", bare.upper()) and len(bare) > 1:
            out.append(word)
        elif bare.lower() in kept:
            out.append(word[:1].upper() + word[1:].lower())
        else:
            out.append(word.lower())
    text = "".join(out)
    first = re.search(r"[a-z]", text)
    if first and not re.search(r"[A-Z]", text[:first.start()]):
        text = text[:first.start()] + text[first.start()].upper() + text[first.start() + 1:]
    return text


_DANGLING = {"and", "or", "of", "the", "to", "for", "&", "in", "on", "a", "an", "with", "at", "by", "from"}


def shorten(text: str, limit: int, end: str = "…") -> str:
    """``text`` cut at a word boundary to at most ``limit`` characters, with ``end`` where it was cut."""
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    cut = text[:limit - len(end) + 1]
    space = cut.rfind(" ")
    cut = cut[:space] if space > limit * 0.5 else cut[:limit - len(end)]
    words = cut.rstrip(" ,;:–-").split(" ")
    while len(words) > 1 and words[-1].lower() in _DANGLING:      # "Budget 2026/27 and…" -> "Budget 2026/27…"
        words.pop()
    return " ".join(words).rstrip(" ,;:–-") + end


_MINUTES_ONLY = re.compile(r"^(?:\d+\.?\s*)?(?:the\s+)?minutes?(?:\s+of\s+(?:the\s+)?(?:previous\s+|last\s+)?meeting)?"
                           r"[\s.:]*$", re.I)
BUDGET = re.compile(r"\b(?:budgets?|council\s+tax|precepts?)\b", re.I)


def item_name(v: dict[str, Any], keep: str = "") -> str:
    """An item's title as a page names it: in sentence case, and not "Minutes" (the whole meeting's minutes held as
    one item), for which the meeting is named instead."""
    item = (v.get("item") or "").strip()
    if not item or _MINUTES_ONLY.match(item):
        return {"council": "Full council meeting", "cabinet": "Cabinet meeting", "policy": "Policy committee meeting",
                "board": "Board meeting", "mayor": "Mayor’s decisions", "scrutiny": "Overview and scrutiny meeting"
                }.get(v.get("kind", ""), "Meeting")
    return sentence_case(item, keep)


def is_budget(v: dict[str, Any]) -> bool:
    """A vote on a budget, council tax or a precept, by its item's title."""
    return bool(BUDGET.search(v.get("item") or ""))


def short_date(iso: str | None) -> str:
    d = long_date(iso) if iso else ""
    parts = d.split()
    return f"{parts[0]} {parts[1][:3]} {parts[2]}" if len(parts) == 3 else d


def outcome(v: dict[str, Any]) -> str:
    """The vote's result as the minutes give it ("carried", "lost"), or "" where it isn't given or doesn't agree with
    the count (a result read from the sentence about another vote)."""
    c = v.get("counts") or {}
    said = v.get("outcome") or ""
    if v.get("partial") or v.get("question") == MOTION_OR_AMENDMENT:
        return said
    if said == "carried" and c.get("for", 0) < c.get("against", 0) or \
            said == "lost" and c.get("for", 0) > c.get("against", 0):
        return ""
    return said


def tally(v: dict[str, Any]) -> str:
    """"lost 10–19"; "motion 30, amendment 25" for a Scottish division; the result alone where only one side could
    be read."""
    c = v.get("counts") or {}
    outcome_ = outcome(v)
    if v.get("partial"):
        return outcome_
    if v.get("question") == MOTION_OR_AMENDMENT:
        return f"motion {c.get('for', 0)}, amendment {c.get('against', 0)}"
    return f"{outcome_} {c.get('for', 0)}–{c.get('against', 0)}" if outcome_ else \
        f"{c.get('for', 0)} for, {c.get('against', 0)} against"


def heading(v: dict[str, Any], keep: str = "") -> str:
    """The vote's heading on its own page and its link text elsewhere: "Amendment 7: General Fund Budget 2026/27"."""
    item = item_name(v, keep)
    return f"{v['label']}: {item}" if v.get("label") else item


def title(v: dict[str, Any], council: str, short: str) -> str:
    """A vote's page title (before the site's name), at most about ``TITLE_MAX`` characters: what the vote was on,
    its result, the item, the council and the date. "Amendment 7, lost 10–19: General Fund Budget… – Rushmoor, 26 Feb
    2026"; a budget item's single vote, "How councillors voted: Council tax 2020/21 – Blackpool, 27 Feb 2020". The
    council's full name is used where it fits, and the item's title is cut at a word where nothing else fits."""
    label = (v.get("label") or "").replace(" on this item", "")
    item = item_name(v, council)
    result = tally(v)
    if label:
        head = f"{label}, {result}: " if result else f"{label}: "
        tail = ""
    elif is_budget(v):
        head = "How councillors voted: "      # what someone looking for a council's budget or council tax searches
        tail = ""
    else:
        head = ""
        tail = f": {result}" if result else ""
    when = short_date(v.get("date"))
    for name in dict.fromkeys((council, short)):
        end = f" – {name}, {when}" if when else f" – {name}"
        room = TITLE_MAX - len(head) - len(tail) - len(end)
        if len(item) <= room:
            return f"{head}{item}{tail}{end}"
        if room >= ITEM_MIN or name == short:
            return f"{head}{shorten(item, max(room, ITEM_MIN))}{tail}{end}"
    return f"{head}{item}{tail}"


KIND_WORDS = {"council": "full council", "cabinet": "cabinet", "policy": "policy committee", "board": "board",
              "mayor": "mayor’s decisions", "scrutiny": "overview and scrutiny"}


def description(v: dict[str, Any], council: str) -> str:
    """A vote's page description, at most ``DESCRIPTION_MAX`` characters: the label and the count first, then the
    council, the meeting, the date and the item."""
    c = v.get("counts") or {}
    said = outcome(v)
    if v.get("partial"):
        result = f"{said.capitalize()}; only one side could be read" if said else "Only one side could be read"
    elif v.get("question") == MOTION_OR_AMENDMENT:
        result = (f"{c.get('for', 0)} for the motion, {c.get('against', 0)} for the amendment, "
                  f"{c.get('abstain', 0)} abstained")
    else:
        result = (f"{said.capitalize() + ', ' if said else ''}{c.get('for', 0)} for, {c.get('against', 0)} against, "
                  f"{c.get('abstain', 0)} abstained")
    if v.get("label"):
        result = f"{v['label']}: {result[0].lower() + result[1:]}"
    meeting = KIND_WORDS.get(v.get("kind", ""), (v.get("committee") or "a meeting"))
    text = (f"{result}. {council}, {meeting}, {long_date(v.get('date'))}: {item_name(v, council)}. Each "
            "councillor’s party on the date.")
    return shorten(text, DESCRIPTION_MAX)
