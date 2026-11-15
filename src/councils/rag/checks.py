"""The checks on a briefing, as this site runs them: the Where They Stand sites' shared checks (wts-core,
``wts_core.checks``) with what is this site's own passed in.

The checks themselves are the package's: every citation checked against the site's own copy of the source, every
quotation looked for word for word, every sentence with no citation classed (a claim among them is marked as a point
to check), American spellings in the model's own words made British, and judgemental words in the model's own voice
marked. What is this site's own is here:

* the words a "no records" answer opens with (rag/prompts.py tells the model to use them);
* the honorifics whose full stop ends no sentence: the family's, and four that councils' minutes use ("Cllr. Jones",
  "the Revd. Canon Smith");
* the strict form of the "note about the evidence" rule: a sentence is taken for a note about the evidence, and not
  a claim, only by the phrases this site's own verifier had. "The votes were not supplied" and "Gas was supplied to
  two million homes" are both points to check here;
* the list of loaded words: the family's, and words about a council's competence or conduct ("shambles", "chaos",
  "fiasco", "cronyism"). A briefing reports the record and others' findings, and never judges a council in its own
  voice. Ambiguous words with common neutral senses ("claims" for benefits, "extreme weather") are deliberately not
  on the list.

The pipeline runs every check with one call (``wts_core.checks.check_briefing``, in rag/pipeline.py); a saved or
cached briefing is shown through ``rechecked``.
"""

from __future__ import annotations

import re
from typing import Any

from wts_core.checks import (
    COMMON_HONORIFICS,
    COMMON_LOADED_WORDS,
    EVIDENCE_NOTES_STRICT,
    LoadedWords,
    Verifier,
)

from councils.rag.prompts import NO_RECORDS

VERIFIER = Verifier(no_records=NO_RECORDS, evidence_notes=EVIDENCE_NOTES_STRICT,
                    honorifics=(*COMMON_HONORIFICS, "Cllr", "Rev", "Revd", "Hon"))

LOADED_WORDS = LoadedWords(re.compile(
    rf"\b({COMMON_LOADED_WORDS}|shambles|shambolic|chaos|chaotic|fiasco|"
    r"spiteful|vindictive|racist|racism|bigoted|extremist|extremists|far-right|far-left|hard-left|hard-right|"
    r"loony|cronyism|cronies|wasteful|reckless|botched)\b",
    re.IGNORECASE,
))


def rechecked(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A saved or cached briefing's marks, judged again by the current checks: text since recognised as a date, a
    join or a note about the evidence is no longer marked unsupported, and a word since taken off the loaded-words
    list is no longer flagged. Nothing is ever newly marked. A briefing written under the current rules (it carries
    their number, ``rules``) keeps its marks on unsupported text as they were written."""
    return [{**e, "answer": LOADED_WORDS.still_loaded(VERIFIER.recheck(e["answer"]))}
            if e.get("type") == "final" and e.get("answer") else e for e in events]
