"""Remove the names of people who aren't councillors from minutes text before it is indexed or shown
(docs/DECISIONS.md, 9).

Minutes name members of the public (speakers, petitioners, people asking questions), and council staff. Briefings
and pages are limited to councillors' own words and actions, so other people's names are replaced with
"[name removed]"; a role given with the name is kept ("[name removed], Chief Executive").

A name is kept if its surname belongs to a councillor of that council around the date, because some councils write
councillors as "Mrs Hollingsbee" or "Sir Steve Houghton". The raw minutes stay in the store, so the text can be
processed again if the rules change.

Names are found where minutes usually give them:
  * with a title: "Mr J Smith", "Mrs Jones", "Dr Patel";
  * with a role: "Jane Smith (Director of Public Health)", "Colin Carmichael, Chief Executive";
  * as the subject of speaking: "Jane Smith asked …", "Mark Jones said …", "Mark Jones addressed the Council";
  * after a description: "a member of the public, Jane Smith", "Public speaker: John Brown";
  * before a description: "Sarah Brown, a local resident, spoke", "Lucy Byrne, resident of Pill", "Steve Lily, of
    Claremont Terrace Residents Association", "Ann Smith, Gary Danks and Mary Knight, residents of …";
  * after an action towards them: "the Leader invited Jonathan Davies …", "a question from Jane Smith", "a petition
    presented by Gary Danks", "a deputation led by Ann Smith";
  * in a list of the officers at a meeting: "Officers present: Sam Taylor, Joe Bloggs and Ann Other".

Agenda items' titles are passed through here too, wherever they are indexed, shown or given to the model.

Places and job titles written like names ("Hampshire Rose", "the Equalities Manager") are mostly left alone, but some
are removed by mistake; a name given with no such context can be missed. See docs/PILOT.md.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

REMOVED = "[name removed]"

_PART = r"(?:[A-Z][a-z'’]{0,2}[A-Z][a-z'’]+|[A-Z][a-z'’]+)"        # "Smith", "McInroy", "MacDonald", "O'Brien"
_NAME_WORD = rf"{_PART}(?:-{_PART})?"
_TITLED = re.compile(
    rf"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame|(?:(?:Right|Rt|Very)\.?\s+)?(?:Reverend|Reverand|Revd|Rev)|"
    rf"Father|Canon|Bishop)\.?\s+"
    rf"(?:[A-Z]\.?\s*){{0,3}}{_NAME_WORD}(?:\s+{_NAME_WORD}){{0,2}}"
)
_ROLE_WORDS = (r"Chief|Director|Head|Assistant|Corporate|Strategic|Interim|Monitoring|Section 151|Democratic|Service|"
               r"Senior|Principal|Deputy Chief|Executive Director|Officer|Manager|Lead|Solicitor|Clerk|Treasurer|"
               r"Leader of|Programme|Planning|Legal|Finance")
_FULL = rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,2}}"
_WITH_ROLE = re.compile(rf"\b(?P<name>{_FULL})(?=\s*\((?:the\s+)?(?:{_ROLE_WORDS})|,\s+(?:the\s+)?(?:{_ROLE_WORDS})\b|"
                        rf"\s+the\s+(?:{_ROLE_WORDS})\b)")   # "David Armiger the Chief Executive" (found by the check)
_SPEAKING = re.compile(
    rf"(?<!Councillor )(?<!Councillors )(?<!Cllr )(?<!Cllr\. )(?<!Alderman )(?<!Aldermen )\b(?P<name>{_FULL})\s+"
    r"(?=asked|spoke|addressed|presented|submitted|read out|thanked|put (?:a|the|her|his|their) question|"
    r"made (?:a|the) (?:statement|deputation|representation)|"
    # found by the audit of November 2026: "Jo Bloggs said that the scheme would affect her family"
    r"said\b|stated\b|explained\b|commented\b|queried\b|questioned\b|objected\b|responded\b|replied\b|"
    r"highlighted\b|urged\b|requested\b|expressed\b|outlined\b|suggested\b|raised\b)"
)
_OBJECT = re.compile(
    rf"\b(?:invited|welcomed|thanked|introduced|congratulated|thanks to|welcome to|presentation by|statement by|"
    rf"question from|questions from|petition from|deputation from|submitted by|"
    # "The Council received a petition presented by Gary Danks", "a deputation, led by Ahmed Khan" (the audit)
    rf"presented by|led by|organised by|tabled by|raised by|asked by)\s+(?P<name>{_FULL})\b"
)
_DESCRIBED = re.compile(
    rf"(?i:member of the public|members of the public|public speakers?|petitioners?|objectors?|lead petitioner|"
    rf"local residents?|a resident|questioner|applicant|agent for the applicant|on behalf of the applicant)"
    rf"(?:,|:|\s+-|\s+–)?\s+(?P<name>(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+)?(?:[A-Z]\.?\s*){{0,3}}{_FULL}|"
    rf"(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+(?:[A-Z]\.?\s*){{0,3}}{_NAME_WORD})"
)
# A name (or a list of names) said to be a resident, a member of the public, a petitioner, or to come from an
# organisation, straight after it (found by the audit of November 2026): "Sarah Brown, a local resident, spoke",
# "Margaret Ripley, a local resident aged 99", "Lucy Byrne, resident of Pill", "Helen Jones (resident) addressed",
# "Steve Lily, of Claremont Terrace Residents Association", "Sophia McAllister, Gary Danks and Mary Knight residents
# of St James' Estate".
_PERSON = (rf"(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+)?(?:[A-Z]\.?\s*){{0,3}}{_FULL}|"
           rf"(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+(?:[A-Z]\.?\s*){{0,3}}{_NAME_WORD}")
_SEP = r"(?:,\s*|\s+and\s+|\s*&\s*)"
_DESCRIBED_AFTER = re.compile(
    rf"\b(?P<name>(?:{_PERSON})(?:{_SEP}(?:{_PERSON}))*)"
    rf"(?=\s*\((?:a\s+)?(?:local\s+)?(?:resident|member of the public|petitioner|public speaker)\)|"
    rf",?\s+(?:(?:a|an|both|all|two|three|four|fellow)\s+)?(?:local\s+)?(?:residents?|members? of the public|"
    rf"lead petitioners?|petitioners?|public speakers?)\b|"
    rf",\s+(?:of|from)\s+(?:the\s+)?[A-Z])"
)
# The officers at a meeting, listed after a heading: "Officers present: Sam Taylor, Joe Bloggs and Ann Other",
# "Officers in attendance: Mike Ward (Democratic Services), Lucy Gray (Monitoring Officer)" (the audit). Only a
# heading that says they are officers: "Present:" alone lists councillors.
_OFFICERS = re.compile(r"\b(?i:(?:council\s+)?(?:officers?|officials?|staff)\s+(?:present|in attendance|attending)|"
                       r"in attendance \(officers?\))\s*[:\-–]?\s*")
_OFFICER_ENTRY = re.compile(rf"\s*(?P<name>{_PERSON})")
# A question's header: "Question 1 From: Marcus Simpson To: Cabinet Member for ..." (found by the check)
_HEADER = re.compile(rf"\b(?:From|Asked by|Questioner|Submitted by|Petitioner|Speaker)\s*:\s*"
                     rf"(?P<name>(?:[A-Z]\.?\s+){{0,3}}{_NAME_WORD}(?:\s+(?!To\b){_NAME_WORD}){{0,2}})\b")
# Initials and a surname after the same words as _OBJECT ("Question from M J Ray"), and "read by Lee Stevens"
_INITIALS = re.compile(rf"\b(?i:question from|questions from|petition from|deputation from|submitted by|read by|"
                       rf"read out by)\s+(?P<name>(?:[A-Z]\.?\s+){{1,3}}{_NAME_WORD}|{_FULL})\b")
# A speaker in a transcript, named with their area: "Trevor Hammon (Ifield) It's really a question ..." (found by the
# check). A councillor written this way is kept by their surname, like any other.
_TRANSCRIPT = re.compile(rf"(?m)^\s*(?P<name>{_FULL})\s*\([A-Z][a-z]+(?:[ -][A-Z][a-z]+)?\)\s+(?=[A-Z])")
# Words that make a capitalised phrase a place or an organisation, not a person. Words that are also common surnames
# (Green, Hill, Hall, Park, Lane, West ...) only count where they can't be one: first, for the second list.
_ORG_WORDS = {"road", "street", "avenue", "council", "borough", "county", "district", "centre", "center", "school",
              "college", "academy", "trust", "board", "committee", "cabinet", "services", "team", "partnership",
              "authority", "government", "university", "homes", "housing", "plan", "policy", "fund", "estate",
              "crescent", "terrace", "gardens", "nhs", "ltd", "limited", "plc", "association", "society", "forum",
              "police", "agency", "audit", "group", "network", "company", "campaign", "commission", "department",
              "office", "village", "hospital", "rail", "railway", "highways", "water", "energy", "transport",
              "residents", "action", "alliance", "union", "federation", "charity", "foundation", "club"}
# Words of job titles, which minutes often capitalise ("The Equalities Manager presented").
_TITLE_WORDS = {"manager", "officer", "director", "head", "leader", "member", "lead", "executive", "services",
                "service", "delivery", "development", "change", "finance", "performance", "planning", "strategy",
                "strategic", "wellbeing", "equalities", "equality", "engagement", "consultation", "chief", "assistant",
                "deputy", "senior", "democratic", "programme", "project", "portfolio", "holder", "chair", "mayor",
                "governance", "resources", "corporate", "operations", "transformation", "policy", "communities",
                "regeneration", "housing", "environment", "culture", "leisure", "customer", "digital", "legal",
                "monitoring", "treasurer", "clerk", "solicitor", "partnerships", "children", "adults", "education",
                "health", "care", "public", "safety", "commissioning", "economy", "growth", "assets", "property"}
_PLACE_FIRST = {"holy", "saint", "st", "the", "royal", "east", "west", "north", "south", "new", "national", "regional",
                "local", "public", "great", "upper", "lower", "old", "little", "natural", "historic", "sport", "save",
                "friends"}


def _surname(name: str) -> str:
    words = re.sub(r"[^\w' -]", " ", name).split()
    return words[-1].lower().strip("'’") if words else ""


# Words that make a name a councillor's, wherever the pattern that found it started: "Councillor Ann Other said".
_COUNCILLOR_WORDS = {"councillor", "councillors", "cllr", "cllrs", "alderman", "aldermen", "cynghorydd", "cynghorwyr"}


def _is_person(name: str) -> bool:
    words = [w.lower().strip(".,'’") for w in re.sub(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr|Prof|Professor|Sir|Dame|Rev|Revd)\b\.?",
                                                     " ", name).split()]
    return (bool(words) and not any(w in _ORG_WORDS or w in _TITLE_WORDS or w in _COUNCILLOR_WORDS for w in words)
            and words[0] not in _PLACE_FIRST)


# A councillor's role straight after the name: the person is a councillor, whatever the attendance list says.
_COUNCILLOR_ROLE = re.compile(r"^\s*[,(]\s*(?:the\s+)?(?:deputy\s+)?(?:leader|mayor|lord mayor|civic mayor|cabinet member|"
                              r"portfolio holder|chair(?:man)?|vice[- ]chair|executive member|presiding member)\b", re.I)
# Words that end a list of names in minutes rather than belong to one.
_NOT_NAME_TAIL = re.compile(r"(?:\s+(?:Against|For|Abstain\w*|Abstention\w*|Absent|Apologies|Voting|Votes?|Total|None|Nil|"
                            r"Carried|Lost|Resolved|Present|The|And|Amendments?|Motions?|Recommendations?|Substantive))+$")
_AFTER_COUNCILLOR = re.compile(r"(?:councillors?|cllrs?\.?|cynghorydd|alderm[ae]n)\s*$", re.I)
_LIST_MORE = re.compile(rf"^(?:,\s*|\s+and\s+|\s*&\s*)(?P<name>(?:(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+)?(?:[A-Z]\.?\s*){{0,3}}"
                        rf"{_NAME_WORD}(?:\s+{_NAME_WORD}){{1,2}})")


_LETTERS = re.compile(r"\b(?:MBE|OBE|CBE|KBE|DBE|BEM|CMG|JP|DL|TD|RD|KC|QC|MP|MEP|MSc|BSc|BA|MA|BEd|MEd|LLB|LLM|MBA|PhD|"
                      r"FCA|ACA|FCCA|ACMA|FRSA|FRICS|MRICS|MRTPI|CEng|FIET|Hons|Cert|Dip)\b\.?")


_STYLE_WORDS = {"the", "rt", "right", "hon", "honourable", "lord", "lady", "mayor", "deputy", "alderman", "alderwoman",
                "sheriff", "chief", "commoner", "councillor", "cllr", "chair", "chairman", "vice", "mr", "mrs", "ms",
                "miss", "dr", "sir", "dame", "former"}


def councillor_surnames(names: Iterable[str]) -> set[str]:
    """Surnames of the council's members, from attendance names ("Councillor Dave Leech" -> "leech"), including
    both parts of a double-barrelled name."""
    out = set()
    for n in names:
        # "Richard Long, TD", "Councillor Miss Phillipa Tatham BA (Hons)": letters after the name aren't the surname
        # "The Rt. Hon. the Lord Mayor, Alderman Peter Estlin": the first part that is more than titles and roles
        parts = [re.sub(_LETTERS, " ", re.sub(r"\([^)]*\)", " ", p)) for p in n.split(",")]
        n = next((p for p in parts if any(w.lower().strip(".") not in _STYLE_WORDS
                                          for w in re.sub(r"[^\w' -]", " ", p).split())), "")
        s = _surname(n)
        if s:
            out.add(s)
            out.update(p for p in s.split("-") if len(p) > 2)
    return out


def redact(text: str, councillors: set[str]) -> tuple[str, int]:
    """(text with non-councillors' names removed, how many were removed). ``councillors`` is a set of surnames
    (councillor_surnames)."""
    if not text:
        return text, 0
    spans: list[tuple[int, int]] = []

    def consider(name: str, start: int) -> bool:
        name = _NOT_NAME_TAIL.sub("", name)          # "Mr Whiting Against (51)": the heading isn't part of the name
        end = start + len(name)
        if _AFTER_COUNCILLOR.search(text[max(0, start - 14):start]) or _COUNCILLOR_ROLE.match(text[end:end + 40]):
            return False
        words = {w.lower().strip(".,'’") for w in name.split()}
        after = re.match(r"\s+([A-Z][a-z]+)", text[end:end + 30])
        if after and after.group(1).lower() in _ORG_WORDS:   # "Save Our Park Campaign", "Pill Residents Association"
            return False
        if _surname(name) in councillors or words & councillors - {""} and len(words) <= 2 or not _is_person(name):
            return False
        spans.append((start, end))
        return True

    def each(names: str, start: int) -> None:
        """Every name in a list ("Ann Smith, Gary Danks and Mary Knight"), each considered on its own."""
        for p in re.finditer(_PERSON, names):
            consider(p.group(0), start + p.start())

    for rx in (_TITLED, _WITH_ROLE, _SPEAKING, _OBJECT, _DESCRIBED, _HEADER, _INITIALS, _TRANSCRIPT):
        for m in rx.finditer(text):
            name = m.group("name") if "name" in rx.groupindex else m.group(0)
            start = m.start("name") if "name" in rx.groupindex else m.start()
            consider(name, start)
            if rx in (_DESCRIBED, _OBJECT):   # "local residents A Smith, David Edwards and Sarah Holmes"
                pos = start + len(name)
                while (more := _LIST_MORE.match(text[pos:pos + 120])):
                    consider(more.group("name"), pos + more.start("name"))
                    pos += more.end()
    for m in _DESCRIBED_AFTER.finditer(text):
        each(m.group("name"), m.start("name"))
    for m in _OFFICERS.finditer(text):       # the list runs to the end of its sentence or line
        pos = m.end()
        while (entry := _OFFICER_ENTRY.match(text, pos)):
            consider(entry.group("name"), entry.start("name"))
            pos = entry.end()
            role = re.match(r"\s*\([^()\n]{0,80}\)", text[pos:])          # "(Democratic Services)"
            pos += role.end() if role else 0
            sep = re.match(_SEP, text[pos:])
            if not sep:
                break
            pos += sep.end()
    if not spans:
        return text, 0
    spans.sort()
    merged: list[list[int]] = []
    for a, b in spans:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    out, last = [], 0
    for a, b in merged:
        out += [text[last:a], REMOVED]
        last = b
    out.append(text[last:])
    return "".join(out), len(merged)
