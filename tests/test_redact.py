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


def test_vote_heading_after_a_titled_councillor_and_mc_names():
    c = {"whiting", "baker", "streatfeild", "mcinroy"}
    text = "For (2) Mr Streatfeild, Mr M J Whiting Against (2) Mr Baker, Mr J P McInroy. Ms Ann McAllister asked"
    out, n = redact(text, c)
    assert out == "For (2) Mr Streatfeild, Mr M J Whiting Against (2) Mr Baker, Mr J P McInroy. [name removed] asked"
    assert n == 1


def test_misses_found_by_the_check():
    """Found by the check of 100 agenda items across 57 councils (docs/PILOT.md): staff named before their role
    without a comma, and members of the public in a question's header."""
    text = ("Councillor J.G. Slater accompanied by David Armiger the Chief Executive and Stephen Brown the Head of "
            "Local Government Reorganisation, left the meeting. Question 1 From: Marcus Simpson To: Cabinet Member "
            "for Strategic Planning. Question 2 From: Shibaji Shrestha To: Leader of the Council")
    out, n = redact(text, {"slater"})
    assert n == 4 and "Armiger" not in out and "Stephen Brown" not in out and "Simpson" not in out
    assert "Shrestha" not in out and "Councillor J.G. Slater" in out and "[name removed] the Chief Executive" in out
    assert "From: [name removed] To: Cabinet Member" in out
    out, n = redact("2) Question by Jane Doe be read by Lee Stevens. 3) Question from M J Ray How many", set())
    assert "Stevens" not in out and "Ray" not in out
    kept, n = redact("Councillor Kim Jones the Leader of the Council spoke.", {"jones"})
    assert n == 0 and kept.startswith("Councillor Kim Jones")


def test_second_check():
    """Found by the second check (docs/PILOT.md): clergy titled "the Right Reverend", and a public speaker named with
    their area at the start of a transcript's line."""
    out, n = redact("a vote of thanks to Right Reverend Sophie Jelley for her service", set())
    assert "Jelley" not in out and "Sophie" not in out
    out, n = redact("Thank you.\nTrevor Hammon (Ifield) It's really a question I'm hoping", set())
    assert "Hammon" not in out and "(Ifield) It's really" in out
    kept, n = redact("Kim Jones (Ifield) Thank you, Chair.", {"jones"})
    assert n == 0


def test_letters_after_a_councillors_name():
    """Found by the 100-vote check: "Richard Long, TD" gave the surname "td", so Mr R Long was removed."""
    sur = councillor_surnames(["Richard Long, TD", "Councillor Miss Phillipa Tatham BA (Hons)", "Cllr Jo Smith MBE",
                               "The Rt. Hon. the Lord Mayor, Alderman Peter Estlin", "Tim Hailes (Alderman)"])
    assert {"long", "tatham", "smith", "estlin", "hailes"} <= sur and "mayor" not in sur
    out, n = redact("For: Mr R Long and Miss Tatham.", sur)
    assert n == 0


def test_an_alderman_is_kept():
    out, n = redact("Alderman Jo Smith spoke in favour, and Ann Other addressed the meeting.", {"smith"})
    assert "Alderman Jo Smith" in out and "Ann Other" not in out


def test_patterns_found_by_the_audit():
    """Members of the public named on the live site in November 2026 (North Somerset, York, Southwark, Woking,
    Waverley), and the forms the audit found slipping through."""
    for text, gone in [
        ("Lucy Byrne, resident of Pill, addressed the meeting.", ["Lucy Byrne"]),
        ("Steve Lily, of Claremont Terrace Residents Association, spoke.", ["Steve Lily"]),
        ("Sophia McAllister, Gary Danks and Mary Knight residents of St Jame's Estate presented a petition.",
         ["Sophia McAllister", "Gary Danks", "Mary Knight"]),
        ("Margaret Ripley, a local resident aged 99, attended.", ["Margaret Ripley"]),
        ("Sarah Brown, a local resident, spoke against the proposal.", ["Sarah Brown"]),
        ("Jo Bloggs said that the scheme would affect her family.", ["Jo Bloggs"]),
        ("The Council received a petition presented by Gary Lineker regarding the closure.", ["Gary Lineker"]),
        ("The deputation, led by Ahmed Khan, raised concerns.", ["Ahmed Khan"]),
        ("Officers present: Sam Taylor, Joe Bloggs and Ann Other.", ["Sam Taylor", "Joe Bloggs", "Ann Other"]),
        ("Officers in attendance: Mike Ward (Democratic Services), Lucy Gray (Monitoring Officer).",
         ["Mike Ward", "Lucy Gray"]),
        ("Presentation of CIL Petition for Farnham – Mr Steve Dally", ["Steve Dally"]),
    ]:
        out = r(text)
        assert not any(n in out for n in gone), out
        assert REMOVED in out


def test_councillors_stay_in_the_new_patterns():
    """Councillors, known by their surnames from the attendance lists or written as "Councillor", are kept by every
    new pattern; and organisations are not taken for people."""
    for text in ["Kate Hollingsbee said that the budget was balanced.",
                 "Councillor Ann Other said that the budget was balanced.",
                 "Councillor Davies said that the scheme was good.",
                 "Dave Leech, a local resident, spoke.",
                 "The petition was presented by Councillor Jane Smith.",
                 "The Leader said that the council would consider it.",
                 "Hampshire County Council said that funding had been cut.",
                 "Network Rail said the line would close.",
                 "Petition presented by Save Our Park Campaign"]:
        assert r(text) == text


def test_a_long_list_of_names_is_read_in_time_growing_with_its_length_not_its_square():
    """A petition's hundreds of signatories, or a long run of capitalised words and commas, once took hours (the
    re-index of 19 November 2026 stopped on one item for a day): each list is now read back from what follows it."""
    import time

    from councils.parse.redact import redact

    names = ", ".join(f"Mr A B Smith Jones Brown{'e' * (i % 3)}" for i in range(3000))
    started = time.perf_counter()
    redact(names + ", residents of Pill, spoke.", set())
    redact(names + " spoke.", set())
    assert time.perf_counter() - started < 5


def test_names_before_residents_are_still_found_after_any_words_and_in_any_list():
    from councils.parse.redact import REMOVED, redact

    out, n = redact("The Chair said Ann Smith, Bob Jones and Carol Lee, residents of Pill, spoke.", set())
    assert out == f"The Chair said {REMOVED}, {REMOVED} and {REMOVED}, residents of Pill, spoke." and n == 3
    out, _ = redact("Helen Jones (resident) addressed the committee.", set())
    assert out == f"{REMOVED} (resident) addressed the committee."
