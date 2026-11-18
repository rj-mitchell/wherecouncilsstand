"""Declarations of interest made at a meeting, from its minutes.

Typical forms:

    Councillors Leech and Osborne both declared a non-pecuniary interest in minute number 159 due to their positions
    on the board of Berneslai Homes.
    Councillor Smith declared a disclosable pecuniary interest in item 6 as ... and left the meeting.
    Councillor A Jones - Item 7 - personal interest as a member of ...

Only councillors' own declarations are read. What the interest is stays in the excerpt in the store, as the minutes
give it, and is never shown or searched.

``without_reasons`` is what the search index, the site's pages and the model are given instead: each declaration cut
down to who declared, the item and the kind of interest ("Councillor Smith declared a personal interest in item 6."),
with the reason left out. Reasons often describe a councillor's family, and sometimes their health, a disability or
the care a relative receives (docs/PILOT.md, "Declarations of interest"). The reader follows the link to the council's
own minutes for the rest.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from councils.parse.votes import Matcher, Member, flatten, split_names

_KIND = (r"(?:disclosable pecuniary|other registrable|non[- ]registrable|non[- ]pecuniary|pecuniary|personal and "
         r"prejudicial|prejudicial|personal|significant|registrable|declarable|private|other)")
DECLARED = re.compile(
    rf"(?P<who>(?:the (?:mayor|chair(?:man)?)\s*\(?)?(?:councillors?|cllrs?\.?)\s+[^.;]{{1,200}}?"
    # Shetland names its councillors by title: "Mr G Smith, Mr T Smith and Ms Macdonald declared an interest"
    # (not one inside "Councillor Mrs Scott", read by the line above)
    rf"|(?<!councillor )(?<!councillors )(?<!cllr )(?<!cllr\. )(?-i:\b(?:Mr|Mrs|Ms|Miss|Dr))\.?\s+(?-i:[A-Z])"
    # and not across a "Councillor": "... to Mr Stewart Councillor Andrew McGuire declared" is the councillor's
    rf"(?:(?!\bcouncill?ors?\b|\bcllrs?\b)[^.;]){{0,200}}?)\s+"
    rf"(?:(?:both|each|all)\s+)?(?:declared|declare|disclosed|reported|made a declaration of)\s+(?:an?\s+|their\s+|his\s+|her\s+)?"
    rf"(?P<kind>{_KIND}(?:\s+(?:and|or)\s+{_KIND})?)?\s*(?:interests?|declarations?)",
    re.I,
)
DASHED = re.compile(
    rf"(?P<who>(?:councillor|cllr\.?)\s+[A-Z][\w.' -]{{1,40}}?)\s*[-–:]\s*(?:item|minute|agenda item)?\s*[\w.()]*\s*[-–:]\s*"
    rf"(?P<kind>{_KIND})\s+interest",
    re.I,
)
NONE_DECLARED = re.compile(r"\b(?:there were )?no declarations? of (?:any )?interests?\b|\bno (?:interests|declarations) were\b",
                           re.I)


# A declaration that says what it is without the word "interest": "Councillor Tam declared that her son ..."
DECLARED_THAT = re.compile(
    r"(?P<who>(?:the (?:mayor|chair(?:man)?)\s*\(?)?(?:councillors?|cllrs?\.?)\s+[^.;]{1,200}?)\s+"
    r"(?:declared|disclosed)\s+(?:to the (?:meeting|committee|council|cabinet)\s+)?that\b",
    re.I,
)
# An agenda item that is the declarations themselves: "Declarations of Interest", "Disclosures of Pecuniary and
# Other Interests", "Apologies for absence and declarations of members' interests"
DECLARATIONS_ITEM = re.compile(r"\b(?:declarations?|disclosures?)\b(?:\s+\S+){0,5}?\s+interests?\b|"
                               r"\binterests?\b(?:\s+\S+){0,2}?\s+(?:declared|disclosed)\b", re.I)
_ITEM_REF = re.compile(r"(?:\b(?:in|on|to|regarding|relating to|in respect of|under|at)\s+|[-–:]\s*)(?:agenda\s+)?"
                       r"(?P<what>item|minute)s?\s*(?:no\.?|number|ref\.?)?\s*(?P<ref>\d+[\w.()]*"
                       r"(?:\s*(?:,|and|&)\s*\d+[\w.()]*)*)", re.I)
# What a sentence straight after a declaration often goes on to say about the councillor's circumstances
_PERSONAL = re.compile(r"\b(?:family|relative|relation|mother|father|son|daughter|husband|wife|partner|spouse|child|"
                       r"children|grand\w*|brother|sister|parent|in-law|nephew|niece|aunt|uncle|cousin|carer|cares?|"
                       r"cared|caring|disab\w*|health|medical|ill|illness|condition|hospital|dementia|cancer|patient|"
                       r"treatment|diagnos\w*|pregnan\w*|bereave\w*|died|death|funeral|benefit|grant|tenant|lives)\b",
                       re.I)
_TERMINAL = re.compile(r"[.!?](?=\s|$)|\n")


@dataclass(frozen=True)
class Declaration:
    name: str
    member_id: str
    interest: str
    excerpt: str


def parse(text: str, members: list[Member]) -> list[Declaration]:
    flat = flatten(text)
    if not flat:
        return []
    matcher = Matcher(members)
    out = []
    seen = set()
    for rx in (DECLARED, DASHED):
        for m in rx.finditer(flat):
            start = flat.rfind(". ", 0, m.start()) + 1
            end = flat.find(". ", m.end())
            excerpt = flat[start:end + 1 if end > 0 else len(flat)].strip()[:600]
            kind = re.sub(r"\s+", " ", (m.group("kind") or "").lower()).replace("non pecuniary", "non-pecuniary")
            titled = not re.match(r"(?:the |councill?ors?\b|cllrs?\b)", m.group("who"), re.I)
            for name in split_names(re.sub(r"^the (?:mayor|chair(?:man)?)\s*\(?", "", m.group("who"), flags=re.I)):
                if re.search(r"\d", name) or len(name.split()) > 4:
                    continue
                if titled and not matcher.match(name):
                    continue          # "Mr X" may be an officer: only a councillor at the meeting is read
                key = (name.lower(), m.start())
                if key in seen:
                    continue
                seen.add(key)
                out.append(Declaration(name, matcher.match(name), kind, excerpt))
    return out


def _who(who: str) -> str:
    """The councillors a declaration names, written plainly: "Councillor Smith", "Councillors Leech and Osborne";
    anything else said before "declared" (the reason, often) is left out."""
    names = [n for n in split_names(re.sub(r"^the (?:mayor|chair(?:man)?)\s*\(?", "", flatten(who), flags=re.I))
             if not re.search(r"\d", n) and len(n.split()) <= 4]
    if not names:
        return "A councillor"
    titled = re.match(r"(?:Mr|Mrs|Ms|Miss|Mx|Dr)\b", names[0])
    if titled:
        return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]
    if len(names) == 1:
        return f"Councillor {names[0]}"
    return "Councillors " + ", ".join(names[:-1]) + " and " + names[-1]


def _reduced(m: re.Match, sentence: str) -> str:
    """One declaration as the site gives it: who, the item and the kind of interest."""
    kind = re.sub(r"\s+", " ", (m.groupdict().get("kind") or "").lower()).replace("non pecuniary", "non-pecuniary")
    article = "an" if not kind or kind[0] in "aeiou" else "a"
    ref = _ITEM_REF.search(sentence)
    where = f" in {ref.group('what').lower()} {ref.group('ref').strip().rstrip('.')}" if ref else ""
    left = re.search(r"\b(?:left|withdrew from|leaving|withdrawing from) the (meeting|room|chamber)\b", sentence, re.I)
    left_too = f" and left the {left.group(1).lower()}" if left else ""
    return f"{_who(m.group('who'))} declared {article} {kind + ' ' if kind else ''}interest{where}{left_too}."


def _sentence(text: str, start: int, end: int) -> tuple[int, int]:
    """The bounds of the sentence (or line) around text[start:end]."""
    before = [x.end() for x in _TERMINAL.finditer(text, 0, start)]
    a = before[-1] if before else 0
    after = _TERMINAL.search(text, end)
    b = after.end() if after else len(text)
    # a sentence the PDF wrapped onto the next line goes on in lower case: it is part of the same sentence
    while b < len(text) and text[b - 1] == "\n" and re.match(r"[ \t]*[a-z(]", text[b:]):
        nxt = _TERMINAL.search(text, b)
        b = nxt.end() if nxt else len(text)
    return a, b


def without_reasons(text: str, title: str = "") -> str:
    """The minutes text with each declaration of interest cut down to who declared, the item and the kind of
    interest. A sentence straight after one that says more about the councillor's circumstances (family, health,
    care) is left out too. An item that is the declarations themselves keeps only the cut-down declarations (or
    that none were made), since what else it says is mostly the reasons. Applying it twice changes nothing more."""
    if not text:
        return text
    plain = text.replace("\u2019", "'")         # same length, so the positions found in it hold in ``text``
    found: list[tuple[int, int, str]] = []
    for rx in (DECLARED, DASHED, DECLARED_THAT):
        for m in rx.finditer(plain):
            a, b = _sentence(plain, m.start(), m.end())
            if any(x < b and a < y for x, y, _ in found):
                continue
            found.append((a, b, _reduced(m, plain[a:b])))
    found.sort()
    if title and DECLARATIONS_ITEM.search(title):
        if found:
            return "\n".join(r for _, _, r in found)
        return "There were no declarations of interest." if NONE_DECLARED.search(plain) else ""
    if not found:
        return text
    out, last = [], 0
    for a, b, reduced in found:
        if a < last:
            continue
        out += [text[last:a], (" " if a and not text[a - 1].isspace() else "") + reduced]
        last = b
        # what the next sentence says about the councillor's circumstances goes with the reason
        nxt = _sentence(plain, last, last)
        if re.match(r"\s*(?:she|he|they|her|his|their|this|the councillor|the member)\b", plain[last:nxt[1]], re.I) \
                and _PERSONAL.search(plain[last:nxt[1]]):
            last = nxt[1]
        if text[last - 1:last] == "\n":
            out.append("\n")
    out.append(text[last:])
    return "".join(out)
