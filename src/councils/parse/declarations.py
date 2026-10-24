"""Declarations of interest made at a meeting, from its minutes.

Typical forms:

    Councillors Leech and Osborne both declared a non-pecuniary interest in minute number 159 due to their positions
    on the board of Berneslai Homes.
    Councillor Smith declared a disclosable pecuniary interest in item 6 as ... and left the meeting.
    Councillor A Jones - Item 7 - personal interest as a member of ...

Only councillors' own declarations are read. What the interest is stays in the excerpt, as the minutes give it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from councils.parse.votes import Matcher, Member, flatten, split_names

_KIND = (r"(?:disclosable pecuniary|other registrable|non[- ]registrable|non[- ]pecuniary|pecuniary|personal and "
         r"prejudicial|prejudicial|personal|significant|registrable|declarable|private|other)")
DECLARED = re.compile(
    rf"(?P<who>(?:the (?:mayor|chair(?:man)?)\s*\(?)?(?:councillors?|cllrs?\.?)\s+[^.;]{{1,200}}?)\s+"
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
            for name in split_names(re.sub(r"^the (?:mayor|chair(?:man)?)\s*\(?", "", m.group("who"), flags=re.I)):
                if re.search(r"\d", name) or len(name.split()) > 4:
                    continue
                key = (name.lower(), m.start())
                if key in seen:
                    continue
                seen.add(key)
                out.append(Declaration(name, matcher.match(name), kind, excerpt))
    return out
