"""Councils' own party labels ("LAB", "Labour", "Lab", "Labour & Co-operative") to one code per party.

National parties have fixed codes. A label for a single independent councillor is "IND". A named group of
independents or residents ("Ashfield Independents", "R4GV") is a local party, not "IND": its code is "LOCAL", and the
label is kept as recorded. Labels not recognised return "", and are listed by the pilot report. A council's own codes
("L", "WLP", "IND2") are mapped in data_static/parties.csv, by council, by scripts/party_labels.py; that file overrides
these rules.
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
    ("LAB", r"lab|labour|labour (and |& )?co-?op(erative)?( party)?|lab ?(/|and|&)? ?co-?op|labcop|labco|labourcoop"
            r"|labour party|labour group|welsh labour( party)?|labour and co-operative party|the labour party"
            # Labour and Co-operative, as councils abbreviate it: "L&C", "LAB-CO", "LCO", "LABC", "LCP", "co-op"
            r"|l ?(&|and) ?co?(-?op)?|landc|lco|lac|laco|labc|lcp|lab ?(-|&) ?co(-?op(erative)?|p)?|lab&coop"
            r"|la[bo]?our (&|and) co-?op(erative)?( party)?|co-?op(erative)?( party)?"),
    ("CON", r"con|cons|conservatives?( party| group)?|conservative (and|&) unionist( party)?|tory|tories|conu"
            r"|the conservative party( candidate)?"),
    ("LD", r"ld|lib ?dems?|libdems?|liberal democrats?( party| group)?|lib dem group|libdem group|libdem ?fo(cus)?"
           r"|wld|welsh liberal democrats?"),
    ("GRN", r"grn|gre|gp|green|greens|green party( candidate)?|green group|the green party"
            r"|green party and independent group"),
    ("REF", r"ref|refuk|ruk|reform ?uk|reform|reform uk party|reform group|reform uk group"),
    ("PC", r"pc|plaid|plai|plaid cymru|plaid cymru - the party of wales"),
    ("UKIP", r"ukip|uk independence party"),
    ("LIB", r"liberal|liberal party"),
    ("YP", r"your party|yp"),
    ("WPB", r"workers party( of britain)?|wpb"),
    ("SDP", r"sdp|social democratic party"),
    ("IND", r"i|ind|ind ind|indy|indep|inde|independent|independant|independents?( member| councillor)?|non-? ?aligned|unaligned|no party|non political"),
    ("NONE", r"|none|n/a|-"),
]
_COMPILED = [(code, re.compile(rf"^(?:{pattern})$", re.I)) for code, pattern in _RULES]
_LOCAL = re.compile(r"independents?\b|residents?\b|association|alliance|first\b|for \w|group$|^r4"
                    r"|\bind(?:s|ep)?\b|(?<=[a-z])Ind\b|^ind-?cons?\b", re.I)


@lru_cache(maxsize=1)
def overrides() -> dict[tuple[str, str], str]:
    """(GSS code, label) -> code. A GSS code of "*" applies to every council."""
    path = STATIC_DIR / "parties.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {(r["gss"], r["label"].strip().lower()): r["code"] for r in csv.DictReader(fh)}


@lru_cache(maxsize=1)
def _local_names() -> dict[tuple[str, str], str]:
    path = STATIC_DIR / "parties.csv"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return {(r["gss"], r["label"].strip().lower()): r["party_name"] for r in csv.DictReader(fh)
                if r["code"] == "LOCAL" and r["party_name"] and r["party_name"] != "Independent / Other"}


def local_name(label: str, gss: str = "") -> str:
    """A local party's name as Open Council Data gives it ("RFU" -> "Residents for Uttlesford"), else the label."""
    return _local_names().get((gss, label.strip().lower()), label)


def normalise(label: str | None, gss: str = "") -> str:
    """The party code for a council's label, or "" if it isn't recognised."""
    t = re.sub(r"\s+", " ", (label or "").replace("&amp;", "&")).strip().strip(".")
    for key in ((gss, t.lower()), ("*", t.lower())):
        if key in overrides():
            return overrides()[key]
    for code, rx in _COMPILED:
        if rx.match(t):
            return code
    if _LOCAL.search(t):
        return "LOCAL"
    return ""
