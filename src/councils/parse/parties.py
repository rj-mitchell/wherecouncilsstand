"""Councils' own party labels ("LAB", "Labour", "Lab", "Labour & Co-operative") to one code per party.

National parties have fixed codes. A label for a single independent councillor is "IND". A named group of
independents or residents ("Ashfield Independents", "R4GV") is a local party, not "IND": its code is "LOCAL", and the
label is kept as recorded. Labels not recognised return "", and are listed by the pilot report so they can be added
to data_static/parties.csv, which overrides these rules.
"""

from __future__ import annotations

import csv
import re
from functools import lru_cache

from councils.config import STATIC_DIR

NAMES = {
    "LAB": "Labour", "CON": "Conservative", "LD": "Liberal Democrats", "GRN": "Green", "REF": "Reform UK",
    "PC": "Plaid Cymru", "UKIP": "UKIP", "LIB": "Liberal Party", "YP": "Your Party", "WPB": "Workers Party",
    "SDP": "Social Democratic Party", "IND": "Independent", "LOCAL": "Local party or group",
    "NONE": "No party recorded",
}

_RULES = [
    ("LAB", r"lab|labour|labour (and|&) co-?op(erative)?( party)?|lab ?(/|and|&)? ?co-?op|labour party|labour group"),
    ("CON", r"con|cons|conservatives?( party| group)?|conservative (and|&) unionist|tory|tories"),
    ("LD", r"ld|lib ?dems?|libdems?|liberal democrats?( party| group)?|lib dem group|libdem group"),
    ("GRN", r"grn|green|greens|green party|green group|the green party"),
    ("REF", r"ref|refuk|reform|reform uk|reform uk party|reform group|reform uk group"),
    ("PC", r"pc|plaid|plaid cymru|plaid cymru - the party of wales"),
    ("UKIP", r"ukip|uk independence party"),
    ("LIB", r"liberal|liberal party"),
    ("YP", r"your party|yp"),
    ("WPB", r"workers party( of britain)?|wpb"),
    ("SDP", r"sdp|social democratic party"),
    ("IND", r"ind|independent|independents?( member| councillor)?|non-? ?aligned|unaligned|no party|non political"),
    ("NONE", r"|none|n/a|-"),
]
_COMPILED = [(code, re.compile(rf"^(?:{pattern})$", re.I)) for code, pattern in _RULES]
_LOCAL = re.compile(r"independents?\b|residents?\b|association|alliance|first\b|for \w|group$|^r4", re.I)


@lru_cache(maxsize=1)
def overrides() -> dict[str, str]:
    path = STATIC_DIR / "parties.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {r["label"].strip().lower(): r["code"] for r in csv.DictReader(fh)}


def normalise(label: str | None) -> str:
    """The party code for a council's label, or "" if it isn't recognised."""
    t = re.sub(r"\s+", " ", (label or "").replace("&amp;", "&")).strip().strip(".")
    if t.lower() in overrides():
        return overrides()[t.lower()]
    for code, rx in _COMPILED:
        if rx.match(t):
            return code
    if _LOCAL.search(t):
        return "LOCAL"
    return ""
