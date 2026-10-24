"""Named votes and declarations of interest read from minutes text shaped like real councils' minutes."""

from councils.parse import declarations, votes
from councils.parse.votes import Member

MEMBERS = [
    Member("1", "Councillor Peter Birkinshaw", "Committee Member"),
    Member("2", "Councillor Doug Birkinshaw", "Committee Member"),
    Member("3", "Councillor Jo Carr", "Committee Member"),
    Member("4", "Councillor Sam Smith", "Committee Member"),
    Member("5", "Councillor Alan Markham", "Mayor"),
    Member("6", "Councillor Kate Andrews BEM", "Committee Member"),
    Member("7", "Councillor Lee Lowe-Flello", "Committee Member"),
    Member("8", "Councillor Ken Richardson  Msc", "Committee Member"),
]


def by_side(found):
    out = {}
    for v in found:
        out.setdefault(v.side, []).append(v.member_id or v.name)
    return out


def test_recorded_vote_with_wrapped_lines():
    text = ("Upon being put to the Vote, the\nMotion was lost.\nIn accordance with Standing\nOrder No 18(b) at the "
            "request of Councillor P Birkinshaw, supported by\nmore than 10 other Members, a recorded vote was taken "
            "on this\nMotion.\nIn favour of the\nMotion:\nCouncillors\nP Birkinshaw, Carr and Smith.\n"
            "Against the Motion:\nThe Mayor (Councillor Markham),\nand Councillors Andrews BEM, D Birkinshaw, "
            "Lowe-Flello and Richardson.\nAbstentions: None.")
    found = votes.parse(text, MEMBERS)
    assert by_side(found) == {"for": ["1", "3", "4"], "against": ["5", "6", "2", "7", "8"]}
    assert {v.outcome for v in found} == {"lost"}
    assert {v.question for v in found} == {"motion"}


def test_budget_vote_present_at_the_time_of_voting():
    text = ("In accordance with the requirements of the Local Authorities (Standing Orders) (England) (Amendment) "
            "Regulations 2014, a recorded vote was then taken. Those in favour of the motion, present at the time of "
            "voting: The Mayor (Councillor Markham) and Councillors Andrews BEM and Carr. Those against the motion, "
            "present at the time of voting: Councillors Smith and P Birkinshaw. Abstentions: Councillor "
            "Richardson. The motion was carried.")
    found = votes.parse(text, MEMBERS)
    assert by_side(found) == {"for": ["5", "6", "3"], "against": ["4", "1"], "abstain": ["8"]}
    assert {v.outcome for v in found} == {"carried"}


def test_two_votes_in_one_item():
    text = ("For the amendment: Councillors Carr and Smith. Against the amendment: Councillors Andrews BEM. "
            "The amendment was lost. For the motion: Councillors Andrews BEM and Carr. Against the motion: "
            "Councillor Smith. The motion was carried.")
    found = votes.parse(text, MEMBERS)
    assert sorted({v.block for v in found}) == [0, 1]
    assert {(v.block, v.question, v.outcome) for v in found} == {(0, "amendment", "lost"), (1, "motion", "carried")}


def test_unknown_name_kept_unmatched():
    found = votes.parse("In favour: Councillors Carr and Nobody. Against: Councillor Smith.", MEMBERS)
    assert [(v.name, v.member_id) for v in found if v.side == "for"] == [("Carr", "3"), ("Nobody", "")]


def test_ambiguous_surname_without_initial_is_unmatched():
    found = votes.parse("In favour: Councillor Birkinshaw. Against: Councillor Smith.", MEMBERS)
    assert [v.member_id for v in found if v.side == "for"] == [""]


def test_no_named_vote():
    assert votes.parse("Upon being put to the vote the motion was carried by 30 votes to 12.", MEMBERS) == []


def test_numbers_are_not_names():
    assert votes.parse("The delay for 18 months: was 168 days.", MEMBERS) == []


def test_declarations():
    text = ("Councillors Carr and Smith both declared a non-pecuniary interest in minute number 159 due to their "
            "positions on the board of Berneslai Homes. Councillor Markham declared a disclosable pecuniary "
            "interest in item 6 as a landowner and left the meeting.")
    found = declarations.parse(text, MEMBERS)
    assert [(d.member_id, d.interest) for d in found] == [("3", "non-pecuniary"), ("4", "non-pecuniary"),
                                                          ("5", "disclosable pecuniary")]
    assert "Berneslai Homes" in found[0].excerpt


def test_dashed_declaration():
    found = declarations.parse("Councillor Andrews – Item 7 – personal interest as a member of the trust.", MEMBERS)
    assert [(d.member_id, d.interest) for d in found] == [("6", "personal")]


def test_no_declarations():
    assert declarations.parse("There were no declarations of interest.", MEMBERS) == []
