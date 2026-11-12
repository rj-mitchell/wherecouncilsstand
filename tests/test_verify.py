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


def test_a_short_claim_stays_a_point_to_check_when_a_saved_briefing_is_shown_again():
    from councils.rag.verify import _classify_uncited, recheck_flags

    # verify() splits a whole sentence off a lead-in and marks it as a claim, however short it is
    parts = _classify_uncited("Opposition councillors criticised the budget. Cllr Jones said on 4 May that ", True)
    assert [p.status for p in parts] == ["unsupported", "connective"]
    answer = {"segments": [*({"text": p.text, "status": p.status} for p in parts),
                           {"text": "\"it has failed\"", "status": "cited"}],
              "unsupported_segments": 1, "grounded_ratio": 0.3}
    # shown again, it is judged without that knowledge: being short must not clear it
    assert recheck_flags(answer) is answer


def test_saved_briefings_with_a_lead_in_in_pieces_are_cleared():
    from councils.rag.verify import recheck_flags

    # as Where MPs Stand: short uncited pieces between a lead-in and its quotation do not stop it leading in
    answer = {"segments": [{"text": "- Members differed sharply on the timetable, as when Cllr. ", "status": "unsupported"},
                           {"text": "Jones said ", "status": "connective"},
                           {"text": "\"it will be delivered\"", "status": "cited"}],
              "unsupported_segments": 1, "grounded_ratio": 0.5}
    out = recheck_flags(answer)
    assert [s["status"] for s in out["segments"]] == ["connective", "connective", "cited"]
    assert out["unsupported_segments"] == 0 and out["grounded_ratio"] == 1.0
