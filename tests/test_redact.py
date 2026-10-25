"""Removing the names of people who aren't councillors."""

from councils.parse.redact import REMOVED, councillor_surnames, redact

COUNCILLORS = councillor_surnames(["Councillor Dave Leech", "Councillor Kate Hollingsbee", "Councillor Sir Steve "
                                   "Houghton", "Councillor Lee Lowe-Flello", "Councillor Jane Smith"])


def r(text):
    return redact(text, COUNCILLORS)[0]


def test_titled_member_of_the_public():
    assert r("Mr J Bloggs asked whether the bins would be collected.") == f"{REMOVED} asked whether the bins would be collected."


def test_councillor_written_with_a_title_is_kept():
    assert r("Mrs Hollingsbee moved the motion, seconded by Sir Steve Houghton.") == \
        "Mrs Hollingsbee moved the motion, seconded by Sir Steve Houghton."


def test_officer_name_removed_role_kept():
    assert r("Colin Carmichael, Chief Executive, explained the report.") == f"{REMOVED}, Chief Executive, explained the report."
    assert r("David Regan (Director of Public Health) presented.") == f"{REMOVED} (Director of Public Health) presented."


def test_public_speakers_and_petitioners():
    assert r("A member of the public, Anne Walker, asked about parking.") == \
        f"A member of the public, {REMOVED}, asked about parking."
    assert r("Public speaker: John Brown addressed the meeting.") == f"Public speaker: {REMOVED} addressed the meeting."
    assert r("The lead petitioner, Mrs Patel, presented the petition.") == \
        f"The lead petitioner, {REMOVED}, presented the petition."


def test_speaking_without_title():
    assert r("Sarah Green asked a question about libraries.") == f"{REMOVED} asked a question about libraries."
    assert r("Councillor Jane Smith asked a question about libraries.") == \
        "Councillor Jane Smith asked a question about libraries."


def test_places_are_not_people():
    assert r("Ewenny Road, the Chief Executive's report") == "Ewenny Road, the Chief Executive's report"
    assert r("Holy Trinity (Assistant Curate)") == "Holy Trinity (Assistant Curate)"


def test_double_barrelled_councillor():
    assert r("Mr Lowe-Flello spoke.") == "Mr Lowe-Flello spoke."


def test_count():
    assert redact("Mr A Brown and Mrs C White asked.", COUNCILLORS)[1] == 2


def test_job_titles_are_not_names():
    assert r("The Consultation, Engagement and Equalities Manager presented the plan.") == \
        "The Consultation, Engagement and Equalities Manager presented the plan."


def test_list_of_residents():
    assert r("Questions from local residents Anne Walker, David Edwards and Sarah Holmes were answered.") == \
        f"Questions from local residents {REMOVED}, {REMOVED} and {REMOVED} were answered."


def test_never_after_councillor():
    assert r("Councillor Dame Joan Scott was admitted.") == "Councillor Dame Joan Scott was admitted."


def test_councillor_by_role():
    assert r("Julia McShane, Leader of the Council, gave her report.") == \
        "Julia McShane, Leader of the Council, gave her report."


def test_named_after_an_action():
    assert r("The Leader invited Jonathan Davies from Putting Cumbria First to make his statement.") == \
        f"The Leader invited {REMOVED} from Putting Cumbria First to make his statement."
    assert r("The Mayor thanked Councillor Jane Smith.") == "The Mayor thanked Councillor Jane Smith."
