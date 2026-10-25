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

_OBJ = r"(?:original |substantive |amended |revised |above )?(?:motion|amendment|recommendations?|resolutions?|budget|proposals?|report|substantive motion|item|objection)"
_TRAIL = rf"(?:\s+(?:the|this|that)\s+(?:(?!\b(?:are|were|was|is|be|been|recorded|follows|below|vot\w+)\b)[^:;.()]){{1,90}}?(?=\s*:(?!\d))|\s+(?:on\s+|from\s+)?(?:the|this|that)\s+{_OBJ}(?:\s+(?:to|for|on|relating to|in respect of)\s[^:;.()]{{1,90}}?(?=\s*:))?)?(?:\s+as amended)?(?:\s+below)?(?:,?\s+(?:being\s+)?present at the time of (?:the )?vot(?:e|ing))?(?:\s+were)?"
_COUNT = r"(?:\s*\(\s*\d+\s*(?:total|votes?|members)?\s*\))?(?:\s*[-–]?\s*\d+\s*(?:members|councillors|votes)?)?"
_WHO = r"(?:(?:those|members|councillors)\s+(?:who\s+)?)?"
SIDES = {
    "for": rf"{_WHO}(?:votes?\s+|voting\s+|voted\s+)?(?:in\s+favour(?:\s+of)?|for){_TRAIL}{_COUNT}",
    "against": rf"{_WHO}(?:votes?\s+|voting\s+|voted\s+)?(?:against|againt){_TRAIL}{_COUNT}",
    "abstain": rf"{_WHO}(?:voting\s+to\s+)?(?:abstentions?|abtentions?|absentions?|abstained|abstaining|abstain|abstained from voting)(?:\s+(?:from|on)\s+the\s+vote)?{_TRAIL}{_COUNT}",
    # not a side: ends the list before it ("Not voting: Councillors Bailey ..."; "Absent: ...")
    "none": rf"{_WHO}(?:(?:present\s+)?not\s+voting|did\s+not\s+vote|absent|not\s+present)(?:\s+(?:from|in)\s+the\s+(?:vote|meeting|chamber|room))?{_COUNT}",
}
HEADING = re.compile(
    # a heading ends with a colon or dash, or runs straight into "Councillors ..."
    "|".join(rf"(?P<{side}>(?<![\w-]){pattern}(?:\s*(?::-|:|–(?!\d)|—|-(?!\d))\s*|\.?\s+(?=councill?ors?\b|cllrs?\b)|(?<=\))\s*\.?(?:\s+|$)))"
             for side, pattern in SIDES.items()),
    re.I,
)
# Where a list of names ends: the end of a sentence followed by something that isn't a name.
_STOP = re.compile(
    r"\.\s+(?=[(\d])|^\s*(?=(?:motion|amendment|recommendations?|proposals?|objection)s? (?:was |were )?(?:carried|lost|fell|defeated|agreed)\b)"
    r"|(?:\.\s+|\s+)(?=(?:upon|on being|the (?:motion|amendment|original|substantive|recommendations?|mayor declared|chair declared)"
    r"|resolved|it was|accordingly|there (?:were|was)|therefore|this was|having|following|in accordance|councillor \w+ (?:then|moved|asked|requested|abstained|voted)"
    r"|the (?:(?:lord|deputy|civic) )*mayor (?:abstained|did|announced|ruled|then|voted)"
    r"|the (?:vote|result|following|council|meeting|lord mayor|chair(?:man)?|leader|amended|recommendations)\b|one abstention|decisions?:"
    r"|a recorded vote|a named vote|\(\w\)\s|\d+\.\s"
    r"|(?:motion|amendment|recommendations?|proposals?|objection)s? (?:was |were )?(?:carried|lost|fell|defeated|agreed)\b"
    r"|total (?:equals|votes|number)\b))"
    # a new sentence that isn't a name: "Councillor Gill. The proposed motion therefore FELL."
    r"|(?<=\w\w)(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)\.\s+(?=(?-i:[A-Z][a-z]+\s+(?!and\b)[a-z]))",
    re.I,
)
_OUTCOME = re.compile(r"\b(carried|lost|defeated|fell|was not carried|not carried|agreed|approved|rejected)\b", re.I)
_HONOURS = re.compile(r"\b(?:BEM|OBE|MBE|CBE|JP|J\.P|DL|KC|QC|MP|MSc|BSc|BA|MA|PhD|FRSA|Dr|Mr|Mrs|Ms|Miss|Cllr|Cllrs|"
                      r"Councill?ors?|Cynghorydd|Cynghorwyr|Sir|Dame|Rev|Revd|Prof)\b\.?", re.I)
_ROLE = re.compile(r"\b(?:the\s+|elected\s+)(?:(?:civic|lord|deputy|worshipful(?:\s+the)?)\s+)*(mayor|chair(?:man|woman|person)?|presiding member|vice[- ]chair)\b", re.I)
# "the Deputy Mayor, Councillor Ed Foley"; "His Worshipful the Mayor Councillor Salim Chowdhury" -> one name
_ROLE_THEN_NAME = re.compile(
    r"\b(?i:(?:(?:his|her)\s+)?(?:worshipful\s+)?(the\s+(?:(?:civic|lord|deputy|worshipful(?:\s+the)?)\s+)*"
    r"(?:mayor|chair(?:man|woman|person)?))),?\s+(?i:councill?or|cllr)\.?\s+((?:[A-Z][\w'.-]*\s+){0,3}?[A-Z][\w'-]+)"
    r"(?=\s*(?:,|;|\band\b|&|\(|\.|$))")
_NONE = re.compile(r"^(?:none|nil|no members?|no councillors?|0|-)$", re.I)
_ANNOUNCED = re.compile(r"recorded vote|named vote|roll[- ]call|recorded as follows|voting (?:was|were) as follows|"
                        r"votes? (?:was|were) (?:cast|recorded) as follows|voted as follows", re.I)
_PARTICLES = {"de", "da", "van", "von", "der", "le", "la", "du", "di", "del", "st", "o", "mc", "mac"}


def looks_like_name(text: str) -> bool:
    """"P Birkinshaw", "Andrews BEM", "The Mayor (Councillor Markham)", not "Voluntary Controlled nursery schools"."""
    inner = re.search(r"\(([^)]*)\)", text)
    if inner and _ROLE.search(text[:inner.start()]):
        text = inner.group(1)                       # "The Deputy Lord Mayor (Councillor Jayne Dunn)"
    words = re.sub(r"[()]", " ", text).replace("'", "").split()
    if not words or len(words) > 5:
        return False
    if words[-1].lower() in _NOT_NAME_ENDINGS and not (len(words[-1]) == 1 and words[-1].isupper()):
        return False                                # ... but "Williams A" is a name written surname first
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


def _role_key(role: str) -> str:
    """"The Worshipful the Lord Mayor", "Lord Mayor" -> "mayor"; "Chairman of the Council" -> "chair of council"."""
    words = re.sub(r"\b(?:chair(?:man|woman|person))\b", "chair", role.lower()).replace("-", " ").split()
    return " ".join(w for w in words if w not in {"the", "his", "her", "worshipful", "civic", "lord", "elected", "of"})


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
        w = re.sub(r"\s*\((?:the\s+)?(?:(?:lord|deputy|civic)\s+)*(?:mayor|chair\w*)\)\s*$", "", w, flags=re.I) \
            if not _ROLE.search(w.split("(")[0]) else w   # "Roy Emmett (Mayor)" -> "Roy Emmett"
        w = re.sub(r"^([A-Z][\w'-]+)\s+([A-Z])\.?$", r"\2 \1", w)    # "Barratt R" -> "R Barratt"
        inner = re.search(r"\(([^)]*)\)", w)
        rest = _HONOURS.sub(" ", w[:role.start()] + w[role.end():]).strip(" ,") if role else ""
        if inner and re.search(r"[A-Z]", inner.group(1)):
            w = inner.group(1)                      # "The Mayor (Councillor Markham)" -> "Councillor Markham"
        elif role and re.search(r"[A-Z]", rest):
            w = rest                                # "The Lord Mayor Shabir Hussain" -> "Shabir Hussain"
        elif role:
            want = _role_key(role.group(0))
            hits = [m for m in self.members if _role_key(m.role).startswith(want)
                    and ("deputy" in want) == ("deputy" in m.role.lower())
                    and ("vice" in want) == ("vice" in m.role.lower())]
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
            if not hits and self.by_surname.get(surname):
                return ""                           # "K Berberi" when the only Berberi listed is Mark
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


_SENTENCE_END = re.compile(r"(?<=\w\w)(?<!\bMr)(?<!\bMrs)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bCllr)\.\s")


def split_names(segment: str) -> list[str]:
    """"The Mayor (Councillor Markham), and Councillors Barnard, D Birkinshaw and Smith." -> names."""
    s = re.sub(r"[(\[]\s*\d+\s*(?:votes?|members?|total)?\s*[)\]]", " ", segment, flags=re.I)
    s = re.sub(r"^\s*\d+\s*(?:votes?)?\s*(?::-|:|-|–|as follows;?-?)\s*", " ", s)      # "FOR: 40:- Bawn, ..."
    s = re.sub(r"^\s*\d+\s+(?=cllrs?\b|councill?ors\b)", " ", s, flags=re.I)              # "12 Cllrs. Bawn, ..."
    s = s.replace("?", " ").replace("~", " ").strip().rstrip(".;")                          # ticks lost as "?"
    s = _ROLE_THEN_NAME.sub(lambda m: f"{m.group(1)} (Councillor {m.group(2)})", s)
    if len(re.findall(r"\bcouncillor\b", s, re.I)) >= 2 and len(re.findall(r",|;|\band\b", s)) < \
            len(re.findall(r"\bcouncillor\b", s, re.I)) - 1:
        # "Councillor Tim Anderson Councillor Jon Askew ...": each "Councillor" starts a name
        s = re.sub(r"\b(?:the (?:deputy )?mayor|the (?:vice[- ])?chair(?:man)?),?\s*(?=councillor)", "", s, flags=re.I)
        s = re.sub(r"\bcouncillor\b", ",", s, flags=re.I)
    s = re.sub(r"\bcouncill?ors?\b:?|\bcllrs?\b\.?", "", s, flags=re.I)
    parts = re.split(r",|;|\band\b|&", s)
    if len(parts) == 1 and len(parts[0].split()) > 4 and all(w[0].isupper() for w in parts[0].split()):
        parts = _unrun(parts[0])
    names = []
    for p in parts:
        p = _SENTENCE_END.split(p)[0].strip(" .:-–")    # "T Spencer. Total": the list ended at the full stop
        if not p or _NONE.match(p) or not _HONOURS.sub(" ", p).strip(" .,"):
            continue                                # "None"; "MBE" or "Mrs" split from a name set out in columns
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


def _stated(heading: str) -> int | None:
    """The count a heading gives: "For (26) -", "Those voting FOR – 8", "Abstentions - 0"."""
    m = re.search(r"(\d+)\D*$", heading)
    return int(m.group(1)) if m else None


def _outcome_near(flat: str, start: int, names_end: int, prev_end: int, next_start: int) -> str:
    """The result given in the sentences straight after the names ("Amendment Lost."; "Following the vote, the
    motion was declared LOST."), up to one that moves on to another question; else the last one given just before
    the vote ("... was put to the vote and was lost. The votes were recorded as follows: ...")."""
    after = flat[names_end:min(next_start, names_end + 300)].lstrip(" .;?")
    for sentence in _SENTENCE_END.split(after):
        if re.search(r"\b(?:then|put to|moving to|original|subsequently|next)\b", sentence, re.I):
            break                                    # the result of the next question, not this one
        if found := _outcome(sentence):
            return found
    before = list(_OUTCOME.finditer(flat[max(prev_end, start - 300):start]))
    return _outcome(before[-1].group(0)) if before else ""


# One member recorded on their own after the lists: "The Lord Mayor abstained from voting."; "Councillor Huntley
# voted against."
_STRAGGLER = re.compile(
    r"^(?P<name>the\s+(?:(?:lord|deputy|civic)\s+)*(?:mayor|chair(?:man)?)|(?:councillor|cllr\.?)\s+(?:[A-Z]\.?\s+)?"
    r"[A-Z][\w'-]+(?:\s+[A-Z][\w'-]+)?)\s+(?:(?P<abstain>abstained|did not vote)|voted\s+(?P<side>against|for|in favour))\b",
    re.I)


def _stragglers(flat: str, names_end: int, next_start: int) -> list[tuple[str, str]]:
    out = []
    for sentence in _SENTENCE_END.split(flat[names_end:min(next_start, names_end + 300)].lstrip(" .;?")):
        if re.search(r"\b(?:then|put to|moving to|original|subsequently|next)\b", sentence, re.I):
            break
        if m := _STRAGGLER.match(sentence.strip()):
            if m.group("abstain") and m.group("abstain").lower() == "did not vote":
                continue
            side = "abstain" if m.group("abstain") else ("against" if m.group("side").lower() == "against" else "for")
            out.append((side, re.sub(r"^(?:councillor|cllr\.?)\s+", "", m.group("name"), flags=re.I)))
    return out


def parse(text: str, members: list[Member]) -> list[Vote]:
    """Every named vote in one agenda item's minutes."""
    flat = flatten(text)
    heads = list(HEADING.finditer(flat))
    if not heads:
        return _parse_alternative(flat, Matcher(members))
    # Each heading's list of names, then the headings grouped into votes: a side named again starts a new vote.
    # An entry is (heading, side, names or None if the list can't be read, where the names end).
    sides: list[tuple] = []
    tallies: list[tuple[str, int]] = []      # sides given only as a count: "For - 65 Against - 0"
    for n, h in enumerate(heads):
        end = heads[n + 1].start() if n + 1 < len(heads) else len(flat)
        segment = flat[h.end():end]
        stop = _STOP.search(segment)
        names_end = h.end() + (stop.start() if stop else len(segment))
        raw = flat[h.end():names_end]
        side = h.lastgroup or ""
        if side == "none":
            continue                              # "Not voting:", "Absent:": only ends the list before it
        if not re.search(r"(?:[:\-–—)\d]|\)\.)\s*$", h.group(0)) and not re.search(r"vot|favour|those|members", h.group(0), re.I):
            continue                              # "For Councillor Gordon": a heading needs a colon unless it says "voting"
        if re.match(r"^\s*councill?or\s+[\w' .-]{1,40}?\s*(?:\(\s*\d+\s*votes?\s*\))?\s*:", raw, re.I) or \
                re.search(r"\bfor\s+(?:councillor|cllr)\b", h.group(0), re.I):
            sides.append((h, side, None, names_end))   # "FOR COUNCILLOR SHOOB: ...": an election of a person
            continue
        if re.match(r"^\s*(?:none|nil)\b(?!\s*\.)", raw, re.I) and split_names(re.sub(r"^\s*(?:none|nil)\b", "", raw, flags=re.I)):
            sides.append((h, side, None, names_end))   # names after "None": a column layout that can't be read reliably
            continue
        lead = re.match(r"^\s*(\d+)\b\s*(?:votes?|members|councillors)?(?![:\w])", raw)
        stated = _stated(h.group(0))
        if lead and stated is None:
            stated, raw = int(lead.group(1)), raw[lead.end():]     # "For - 65 Against - 0 ..."
        names = split_names(raw)
        if not raw.strip(" .:-–"):
            if stated == 0:
                sides.append((h, side, [], names_end))     # "AGAINST the Amendment (0)."
            elif stated is not None:
                tallies.append((side, stated))           # "Those voting FOR – 56": a total after the names
            else:
                sides.append((h, side, None, names_end))   # "FOR: AGAINST: ABSTAIN:" across columns
            continue
        if "block vote" in raw.lower():
            sides.append((h, side, None, names_end))   # "Labour block vote of 15 votes": not a vote by name
            continue
        if stated and len(names) > stated * 1.5 + 2:
            # far more names than the count, as when both lists follow both headings ("For the Motion (31)
            # Against the Motion (13) Councillors ..."), or the list runs on into the text: leave this side out
            continue
        if stated == 0 and names:
            # "For - 65 Against - 0 Abstentions - 0 Avis, Banks, ...": the names belong to the side with that count
            # (a zero count followed by anything else, "Abstentions (0) RESOLVED that ...", is just zero)
            owner = [s for s, c in tallies[-3:] if abs(c - len(names)) <= 2]
            sides.append((h, owner[-1] if owner else side, names if owner else [], names_end))
            continue
        if side == "for" and not names:
            continue                     # "for" used in passing, with no names after it
        sides.append((h, side, names, names_end))
    blocks: list[list[tuple]] = []
    for entry in sides:
        if not blocks or entry[1] in {e[1] for e in blocks[-1]}:
            blocks.append([])
        blocks[-1].append(entry)

    # A real named vote gives at least two sides, or is announced just before ("a recorded vote was taken").
    blocks = [entries for entries in blocks if all(e[2] is not None for e in entries)]
    blocks = [entries for entries in blocks
              if len({e[1] for e in entries}) >= 2
              or _ANNOUNCED.search(flat[max(0, entries[0][0].start() - 400):entries[0][0].start()])]
    matcher = Matcher(members)
    if not blocks:
        return _parse_alternative(flat, matcher)     # "for the next 3-5 years:" was the only heading
    out: list[Vote] = []
    for b, entries in enumerate(blocks):
        start = entries[0][0].start()
        names_end = entries[-1][3]
        prev_end = blocks[b - 1][-1][3] if b else 0
        next_start = blocks[b + 1][0][0].start() if b + 1 < len(blocks) else len(flat)
        outcome = _outcome_near(flat, start, names_end, prev_end, next_start)
        excerpt = flat[max(prev_end, start - 200):min(next_start, names_end + 150)][:1500]
        question = next((q for q in (_question(e[0].group(0)) for e in entries) if q), "")
        seen: dict[tuple[str, str], str] = {}
        listed = [(side, names) for _, side, names, _ in entries]
        listed += [(side, [name]) for side, name in _stragglers(flat, names_end, next_start)]
        for side, names in listed:
            for name in names:
                member_id = matcher.match(name)
                if (side, member_id) in seen:
                    if seen[(side, member_id)] == name or _ROLE.fullmatch(name.strip()):
                        continue             # "the Deputy Mayor, Councillor Foley" counted once
                    member_id = ""           # two names written differently matched one member: keep both, unmatched
                elif member_id:              # (a member on both sides is left for extract.py to drop)
                    seen[(side, member_id)] = name
                out.append(Vote(b, side, name, member_id, outcome, question, excerpt))
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
