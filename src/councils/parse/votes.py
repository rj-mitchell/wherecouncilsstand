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

_OBJ = r"(?:original |substantive |amended |revised |above )?(?:motion|amendment|recommendations?|resolutions?|budget|proposals?|report|substantive motion|item)"
_TRAIL = rf"(?:\s+(?:on\s+|from\s+)?(?:the|this|that)\s+{_OBJ}(?:\s+(?:to|for|on|relating to|in respect of)\s[^:;.()]{{1,90}}?(?=\s*:))?)?(?:\s+as amended)?(?:\s+below)?(?:,?\s+(?:being\s+)?present at the time of (?:the )?vot(?:e|ing))?(?:\s+were)?"
_COUNT = r"(?:\s*\(\s*\d+\s*\))?(?:\s*-?\s*\d+\s*(?:members|councillors|votes)?)?"
SIDES = {
    "for": rf"(?:(?:those|members|councillors)\s+(?:voting\s+|who\s+voted\s+)?)?(?:voted\s+)?(?:in\s+favour(?:\s+of)?|for){_TRAIL}{_COUNT}",
    "against": rf"(?:(?:those|members|councillors)\s+(?:voting\s+|who\s+voted\s+)?)?(?:voted\s+)?(?:against|againt){_TRAIL}{_COUNT}",
    "abstain": rf"(?:(?:those|members|councillors)\s+(?:who\s+|voting\s+to\s+)?)?(?:abstentions?|abtentions?|absentions?|abstained|abstaining|abstain|abstained from voting){_TRAIL}{_COUNT}",
}
HEADING = re.compile(
    # a heading ends with a colon or dash, or runs straight into "Councillors ..."
    "|".join(rf"(?P<{side}>(?<![\w-]){pattern}(?:\s*(?::-|:|–|—|-)\s*|\s+(?=councillors?\b)|(?<=\))\s*\.?\s+))"
             for side, pattern in SIDES.items()),
    re.I,
)
# Where a list of names ends: the end of a sentence followed by something that isn't a name.
_STOP = re.compile(
    r"\.\s+(?=\()|(?:\.\s+|\s+)(?=(?:upon|on being|the (?:motion|amendment|original|substantive|recommendations?|mayor declared|chair declared)"
    r"|resolved|it was|accordingly|there (?:were|was)|therefore|this was|having|following|in accordance|councillor \w+ (?:then|moved|asked|requested)"
    r"|the (?:vote|result|following|council|meeting|lord mayor|chair(?:man)?|leader|amended|recommendations)\b|one abstention|decisions?:"
    r"|a recorded vote|a named vote|\(\w\)\s|\d+\.\s))",
    re.I,
)
_OUTCOME = re.compile(r"\b(carried|lost|defeated|fell|was not carried|not carried|agreed|approved|rejected)\b", re.I)
_HONOURS = re.compile(r"\b(?:BEM|OBE|MBE|CBE|JP|DL|KC|QC|MP|MSc|BSc|BA|MA|PhD|FRSA|Dr|Mr|Mrs|Ms|Miss|Cllr|Cllrs|"
                      r"Councillors?|Cynghorydd|Cynghorwyr|Sir|Dame|Rev|Revd|Prof)\b\.?", re.I)
_ROLE = re.compile(r"\bthe\s+(?:(?:civic|lord|deputy)\s+)?(mayor|chair(?:man|woman|person)?|presiding member|vice[- ]chair)\b", re.I)
_NONE = re.compile(r"^(?:none|nil|no members?|no councillors?|0|-)$", re.I)
_ANNOUNCED = re.compile(r"recorded vote|named vote|roll[- ]call|recorded as follows|voting (?:was|were) as follows|"
                        r"votes? (?:was|were) (?:cast|recorded) as follows|voted as follows", re.I)
_PARTICLES = {"de", "da", "van", "von", "der", "le", "la", "du", "di", "del", "st", "o", "mc", "mac"}


def looks_like_name(text: str) -> bool:
    """"P Birkinshaw", "Andrews BEM", "The Mayor (Councillor Markham)", not "Voluntary Controlled nursery schools"."""
    words = re.sub(r"[()]", " ", text).replace("'", "").split()
    if not words or len(words) > 5:
        return False
    if words[-1].lower() in _NOT_NAME_ENDINGS:
        return False
    return all(w[0].isupper() or w.lower() in _PARTICLES or w.lower() in ("the", "councillor", "cllr")
               for w in words)


_NOT_NAME_ENDINGS = {"the", "one", "members", "councillors", "following", "under", "resolved", "motion", "amendment",
                     "a", "an", "of", "to", "and", "votes", "vote"}


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
            hits = [m for m in self.members if re.sub(r"^the\s+", "", m.role.lower()).startswith(want)]
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


def _unrun(part: str) -> list[str]:
    """Names set out in columns lose their separators: "Bagshaw Mann P Innes Mannion-Brunt" -> one name per surname,
    keeping a single initial with the surname after it."""
    words = part.split()
    out, i = [], 0
    while i < len(words):
        if len(words[i].rstrip(".")) == 1 and i + 1 < len(words):
            out.append(f"{words[i].rstrip('.')} {words[i + 1]}")
            i += 2
        else:
            out.append(words[i])
            i += 1
    return out


def split_names(segment: str) -> list[str]:
    """"The Mayor (Councillor Markham), and Councillors Barnard, D Birkinshaw and Smith." -> names."""
    s = re.sub(r"\(\s*\d+\s*(?:votes?|members?)?\s*\)", " ", segment)
    s = re.sub(r"^\s*\d+\s*(?:votes?)?\s*(?::-|:|-|–|as follows;?-?)\s*", " ", s)      # "FOR: 40:- Bawn, ..."
    s = s.replace("?", " ").strip().rstrip(".;")                                            # ticks lost as "?"
    if len(re.findall(r"\bcouncillor\b", s, re.I)) >= 2 and len(re.findall(r",|;|\band\b", s)) < \
            len(re.findall(r"\bcouncillor\b", s, re.I)) - 1:
        # "Councillor Tim Anderson Councillor Jon Askew ...": each "Councillor" starts a name
        s = re.sub(r"\b(?:the (?:deputy )?mayor|the (?:vice[- ])?chair(?:man)?),?\s*(?=councillor)", "", s, flags=re.I)
        s = re.sub(r"\bcouncillor\b", ",", s, flags=re.I)
    s = re.sub(r"\bcouncillors?\b:?|\bcllrs?\b\.?", "", s, flags=re.I)
    parts = re.split(r",|;|\band\b|&", s)
    if len(parts) == 1 and len(parts[0].split()) > 4 and all(w[0].isupper() for w in parts[0].split()):
        parts = _unrun(parts[0])
    names = []
    for p in parts:
        p = p.strip(" .:-–")
        if not p or _NONE.match(p):
            continue
        if len(p) > 60 or not re.search(r"[A-Za-z]", p) or re.search(r"\d", p) or not looks_like_name(p):
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


# "For the proposal 4 votes (namely, Councillors Fojtik, Fradgley and Moorse)"; "Against the resolutions None"
NAMELY = re.compile(
    r"(?P<side>for|in favour|against|abstentions?|abstained)(?:\s+(?:the|this)\s+\w+)?\s+(?:(?:\d+|one|two|three)\s+votes?\s*"
    r"\((?:namely,?\s*)?(?P<names>[^()]*(?:\([^()]*\)[^()]*)*)\)|(?P<none>none|nil)\b)",
    re.I,
)
# "(Councillors K Barton, I J Bastable ... voting in favour and Councillors X and Y voting against)"
INLINE_SIDE = re.compile(r"\s+(?:voting\s+(?P<side>in favour|for|against)|(?P<abst>abstaining|abstained))\b", re.I)
_SIDE_WORD = {"for": "for", "in favour": "for", "against": "against"}


def _parse_alternative(flat: str, matcher: Matcher) -> list[Vote]:
    """Named votes written without headings: names in brackets after a count ("namely"), or before the side."""
    out: list[Vote] = []
    for kind in ("namely", "inline"):
        block_start = None
        sides_seen: set[str] = set()
        block = 0
        if kind == "namely":
            hits = [(m.start(), m.end(), "abstain" if m.group("side").lower().startswith("abst")
                     else _SIDE_WORD[m.group("side").lower()],
                     [] if m.group("none") else split_names(m.group("names") or "")) for m in NAMELY.finditer(flat)]
        else:
            hits = []
            prev = 0
            for m in INLINE_SIDE.finditer(flat):
                if re.match(r"\s+of\s+(?:councillor|cllr)\b", flat[m.end():m.end() + 20], re.I):
                    continue                        # "voting in favour of Councillor Bigmore": an election
                # the names run back from the side word to an opening bracket, the last side or the sentence start
                start = max(flat.rfind("(", prev, m.start()) + 1, flat.rfind(". ", prev, m.start()) + 2, prev)
                segment = re.sub(r"^\s*and\s+", "", flat[start:m.start()])
                side = "abstain" if m.group("abst") else _SIDE_WORD[m.group("side").lower()]
                hits.append((start, m.end(), side, split_names(segment)))
                prev = m.end()
        for start, end, side, names in hits:
            if not names and kind == "inline":
                continue
            if side in sides_seen:
                block += 1
                sides_seen = set()
                block_start = start
            sides_seen.add(side)
            block_start = start if block_start is None else block_start
            outcome = _outcome(flat[max(0, block_start - 300):end + 200])
            excerpt = flat[max(0, block_start - 200):end + 100][:1500]
            for name in names:
                out.append(Vote(block, side, name, matcher.match(name), outcome, "", excerpt))
        if out:
            # a named vote names at least two members, or names one side of a vote announced as recorded
            if len(out) >= 2 and (len({v.side for v in out}) >= 2 or _ANNOUNCED.search(flat)):
                return out
            out = []
    return []


def parse(text: str, members: list[Member]) -> list[Vote]:
    """Every named vote in one agenda item's minutes."""
    flat = flatten(text)
    heads = list(HEADING.finditer(flat))
    if not heads:
        return _parse_alternative(flat, Matcher(members))
    # Each heading's list of names, then the headings grouped into votes: a side named again starts a new vote.
    sides = []
    for n, h in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(flat)
        segment = flat[h.end():end]
        stop = _STOP.search(segment)
        names_end = h.end() + (stop.start() if stop else len(segment))
        raw = flat[h.end():names_end]
        if not re.search(r"[:\-–—)]\s*$", h.group(0)) and not re.search(r"voting|favour|those|members", h.group(0), re.I):
            continue                              # "For Councillor Gordon": a heading needs a colon unless it says "voting"
        if re.match(r"^\s*councill?or\s+[\w' .-]{1,40}?\s*(?:\(\s*\d+\s*votes?\s*\))?\s*:", raw, re.I) or \
                re.search(r"\bfor\s+(?:councillor|cllr)\b", h.group(0), re.I):
            sides.append((h, None, names_end))   # "FOR COUNCILLOR SHOOB: ...": an election of a person, not a motion
            continue
        if re.match(r"^\s*(?:none|nil)\b", raw, re.I) and split_names(re.sub(r"^\s*(?:none|nil)\b", "", raw, flags=re.I)):
            sides.append((h, None, names_end))   # names after "None": a column layout that can't be read reliably
            continue
        names = split_names(raw)
        if not raw.strip(" .:-–"):
            if re.search(r"\(\s*0\s*\)", h.group(0)):
                sides.append((h, [], names_end))     # "AGAINST the Amendment (0)."
            else:
                sides.append((h, None, names_end))   # "FOR: AGAINST: ABSTAIN:" across columns
            continue
        if h.lastgroup == "for" and not names:
            continue                     # "for" used in passing, with no names after it
        sides.append((h, names, names_end))
    blocks: list[list[tuple]] = []
    for entry in sides:
        if not blocks or entry[0].lastgroup in {e[0].lastgroup for e in blocks[-1]}:
            blocks.append([])
        blocks[-1].append(entry)

    # A real named vote gives at least two sides, or is announced just before ("a recorded vote was taken").
    blocks = [entries for entries in blocks if all(e[1] is not None for e in entries)]
    blocks = [entries for entries in blocks
              if len({e[0].lastgroup for e in entries}) >= 2
              or _ANNOUNCED.search(flat[max(0, entries[0][0].start() - 400):entries[0][0].start()])]
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


_COLUMNS = {"for": re.compile(r"^(?:for|in favour|yes|aye)\s*:?$", re.I),
            "against": re.compile(r"^(?:against|no|nay)\s*:?$", re.I),
            "abstain": re.compile(r"^(?:abstain(?:ed|ing)?|abstentions?)\s*:?$", re.I)}


def parse_tables(tables: list[list[list[str]]], members: list[Member], first_block: int = 0,
                 context: str = "") -> list[Vote]:
    """Named votes set out as a table: a heading row "Name | For | Against | Abstain | Absent" and a row per member
    with a mark (a tick, often lost as "?", or an X) in one column."""
    matcher = Matcher(members)
    out: list[Vote] = []
    block = first_block
    for rows in tables:
        start, cols, head = 0, {}, []
        for n, row in enumerate(rows[:4]):  # the heading row, after any title rows
            cols = {side: i for i, cell in enumerate(row) for side, rx in _COLUMNS.items() if rx.match(cell.strip())}
            if "for" in cols and "against" in cols and len(row) >= 3:
                start, head = n, row
                break
        if not head:
            continue
        found = []
        if not re.match(r"^(?:name|councillor|member)s?\b", head[0].strip(), re.I):
            # a column per side, the names listed in its cells
            for row in rows[start + 1:]:
                for side, i in cols.items():
                    if i < len(row) and row[i].strip():
                        found += [(n, side) for n in split_names(row[i].replace("\n", " "))]
            if found:
                outcome = _outcome(context)
                excerpt = " | ".join(head) + " … (" + str(len(found)) + " members)"
                for name, side in found:
                    out.append(Vote(block, side, name, matcher.match(name), outcome, "", excerpt))
                block += 1
            continue
        for row in rows[start + 1:]:
            name = " ".join(_HONOURS.sub(" ", row[0]).split()) if row else ""
            if not name or re.search(r"\d", name) or not looks_like_name(name):
                continue
            marked = [side for side, i in cols.items() if i < len(row) and row[i].strip()]
            if len(marked) == 1:
                found.append((row[0], marked[0]))
        if not found:
            continue
        outcome = _outcome(context)
        excerpt = " | ".join(head) + " … (" + str(len(found)) + " members)"
        for name, side in found:
            written = " ".join(_HONOURS.sub(" ", name).split())
            out.append(Vote(block, side, written, matcher.match(written), outcome, "", excerpt))
        block += 1
    return out
