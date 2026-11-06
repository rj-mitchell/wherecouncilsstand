"""The verifier's reading of what is uncited: lead-ins to a quotation, and honorifics (from Where Countries Stand)."""

from councils.rag.sources import Source
from councils.rag.verify import _classify_uncited, verify

QUOTE = "The council agreed to restore weekly bin collections from April."
SRC = [Source(1, "minutes", "Full Council", "https://example/1", [QUOTE])]


def cited(text: str) -> dict:
    return {"text": text, "citations": [{"search_result_index": 0, "cited_text": QUOTE}]}


def test_a_lead_in_written_in_pieces_is_not_a_claim():
    """Found in real briefings: the model writes a lead-in in pieces, and an honorific's full stop ends no sentence."""
    blocks = [{"text": "- Members differed on how often bins should be collected, as when the Leader, Cllr. "},
              {"text": "Jones said "}, cited(f'"{QUOTE}"'),
              {"text": " The opposition then voted against every budget since 2019. "}]
    statuses = [s.status for s in verify(blocks, SRC).segments]
    assert statuses == ["connective", "connective", "cited", "unsupported"]


def test_an_honorific_does_not_split_a_lead_in_into_a_claim():
    segs = _classify_uncited("Mr. Smith, the portfolio holder, said ", next_is_cited=True)
    assert [s.status for s in segs] == ["connective"]
    # a real sentence before the lead-in is still a claim, and the text is kept as written
    segs = _classify_uncited("The vote was close. Mr. Smith said ", next_is_cited=True)
    assert [s.status for s in segs] == ["unsupported", "connective"]
    assert "".join(s.text for s in segs) == "The vote was close. Mr. Smith said "


def test_a_long_uncited_piece_still_breaks_the_lead_in():
    blocks = [{"text": "Cllr. "}, {"text": "The council has cut every library budget since 2019 and closed six branches. "},
              cited(f'"{QUOTE}"')]
    statuses = [s.status for s in verify(blocks, SRC).segments]
    assert statuses[-1] == "cited" and "unsupported" in statuses[:-1]
