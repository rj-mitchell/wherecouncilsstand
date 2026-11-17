"""The verifier's reading of what is uncited, with this site's inputs (rag/checks.py): lead-ins to a quotation, the
honorifics councils' minutes use, and saved briefings judged again. The checks themselves are wts-core's, and are
tested there case by case; tests/test_parity.py compares them with what this site's own verifier gave."""

from councils.rag.checks import VERIFIER, rechecked
from councils.rag.sources import Source

QUOTE = "The council agreed to restore weekly bin collections from April."
SRC = [Source(1, "minutes", "Full Council", "https://example/1", [QUOTE])]


def cited(text: str) -> dict:
    return {"text": text, "citations": [{"search_result_index": 0, "cited_text": QUOTE}]}


def statuses(*blocks: dict) -> list[str]:
    return [s.status for s in VERIFIER.verify(list(blocks), SRC).segments]


def before_a_quotation(text: str) -> list[tuple[str, str]]:
    """How an uncited block is read when the block after it is a cited quotation: each part and its status."""
    segments = VERIFIER.verify([{"text": text}, cited(f'"{QUOTE}"')], SRC).segments[:-1]
    return [(s.text, s.status) for s in segments]


def shown_again(answer: dict) -> dict:
    return rechecked([{"type": "final", "answer": answer}])[0]["answer"]


def test_a_lead_in_written_in_pieces_is_not_a_claim():
    """Found in real briefings: the model writes a lead-in in pieces, and an honorific's full stop ends no sentence."""
    assert statuses({"text": "- Members differed on how often bins should be collected, as when the Leader, Cllr. "},
                    {"text": "Jones said "}, cited(f'"{QUOTE}"'),
                    {"text": " The opposition then voted against every budget since 2019. "}) == [
        "connective", "connective", "cited", "unsupported"]


def test_an_honorific_does_not_split_a_lead_in_into_a_claim():
    assert [s for _, s in before_a_quotation("Mr. Smith, the portfolio holder, said ")] == ["connective"]
    # the honorifics of councils' minutes are this site's own addition to the family's
    assert [s for _, s in before_a_quotation("The Revd. Canon Smith and Cllr. Jones said ")] == ["connective"]
    # a real sentence before the lead-in is still a claim, and the text is kept as written
    parts = before_a_quotation("The vote was close. Mr. Smith said ")
    assert [s for _, s in parts] == ["unsupported", "connective"]
    assert "".join(t for t, _ in parts) == "The vote was close. Mr. Smith said "


def test_a_long_uncited_piece_still_breaks_the_lead_in():
    got = statuses({"text": "Cllr. "},
                   {"text": "The council has cut every library budget since 2019 and closed six branches. "},
                   cited(f'"{QUOTE}"'))
    assert got[-1] == "cited" and "unsupported" in got[:-1]


def test_a_short_claim_stays_a_point_to_check_when_a_saved_briefing_is_shown_again():
    # verify() splits a whole sentence off a lead-in and marks it as a claim, however short it is
    parts = before_a_quotation("Opposition councillors criticised the budget. Cllr Jones said on 4 May that ")
    assert [s for _, s in parts] == ["unsupported", "connective"]
    answer = {"segments": [*({"text": t, "status": s} for t, s in parts), {"text": "\"it has failed\"",
                                                                         "status": "cited"}],
              "unsupported_segments": 1, "grounded_ratio": 0.3}
    # shown again, it is judged without that knowledge: being short must not clear it
    assert shown_again(answer) == answer


def test_saved_briefings_with_a_lead_in_in_pieces_are_cleared():
    # as Where MPs Stand: short uncited pieces between a lead-in and its quotation do not stop it leading in
    answer = {"segments": [{"text": "- Members differed sharply on the timetable, as when Cllr. ", "status": "unsupported"},
                           {"text": "Jones said ", "status": "connective"},
                           {"text": "\"it will be delivered\"", "status": "cited"}],
              "unsupported_segments": 1, "grounded_ratio": 0.5}
    out = shown_again(answer)
    assert [s["status"] for s in out["segments"]] == ["connective", "connective", "cited"]
    assert out["unsupported_segments"] == 0 and out["grounded_ratio"] == 1.0
    # a briefing written under today's rules carries their number, and is not judged again
    assert shown_again({**answer, "rules": VERIFIER.rules_version}) == {**answer, "rules": VERIFIER.rules_version}


def test_a_claim_above_a_lead_in_stays_a_point_to_check_when_shown_again():
    for block in ("- Spending on the scheme rose by 40% under the last administration\n- Cllr Jones said ",
                  "Was the funding cut by 40% in real terms? Cllr Jones said ",
                  "The scheme was cut by 40% in real terms! Cllr Jones said "):
        parts = before_a_quotation(block)
        assert [s for _, s in parts] == ["unsupported", "connective"], block
        answer = {"segments": [*({"text": t, "status": s} for t, s in parts),
                               {"text": "\"it has failed\"", "status": "cited"}],
                  "unsupported_segments": 1, "grounded_ratio": 0.3}
        # judged again without the block it was written in, it must not pass for the opening of the quotation
        assert shown_again(answer) == answer, block
