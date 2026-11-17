"""Turn a plain-English question into structured, editable search filters (adapted from Where Countries Stand).

This is the only model-driven step before retrieval. Its output is shown to the reader as filters they can change;
retrieval itself is deterministic. Without an API key, :func:`parse_offline` applies simple rules.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field
from wts_core.ports import ModelClient, ModelRequest, Usage

from councils.engine import Filters
from councils.rank.evidence import GROUP_BY
from councils.registry import councils

log = logging.getLogger(__name__)

PartyCode = Literal["LAB", "CON", "LD", "GRN", "REF", "PC", "UKIP", "LIB", "YP", "SNP", "DUP", "SF", "SDLP", "UUP",
                    "APNI", "TUV", "PBP", "IND", "NOC"]
# a strategic authority's "control" is its mayor's party, or none (decision 19)
ControlCode = Literal["LAB", "CON", "LD", "GRN", "REF", "PC", "UKIP", "LIB", "YP", "SNP", "DUP", "SF", "SDLP", "UUP",
                      "APNI", "TUV", "PBP", "IND", "NOC", "MAYOR:LAB", "MAYOR:CON", "MAYOR:LD", "MAYOR:GRN",
                      "MAYOR:REF", "MAYOR:IND", "SA:NONE"]
CouncilType = Literal["county", "district", "unitary", "metropolitan", "london_borough", "strategic_authority"]
Kind = Literal["council", "cabinet", "policy", "board", "mayor", "scrutiny"]
GroupBy = Literal["control", "region", "type", "council"]

PARTY_WORDS = [
    (r"labour", "LAB"), (r"conservatives?|tor(?:y|ies)", "CON"), (r"lib(?:eral)? dems?|liberal democrats?", "LD"),
    (r"greens?|green party", "GRN"), (r"reform(?: uk)?", "REF"), (r"plaid(?: cymru)?", "PC"),
    (r"snp|scottish national(?:ists?| party)?", "SNP"), (r"dup|democratic unionists?", "DUP"),
    (r"sinn f[eé]in", "SF"), (r"sdlp", "SDLP"), (r"uup|ulster unionists?", "UUP"), (r"alliance(?: party)?", "APNI"),
    (r"tuv", "TUV"), (r"people before profit", "PBP"),
    (r"independents?", "IND"),
]
_RUN = r"(?:-?\s*(?:run|led|controlled|held)|\s+(?:majority|controlled|administrations?))"
TYPE_WORDS = {"county councils": "county", "district councils": "district", "unitary councils": "unitary",
              "unitaries": "unitary", "metropolitan": "metropolitan", "london boroughs": "london_borough",
              "london borough councils": "london_borough", "strategic authorities": "strategic_authority",
              "combined authorities": "strategic_authority", "combined county authorities": "strategic_authority",
              "mayoral authorities": "strategic_authority", "metro mayors": "strategic_authority"}
_YEAR = r"((?:19|20)\d\d)"


@dataclass
class QueryPlan:
    question: str
    search_text: str
    filters: Filters
    wants_votes: bool = False
    interpretation: str = ""
    parser: str = "offline"
    group_by: str = "control"
    unresolved_councils: list[str] = field(default_factory=list)
    parse_error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {"question": self.question, "search_text": self.search_text, "filters": self.filters.as_dict(),
                "wants_votes": self.wants_votes, "interpretation": self.interpretation, "parser": self.parser,
                "group_by": self.group_by, "unresolved_councils": self.unresolved_councils}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> QueryPlan:
        f = d.get("filters") or {}
        filters = Filters(date_from=_iso(f.get("date_from")), date_to=_iso(f.get("date_to")),
                          **{k: list(f.get(k) or []) for k in ("councils", "nations", "regions", "council_types",
                                                                "kinds", "control", "parties")},
                          named_votes_only=bool(f.get("named_votes_only")))
        return cls(question=d.get("question", ""), search_text=d.get("search_text") or d.get("question", ""),
                   filters=filters, wants_votes=bool(d.get("wants_votes")), interpretation=d.get("interpretation", ""),
                   parser=d.get("parser", "edited"),
                   group_by=d.get("group_by") if d.get("group_by") in GROUP_BY else "control")


def _iso(v: Any) -> date | None:
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def dates_in(question: str, today: date) -> tuple[date | None, date | None]:
    q = question.lower()
    m = re.search(rf"\bbetween {_YEAR} and {_YEAR}\b|\bfrom {_YEAR} to {_YEAR}\b|\b{_YEAR}\s*[-–]\s*{_YEAR}\b", q)
    if m:
        a, b = [int(x) for x in m.groups() if x]
        return date(min(a, b), 1, 1), date(max(a, b), 12, 31)
    m = re.search(rf"\b(?:since|from|after) {_YEAR}\b", q)
    if m:
        return date(int(m.group(1)), 1, 1), None
    m = re.search(rf"\b(?:before|until|up to) {_YEAR}\b", q)
    if m:
        return None, date(int(m.group(1)) - 1, 12, 31)
    m = re.search(rf"\bin {_YEAR}\b", q)
    if m:
        y = int(m.group(1))
        return date(y, 1, 1), date(y, 12, 31)
    m = re.search(r"\b(?:last|past) (\d+|two|three|four|five|ten) years\b", q)
    if m:
        n = {"two": 2, "three": 3, "four": 4, "five": 5, "ten": 10}.get(m.group(1)) or int(m.group(1))
        return date(today.year - n, 1, 1), None
    return None, None


def councils_in(question: str) -> list[tuple[str, str]]:
    """(GSS code, words matched) for councils named in the question. Names are matched with their capital letters
    ("Bury", not "bury"), longest first, so "North Yorkshire" wins over "York"."""
    found: list[tuple[str, str]] = []
    taken: list[tuple[int, int]] = []
    # a strategic authority by its name, its initials ("GMCA") or its short name with "combined authority" or
    # "mayor" ("West Yorkshire mayor"): its short name alone is often a region's ("the West Midlands")
    names = sorted([(c.short_name, c.gss) for c in councils().values() if len(c.short_name) >= 3
                    and not c.is_authority]
                   + [(n, c.gss) for c in councils().values() if c.is_authority
                      for n in (c.name, c.reference, *(f"{c.short_name} {w}" for w in
                                                       ("Combined Authority", "Combined County Authority", "mayor",
                                                        "Mayor", "CA", "CCA")))],
                   key=lambda x: -len(x[0]))
    for name, gss in names:
        if any(g == gss for g, _ in found):     # an authority already found by another of its names
            continue
        for m in re.finditer(rf"(?<![\w-]){re.escape(name)}(?![\w-])", question):
            if any(a < m.end() and m.start() < b for a, b in taken):
                continue
            taken.append(m.span())
            found.append((gss, name))
            break
    return found


def parse_offline(question: str, today: date | None = None, default_years: int = 4,
                  start: date = date(2018, 5, 1)) -> QueryPlan:
    today = today or date.today()
    ql = question.lower()
    date_from, date_to = dates_in(question, today)
    if date_from is None and date_to is None:
        date_from = max(date(today.year - default_years, 1, 1), start)
    elif date_from is None:
        date_from = start
    control, parties, strip = [], [], []
    for pattern, code in PARTY_WORDS:
        m = re.search(rf"\b(?:{pattern}){_RUN}\b|\bcouncils? (?:run|led|controlled) by (?:the )?(?:{pattern})\b", ql)
        if m:
            control.append(code)
            strip.append(m.group(0))
            continue
        m = re.search(rf"\b(?:{pattern})\s+(?:councillors?|members|group)\b", ql)
        if m:
            parties.append(code)
            strip.append(m.group(0))
    if re.search(r"\bno overall control\b|\bhung councils?\b", ql):
        control.append("NOC")
        strip.append("no overall control")
    for pattern, code in PARTY_WORDS:     # strategic authorities with a mayor of a party (decision 19)
        m = re.search(rf"\b(?:{pattern})\s+(?:metro\s+)?mayors?\b", ql)
        if m and code in ("LAB", "CON", "LD", "GRN", "REF", "IND"):
            control.append(f"MAYOR:{code}")
            strip.append(m.group(0))
    types = sorted({t for w, t in TYPE_WORDS.items() if w in ql})
    nations = [n for n, rx in (("wales", r"\bwelsh councils?\b|\bin wales\b"),
                               ("england", r"\benglish councils?\b|\bin england\b"),
                               ("scotland", r"\bscottish councils?\b|\bin scotland\b"),
                               ("northern_ireland", r"\bnorthern ir(?:eland|ish) councils?\b|\bin northern ireland\b"))
               if re.search(rx, ql)]
    kinds = [k for k, rx in (("cabinet", r"\bcabinets?\b|\bexecutives?\b"), ("council", r"\bfull councils?\b"),
                             ("scrutiny", r"\bscrutiny\b"))
             if re.search(rx, ql)]
    named = councils_in(question)
    wants_votes = bool(re.search(r"\bvot(?:e|ed|es|ing)\b", ql))
    group_by = "region" if re.search(r"\bby region\b|\bregions?\b", ql) else \
        ("type" if types and len(types) > 1 else ("council" if len(named) >= 2 else "control"))
    text = ql
    for w in sorted(strip + [w.lower() for _, w in named], key=len, reverse=True):
        text = text.replace(w, " ")
    text = re.sub(rf"\b(?:between|since|from|after|before|until|in|to|and)\s+{_YEAR}\b|\b{_YEAR}\b", " ", text)
    text = " ".join(text.split()) or question
    bits = []
    if named:
        bits.append("councils: " + ", ".join(councils()[g].name for g, _ in named))
    if control:
        bits.append("in overall control: " + ", ".join(control))
    if parties:
        bits.append("councillors named from: " + ", ".join(parties))
    bits.append(f"from {date_from.year}" + (f" to {date_to.year}" if date_to else ""))
    return QueryPlan(question=question, search_text=text,
                     filters=Filters(date_from=date_from, date_to=date_to, councils=[g for g, _ in named],
                                     nations=nations, council_types=types, kinds=kinds, control=control,
                                     parties=parties),
                     wants_votes=wants_votes, interpretation="Searching " + "; ".join(bits) + ".",
                     parser="offline", group_by=group_by)


class ParsedQuery(BaseModel):
    """Schema the model fills in (structured output)."""

    search_text: str = Field(description="Keywords for retrieval, in the vocabulary of council minutes")
    date_from: str | None = Field(description="YYYY-MM-DD or null")
    date_to: str | None = Field(description="YYYY-MM-DD or null")
    councils: list[str] = Field(description="Councils named in the question, as written")
    control: list[ControlCode]
    parties: list[PartyCode]
    nations: list[Literal["england", "wales", "scotland", "northern_ireland"]]
    council_types: list[CouncilType]
    kinds: list[Kind]
    group_by: GroupBy
    wants_votes: bool
    interpretation: str = Field(description="One sentence: how the question was interpreted")


def system_prompt(today: date, start: date, default_years: int) -> str:
    return f"""You convert research questions about what councils in England, Wales, Scotland and Northern Ireland have discussed and decided
into search filters for their full council and cabinet minutes. Today's date is {today.isoformat()}. The minutes
cover {start.isoformat()} to today.

Rules:
- Only set a filter when the question clearly asks for it. Never invent constraints.
- search_text: the topic, in the vocabulary of council minutes (e.g. "waste collection, bin collections, recycling";
  "council tax, budget, precept"). Leave out words that only express filters (dates, council names, parties).
- date_from/date_to: ISO dates for explicit or clearly implied periods. When the question gives no period, set
  date_from to {max(today.year - default_years, start.year)}-01-01 and date_to to null.
- councils: councils the question names ("Barnsley", "Manchester City Council").
- control: only when the question asks about councils run by a party ("Labour-run councils", "councils controlled
  by Reform UK"): LAB, CON, LD, GRN, REF, PC, UKIP, LIB, YP, SNP, DUP, SF, SDLP, UUP, APNI (Alliance), TUV, PBP, IND, or NOC for no
  overall control. For England's strategic authorities (combined authorities and combined county authorities, with
  their metro mayors) a mayor's party is not control of a council: "authorities with a Labour mayor" is MAYOR:LAB
  (likewise MAYOR:CON, MAYOR:LD, MAYOR:GRN, MAYOR:REF, MAYOR:IND), and authorities without a mayor are SA:NONE. When
  the question compares councils run by different parties, leave control empty and set group_by to "control".
- parties: only when the question asks about what councillors of a party said or did (not who runs the council).
- nations, council_types (strategic_authority for combined and combined county authorities), kinds (council = full
  council, cabinet, policy = committee-system councils' main committees, board = a strategic authority's board,
  scrutiny = its overview and scrutiny committees, mayor = its mayor's decisions): only when asked.
- councils also takes strategic authorities the question names ("Greater Manchester Combined Authority", "WMCA",
  "the West Yorkshire mayor").
- group_by: "control" (by party in overall control, the default), "region", "type" (kind of council) or "council".
- wants_votes: true if the question is about how councillors voted.
- interpretation: one plain sentence describing the filters you chose, in British English."""


def parse_model(settings) -> str:
    return settings.answer.get("query_parse_model") or settings.answer.get("model", "claude-sonnet-5-5")


def parse_with_model(model: ModelClient, settings, question: str,
                     today: date | None = None) -> tuple[QueryPlan, Usage]:
    """The question read by the model into this site's filters, and what the reading cost."""
    today = today or date.today()
    default_years = int(settings.archive.get("default_years", 4))
    p, usage = model.structured(ModelRequest(
        model=parse_model(settings), instructions=system_prompt(today, settings.start_date, default_years),
        question=f"Question: {question}", max_tokens=2000,
        effort=settings.answer.get("query_parse_effort", "low"),
        cache_instructions=settings.answer.get("cache_instructions", "short")), ParsedQuery)
    codes, unresolved = [], []
    for name in p.councils:
        hits = councils_in(name) or councils_in(name.title())
        (codes if hits else unresolved).append(hits[0][0] if hits else name)
    date_to = _iso(p.date_to)
    plan = QueryPlan(
        question=question, search_text=p.search_text.strip() or question,
        filters=Filters(date_from=_iso(p.date_from), date_to=None if date_to and date_to >= today else date_to,
                        councils=codes, nations=list(p.nations), council_types=list(p.council_types),
                        kinds=list(p.kinds), control=list(p.control), parties=list(p.parties)),
        wants_votes=p.wants_votes, interpretation=p.interpretation, parser="model", group_by=p.group_by,
        unresolved_councils=unresolved)
    return plan, usage


def plan_json(plan: QueryPlan) -> str:
    return json.dumps(plan.to_dict(), default=str)
