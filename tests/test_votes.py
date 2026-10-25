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


TOWN = [
    Member("21", "Councillor Ed Foley", "Deputy Mayor"),
    Member("22", "Councillor Janice Howard", "Mayor"),
    Member("23", "Councillor Tom Barlow", "Committee Member"),
    Member("24", "Councillor Ann Williams", "Committee Member"),
    Member("25", "Councillor Jo Bailey", "Committee Member"),
    Member("26", "Councillor Mo Kohler", "Committee Member"),
    Member("27", "Councillor Sue Ward", "Committee Member"),
    Member("28", "Councillor Ian Gill", "Committee Member"),
    Member("29", "Councillor Al Leigh MBE", "Committee Member"),
]


def test_not_voting_ends_a_list_and_a_named_role_counts_once():
    text = ("The Mayor called for a roll-call vote on the amendment. Voting was as follows: Votes in favour: "
            "Councillors Barlow, the Deputy Mayor, Councillor Ed Foley and Williams (3) Votes against: Councillors "
            "Ward and the Mayor, Councillor Janice Howard (2) Not voting: Councillors Bailey and Kohler (2) "
            "The Mayor declared the amendment to be lost.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "21", "24"], "against": ["27", "22"]}
    assert {v.outcome for v in found} == {"lost"}


def test_totals_after_each_list_do_not_split_the_vote():
    text = ("A recorded vote was taken. Those for the amendment: Barlow and Williams Those voting FOR – 2 Those voting "
            "against the amendment: Ward and Bailey. Those voting AGAINST – 2 ABSTENTIONS – 0 Upon being put to the "
            "vote, the amendment was lost.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "24"], "against": ["27", "25"]}
    assert len({v.block for v in found}) == 1


def test_counts_first_then_one_list_belongs_to_the_side_with_that_count():
    text = ("A vote was taken on the Substantive Motion, where there appeared – For - 3 Against - 0 Abstentions - 0 "
            "Barlow, Ward, Bailey The Substantive Motion was carried.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "27", "25"]}


def test_long_heading_up_to_its_colon():
    text = ("A recorded vote was then taken: For the Cabinet recommendations to Council as set out in the minutes "
            "of that meeting: Councillors Barlow, Ward, Williams (3) Against the Cabinet recommendations to Council: "
            "None (0) Abstentions: Councillors Gill, Kohler (2) With more councillors voting for than against, the "
            "resolution was carried.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "27", "24"], "abstain": ["28", "26"]}
    assert {v.outcome for v in found} == {"carried"}


def test_list_ends_at_a_new_sentence_and_outcome_before_the_vote_wins_over_a_later_one():
    text = ("The amendment was put to the vote and was lost. The voting on the amendment was as follows: In favour "
            "(2) Councillors Barlow and Williams. Against (2) Councillors Ward and Kohler. Abstentions (1) "
            "Councillor Gill. The proposed motion was then put to the meeting and was carried.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "24"], "against": ["27", "26"], "abstain": ["28"]}
    assert {v.outcome for v in found} == {"lost"}


def test_outcome_straight_after_and_honours_split_by_columns():
    text = ("Following the debate, the voting was as follows. For (3) Mr Barlow, Mr A Leigh, MBE, Ms Ward "
            "Against (1) Mrs Williams Abstain (0) Motion Carried. RESOLVED that the motion be agreed.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "29", "27"], "against": ["24"]}
    assert {v.outcome for v in found} == {"carried"}


def test_worshipful_mayor_absent_and_voting_without_those():
    text = ("Voting for the motion: Councilors T. Barlow, A. Williams. Voting against the motion: His Worshipful "
            "the Mayor Councillor Janice Howard, Ward. Absent: Councillors Gill and Kohler.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["22", "27"]}


def test_deputy_mayor_in_brackets_is_not_the_mayor():
    text = ("For the Amendment (2) - Councillors Barlow and Williams. Against the Amendment (2) - The Deputy Lord "
            "Mayor (Councillor Ed Foley) and Councillor Ward. Abstentions (1) - The Lord Mayor.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["21", "27"], "abstain": ["22"]}


def test_count_then_cllr_without_a_colon():
    text = ("The amendment was put to a recorded vote. (a) For the amendment – 2 Cllr Barlow and Cllr Williams. "
            "(b) Against the amendment - 1 Cllr Ward. (c) Abstentions – 1 Cllr Gill. 46.4 The amendment was lost.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "24"], "against": ["27"], "abstain": ["28"]}
    assert {v.outcome for v in found} == {"lost"}


def test_titles_with_full_stops_are_not_sentence_ends():
    text = "For: Mrs. Williams, Mr. T Barlow. Against: Cllr. Ward. Total against: 1 Present not voting: Gill."
    assert by_side(votes.parse(text, TOWN)) == {"for": ["24", "23"], "against": ["27"]}


def test_one_member_recorded_after_the_lists():
    text = ("The following members voted in favour of the motion: Councillor Tom Barlow Councillor Ann Williams ? "
            "The following members voted against the motion: ? Councillor Sue Ward Councillor Mo Kohler ? The Mayor "
            "abstained from voting. Following the vote, the motion was declared LOST.")
    found = votes.parse(text, TOWN)
    assert by_side(found) == {"for": ["23", "24"], "against": ["27", "26"], "abstain": ["22"]}
    assert {v.outcome for v in found} == {"lost"}
    text = ("For: Councillors Barlow and Williams. Against: Councillor Ward. Councillor Gill voted against. "
            "The amendment was carried.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["27", "28"]}


def test_years_are_not_headings():
    text = ("The budget for 2023-2027 was moved. A recorded vote was taken. For: Councillors Barlow and Williams. "
            "Against: Councillor Ward.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["27"]}


def test_both_lists_after_both_headings_are_not_read():
    text = ("The votes recorded were as follows: For the Motion (3) Against the Motion (1) Councillors Barlow, "
            "Williams, Kohler and the Mayor Councillors Ward Abstained (0) The motion was carried.")
    assert votes.parse(text, TOWN) == []


def test_surname_first_square_counts_and_mayor_in_brackets():
    text = ("FOR (2) Barlow T, Williams A. AGAINST (1) Councillor Janice Howard (Mayor). Members abstaining from the "
            "vote. Councillors Ward and Gill [2] There were no other votes.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["22"], "abstain": ["27", "28"]}


def test_count_then_full_stop():
    text = ("FOR the Amendment (2): Barlow and Williams. AGAINST the Amendment (2). Ward and Gill. ABSTENTIONS (0): "
            "The Amendment on being put, was declared LOST.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["27", "28"]}


def test_column_table_with_surname_first_cells_and_its_flattened_text():
    tables = [[["FOR", "AGAINST", "ABSTAIN"], ["BARLOW, Tom", "WARD, Sue", "GILL, Ian"], ["WILLIAMS, Ann", "", ""]]]
    found = votes.parse_tables(tables, TOWN)
    assert by_side(found) == {"for": ["23", "24"], "against": ["27"], "abstain": ["28"]}
    text = "Councillors voted as follows for the amendment: FOR AGAINST ABSTAIN BARLOW, Tom WARD, Sue GILL, Ian"
    assert votes.parse(text, TOWN) == []


def test_heading_naming_the_question_needs_no_colon():
    text = ("A recorded vote was taken as follows: For the motion: Councillors Barlow and Williams. Against the motion "
            "Councillors Ward and Gill. The motion was declared carried.")
    assert by_side(votes.parse(text, TOWN)) == {"for": ["23", "24"], "against": ["27", "28"]}
