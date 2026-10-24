"""Named (recorded) votes from minutes text.

Minutes record a named vote as a heading for each side followed by a list of names:

    In favour of the Motion: Councillors P Birkinshaw, Carr, Felton and Smith.
    Against the Motion: The Mayor (Councillor Markham), and Councillors Barnard, D Birkinshaw ...
    Abstentions: Councillor Lodge.

Each name is matched to the meeting's attendance, by surname, and by initial and surname where two members share a
surname. "The Mayor" or "The Chair" is the member recorded in that role. A name that matches no one, or more than one
member, is kept with an empty member id, so the vote can still be shown as the minutes give it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_OBJ = r"(?:original |substantive |amended |revised |above )?(?:motion|amendment|recommendations?|resolution|budget|proposals?|report|substantive motion|item)"
_TRAIL = rf"(?:\s+(?:the|this|that)\s+{_OBJ})?(?:\s+as amended)?(?:,?\s+(?:being\s+)?present at the time of (?:the )?vot(?:e|ing))?(?:\s+were)?"
_COUNT = r"(?:\s*\(\s*\d+\s*\))?(?:\s*-?\s*\d+\s*(?:members|councillors|votes)?)?"
SIDES = {
    "for": rf"(?:(?:those|members|councillors)\s+(?:voting\s+|who\s+voted\s+)?)?(?:voted\s+)?(?:in\s+favour(?:\s+of)?|for){_TRAIL}{_COUNT}",
    "against": rf"(?:(?:those|members|councillors)\s+(?:voting\s+|who\s+voted\s+)?)?(?:voted\s+)?against{_TRAIL}{_COUNT}",
    "abstain": rf"(?:(?:those|members|councillors)\s+(?:who\s+)?)?(?:abstentions?|abstained|abstaining|abstain|abstained from voting){_TRAIL}{_COUNT}",
}
HEADING = re.compile(
    "|".join(rf"(?P<{side}>(?<![\w-]){pattern}\s*(?::-|:|–|—|-)\s*)" for side, pattern in SIDES.items()),
    re.I,
)
# Where a list of names ends: the end of a sentence followed by something that isn't a name.
_STOP = re.compile(
    r"(?:\.\s+|\s+)(?=(?:upon|on being|the (?:motion|amendment|original|substantive|recommendations?|mayor declared|chair declared)"
    r"|resolved|it was|accordingly|there (?:were|was)|therefore|this was|having|following|in accordance|councillor \w+ (?:then|moved|asked|requested)"
    r"|a recorded vote|a named vote|\(\w\)\s|\d+\.\s))",
    re.I,
)
_OUTCOME = re.compile(r"\b(carried|lost|defeated|fell|was not carried|not carried|agreed|approved|rejected)\b", re.I)
_HONOURS = re.compile(r"\b(?:BEM|OBE|MBE|CBE|JP|DL|KC|QC|MP|MSc|BSc|BA|MA|PhD|FRSA|Dr|Mr|Mrs|Ms|Miss|Cllr|Cllrs|"
                      r"Councillors?|Sir|Dame|Rev|Revd|Prof)\b\.?", re.I)
_ROLE = re.compile(r"\bthe\s+(?:(?:civic|lord|deputy)\s+)?(mayor|chair(?:man|woman|person)?|presiding member|vice[- ]chair)\b", re.I)
_NONE = re.compile(r"^(?:none|nil|no members?|no councillors?|0|-)$", re.I)


@dataclass(frozen=True)
class Member:
    member_id: str
    name: str          # as the attendance records it: "Councillor Dave Leech"
    role: str          # "Mayor", "Chair", "Committee Member"


@dataclass(frozen=True)
class Vote:
    block: int         # which named vote in the text (0, 1, ...)
    side: str          # "for", "against", "abstain"
    name: str          # as written in the minutes
    member_id: str     # "" if not matched
    outcome: str       # "carried", "lost" or ""
    question: str      # "motion", "amendment", ... where the heading says
    excerpt: str


def flatten(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("’", "'")).strip()


def _surname_keys(name: str) -> tuple[str, str]:
    """("leech", "d leech") for "Councillor Dave Leech"."""
    words = [w for w in re.sub(r"[^\w' -]", " ", _HONOURS.sub(" ", name)).split() if w]
    if not words:
        return "", ""
    surname = words[-1].lower()
    first = words[0][0].lower() if len(words) > 1 else ""
    return surname, f"{first} {surname}".strip()


class Matcher:
    def __init__(self, members: list[Member]):
        self.members = members
        self.by_surname: dict[str, list[Member]] = {}
        self.by_initial: dict[str, list[Member]] = {}
        self.by_full: dict[str, Member] = {}
        for m in members:
            s, i = _surname_keys(m.name)
            self.by_surname.setdefault(s, []).append(m)
            self.by_initial.setdefault(i, []).append(m)
            full = " ".join(_HONOURS.sub(" ", m.name).split()).lower()
            self.by_full[full] = m
            # double-barrelled or two-word surnames: "Lowe-Flello", "Ann de Vere" -> also index the last two words
            words = full.split()
            if len(words) >= 3:
                self.by_surname.setdefault(" ".join(words[-2:]), []).append(m)

    def match(self, written: str) -> str:
        w = written.strip()
        role = _ROLE.search(w)
        inner = re.search(r"\(([^)]*)\)", w)
        if inner and re.search(r"[A-Z]", inner.group(1)):
            w = inner.group(1)                      # "The Mayor (Councillor Markham)" -> "Councillor Markham"
        elif role:
            want = role.group(1).lower()[:5]
            hits = [m for m in self.members if m.role.lower().startswith(want)]
            return hits[0].member_id if len(hits) == 1 else ""
        clean = " ".join(_HONOURS.sub(" ", w).split()).lower()
        if clean in self.by_full:
            return self.by_full[clean].member_id
        words = clean.split()
        if not words:
            return ""
        surname = words[-1]
        two = " ".join(words[-2:])
        if len(words) >= 2 and two in self.by_surname and len(self.by_surname[two]) == 1:
            return self.by_surname[two][0].member_id
        if len(words) >= 2 and len(words[0]) <= 2:  # "P Birkinshaw", "A. Cave"
            hits = self.by_initial.get(f"{words[0][0]} {surname}", [])
            if len(hits) == 1:
                return hits[0].member_id
        if len(words) >= 2:  # "Peter Birkinshaw"
            hits = [m for m in self.by_surname.get(surname, []) if _surname_keys(m.name)[1] == f"{words[0][0]} {surname}"]
            if len(hits) == 1:
                return hits[0].member_id
        hits = self.by_surname.get(surname, [])
        return hits[0].member_id if len(hits) == 1 else ""


def split_names(segment: str) -> list[str]:
    """"The Mayor (Councillor Markham), and Councillors Barnard, D Birkinshaw and Smith." -> names."""
    s = segment.strip().rstrip(".;")
    s = re.sub(r"\bcouncillors?\b|\bcllrs?\b\.?", "", s, flags=re.I)
    parts = re.split(r",|;|\band\b|&", s)
    names = []
    for p in parts:
        p = p.strip(" .:-–")
        if not p or _NONE.match(p):
            continue
        if len(p) > 60 or not re.search(r"[A-Za-z]", p) or re.search(r"\d", p) or len(p.split()) > 5:
            continue
        names.append(p)
    # "The Mayor (Councillor Markham)" splits inside the brackets only if they held a comma; rejoin unbalanced brackets
    out: list[str] = []
    for n in names:
        if out and out[-1].count("(") > out[-1].count(")"):
            out[-1] = f"{out[-1]}, {n}"
        else:
            out.append(n)
    return out


def _question(heading: str) -> str:
    m = re.search(_OBJ, heading, re.I)
    return m.group(0).lower().split()[-1] if m else ""


def _outcome(text: str) -> str:
    m = _OUTCOME.search(text)
    if not m:
        return ""
    return "lost" if m.group(1).lower() in ("lost", "defeated", "fell", "was not carried", "not carried",
                                            "rejected") else "carried"


def parse(text: str, members: list[Member]) -> list[Vote]:
    """Every named vote in one agenda item's minutes."""
    flat = flatten(text)
    heads = list(HEADING.finditer(flat))
    if not heads:
        return []
    # Each heading's list of names, then the headings grouped into votes: a side named again starts a new vote.
    sides = []
    for n, h in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(flat)
        segment = flat[h.end():end]
        stop = _STOP.search(segment)
        names_end = h.end() + (stop.start() if stop else len(segment))
        names = split_names(flat[h.end():names_end])
        if h.lastgroup == "for" and not names:
            continue                     # "for" used in passing, with no names after it
        sides.append((h, names, names_end))
    blocks: list[list[tuple]] = []
    for entry in sides:
        if not blocks or entry[0].lastgroup in {e[0].lastgroup for e in blocks[-1]}:
            blocks.append([])
        blocks[-1].append(entry)

    matcher = Matcher(members)
    out: list[Vote] = []
    for b, entries in enumerate(blocks):
        start = entries[0][0].start()
        names_end = entries[-1][2]
        prev_end = blocks[b - 1][-1][2] if b else 0
        next_start = blocks[b + 1][0][0].start() if b + 1 < len(blocks) else len(flat)
        # The result is usually given straight after the names, otherwise just before the vote.
        outcome = _outcome(flat[names_end:min(next_start, names_end + 300)]) or \
            _outcome(flat[max(prev_end, start - 300):start])
        excerpt = flat[max(prev_end, start - 200):min(next_start, names_end + 150)][:1500]
        question = next((q for q in (_question(e[0].group(0)) for e in entries) if q), "")
        for h, names, _ in entries:
            for name in names:
                out.append(Vote(b, h.lastgroup or "", name, matcher.match(name), outcome, question, excerpt))
    return out
