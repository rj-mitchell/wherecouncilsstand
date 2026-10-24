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


def test_for_in_ordinary_prose_is_not_a_vote():
    text = ("The Cabinet Member for: Customer Services presented the strategy. Priorities for - Regulatory, "
            "Governance and Staffing were agreed.")
    assert votes.parse(text, MEMBERS) == []


def test_single_side_after_announcement():
    text = "A recorded vote was taken. In favour of the motion: Councillors Carr and Smith. The motion was carried."
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"]}


def test_vote_table():
    from councils.parse.minutes import vote_tables

    html = ("<p>A recorded vote took place.</p><table><tr><td>Recommendation 2.4</td></tr>"
            "<tr><td>Name</td><td>For</td><td>Against</td><td>Abstain</td><td>Absent</td></tr>"
            "<tr><td>Cllr J Carr</td><td>?</td><td>&nbsp;</td><td></td><td></td></tr>"
            "<tr><td>Cllr S Smith</td><td></td><td>?</td><td></td><td></td></tr>"
            "<tr><td>Cllr K Andrews</td><td></td><td></td><td>X</td><td></td></tr>"
            "<tr><td>Cllr A Markham</td><td></td><td></td><td></td><td>?</td></tr></table>")
    found = votes.parse_tables(vote_tables(html), MEMBERS)
    assert by_side(found) == {"for": ["3"], "against": ["4"], "abstain": ["6"]}


def test_count_table_is_not_a_named_vote():
    from councils.parse.minutes import vote_tables

    html = "<table><tr><td>For</td><td>Against</td><td>Abstain</td></tr><tr><td>30</td><td>12</td><td>1</td></tr></table>"
    assert votes.parse_tables(vote_tables(html), MEMBERS) == []


def test_namely_format():
    text = ("A recorded vote was taken on the formal Council Tax resolutions resulting as follows: For the resolutions "
            "3 votes (namely, the Mayor, Councillors Carr and Smith) Against the resolutions None Abstentions 1 vote "
            "(namely, Councillor Andrews)")
    found = votes.parse(text, MEMBERS)
    assert by_side(found) == {"for": ["5", "3", "4"], "abstain": ["6"]}


def test_names_before_side():
    text = ("it was declared CARRIED with 3 voting in favour and 1 against. (Councillors J Carr, S Smith and "
            "K Andrews voting in favour and Councillor Markham voting against).")
    found = votes.parse(text, MEMBERS)
    assert by_side(found) == {"for": ["3", "4", "6"], "against": ["5"]}
    assert {v.outcome for v in found} == {"carried"}


def test_heading_without_colon():
    text = ("Members Voting FOR the Resolutions below Councillors Jo Carr and Sam Smith. (2) Members Voting AGAINST the "
            "Resolutions below Councillors Kate Andrews. (1) The recommendations were therefore carried.")
    found = votes.parse(text, MEMBERS)
    assert by_side(found) == {"for": ["3", "4"], "against": ["6"]}
    assert {v.outcome for v in found} == {"carried"}


def test_count_after_last_name():
    found = votes.parse("For the Motion – Councillors Carr and Smith (2) Against the Motion – Councillor "
                        "Andrews (1)", MEMBERS)
    assert by_side(found) == {"for": ["3", "4"], "against": ["6"]}


def test_heading_ending_in_count_and_full_stop():
    text = ("FOR the Amendment (2): Carr and Smith. AGAINST the Amendment (0). ABSTAIN the Amendment (1): Andrews.")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "abstain": ["6"]}


def test_names_after_none_are_not_guessed():
    text = ("A recorded vote was taken: FOR – Councillors: Carr Smith AGAINST – None ABSTENTIONS – None "
            "Councillors: Andrews Markham RESOLVED – that the tax base be noted.")
    assert votes.parse(text, MEMBERS) == []


def test_long_heading_before_colon():
    text = ("Members Voting FOR the proposal to add to the budget for the Town Hall Refurbishment: Councillors Jo Carr "
            "and Sam Smith (2) Members voting AGAINST the proposal: Councillors Kate Andrews (1)")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "against": ["6"]}


def test_the_mayor_role():
    members = MEMBERS + [Member("9", "Councillor Pat Ray", "The Mayor")]
    members = [m for m in members if m.member_id != "5"]
    found = votes.parse("For: The Mayor; Councillors Carr. Against: Councillor Smith.", members)
    assert by_side(found)["for"] == ["9", "3"]


def test_counts_typos_and_lost_ticks():
    text = ("the votes were cast as follows:- FOR: 2:- Carr, S. Smith AGAINST: 1:- Andrews ABTENTIONS: 1:- Markham "
            "1. County Council RESOLVED")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "against": ["6"], "abstain": ["5"]}
    text = "A recorded vote was held: For:?Carr; Smith (2) Against:?(0) Abstain:? Andrews (1) ? The motion was CARRIED."
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "abstain": ["6"]}


def test_list_ends_at_next_sentence():
    text = ("In Favour of the amendment – Councillors J. Carr, S. Smith. Against the amendment – Councillors K. Andrews, "
            "A. Markham. The vote on the amendment was not carried.")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "against": ["6", "5"]}


def test_voting_to_abstain():
    text = ("Members Voting FOR the Motion: Councillors Jo Carr (1). Members voting AGAINST the Motion: Councillors Sam "
            "Smith and Kate Andrews (2). Members voting to ABSTAIN on the Motion: Councillor Alan Markham (1).")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3"], "against": ["4", "6"], "abstain": ["5"]}


def test_election_of_a_person_is_not_a_motion_vote():
    assert votes.parse("For Councillor Sam Smith", MEMBERS) == []
    text = ("A recorded vote was taken. FOR COUNCILLOR SMITH: Councillors Carr and Andrews (2). FOR COUNCILLOR "
            "MARKHAM: Councillors Markham (1). ABSTENTIONS: None (0).")
    assert votes.parse(text, MEMBERS) == []


def test_list_ends_before_voting_figures():
    text = ("FOR: Councillors Carr and Smith (2). AGAINST: Councillor Andrews (1). ABSTENTIONS: Councillor Markham (1). "
            "(Voting figures: 2 for, 1 against, 1 abstention).")
    assert by_side(votes.parse(text, MEMBERS)) == {"for": ["3", "4"], "against": ["6"], "abstain": ["5"]}


def test_roles_that_are_not_councillors():
    from councils.extract import is_councillor

    assert all(is_councillor(r) for r in ["Committee Member", "Chair", "The Mayor", "Vice-Chair", "Leader",
                                          "Portfolio Holder", "Substitute", "Councillor Also Present"])
    assert not any(is_councillor(r) for r in ["Officer", "Committee Officer", "Democratic Services Officer", "Public",
                                              "Invitees", "Invitee/Observer", "Guest", "Co-Optee", "Council Staff",
                                              "Church Representative", "Independent Member", "Committee Clerk"])
