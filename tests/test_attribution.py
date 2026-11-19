"""Decision 27: a council's control is never a speaker's party. A source's title gives the council's control and,
separately, each named person's own party on the date, marked where it is not the party in control; a council's
directly elected mayor is read from its own attendance lists; and the instructions forbid presenting a point as the
controlling party's unless its speaker is of that party. The people and councils here are made up."""

from __future__ import annotations

from datetime import date

from councils.config import INSTRUCTIONS_VERSION
from councils.rag.prompts import GROUP_BY_INSTRUCTIONS, system_prompt, user_instruction
from councils.rag.sources import Lookup, not_in_control, record_source
from councils.reference import people
from councils.suppress import Suppressions

GSS = "E08000017"           # a metropolitan borough with a directly elected mayor; the people are made up
CABINET, COUNCIL = f"{GSS}:1", f"{GSS}:2"


def att(meeting: str, d: date, member_id: str, name: str, party: str, role: str = "Committee Member") -> dict:
    return {"meeting_id": meeting, "gss": GSS, "date": d, "member_id": member_id, "name": name, "role": role,
            "party": party, "party_label": party}


def lookup_for(attendance: list[dict], meetings: list[dict]) -> Lookup:
    lookup = Lookup.__new__(Lookup)
    lookup.votes, lookup.surnames, lookup.suppressions = {}, {}, Suppressions()
    lookup.people = people.build(attendance, meetings)
    return lookup


D = date(2026, 3, 2)
MEETINGS = [{"meeting_id": CABINET, "kind": "cabinet"}, {"meeting_id": COUNCIL, "kind": "council"}]
ATTENDANCE = [
    att(CABINET, D, "1", "Mayor Jo Smith", "LAB", "Chair"),
    att(CABINET, D, "2", "Councillor Sam Green", "LAB"),
    att(COUNCIL, D, "1", "Mayor Jo Smith", "LAB"),
    att(COUNCIL, D, "3", "Councillor Alex Brown", "REF", "Chair"),
    att(COUNCIL, D, "4", "Councillor Pat White", "REF"),
    att(COUNCIL, D, "5", "Councillor Lee Black", "REF"),
    att(COUNCIL, D, "2", "Councillor Sam Green", "LAB"),
]


def passage(text: str, members: list[str], **more) -> dict:
    return {"record_id": f"{CABINET}:7", "gss": GSS, "council_type": "metropolitan",
            "council_name": "Barchester Metropolitan Borough Council", "committee": "Cabinet", "kind": "cabinet",
            "date": D.isoformat(), "item_title": "Section 114 notice", "item_number": "7.", "control": "REF",
            "text": text, "url": "u", "members": [f"{GSS}:{m}" for m in members], **more}


def test_a_mayor_of_another_party_is_labelled_with_both_the_control_and_their_own_party():
    lookup = lookup_for(ATTENDANCE, MEETINGS)
    assert lookup.people[GSS].control_on(D) == "REF"
    s = record_source(1, passage("The Mayor said that the council had received a Section 114 notice.", []), lookup)
    assert "party in overall control of the council on the date: Reform UK" in s.title
    assert "directly elected mayor of the council on the date: Jo Smith (Labour; not the party in control)" in s.title
    assert s.meta["group"] == "Councils controlled by Reform UK"
    assert s.meta["named"] == ["Jo Smith, the directly elected mayor (Labour; not the party in control)"]


def test_a_councillor_of_another_party_is_marked_and_one_of_the_party_in_control_is_not():
    lookup = lookup_for(ATTENDANCE, MEETINGS)
    s = record_source(1, passage("Councillor Green moved an amendment, which Councillor White opposed.", ["2", "4"]),
                      lookup)
    assert ("councillors named in this passage: Councillor Sam Green (Labour; not the party in control); "
            "Councillor Pat White (Reform UK)") in s.title
    assert "directly elected mayor" not in s.title          # the passage doesn't speak of a mayor
    assert s.meta["named"] == ["Councillor Sam Green (Labour; not the party in control)",
                               "Councillor Pat White (Reform UK)"]


def test_no_overall_control_and_an_unrecorded_party_are_not_marked():
    assert not_in_control("LAB", "NOC") == "" and not_in_control("", "REF") == "" and not_in_control("LAB", "") == ""
    assert not_in_control("LAB", "LAB") == "" and not_in_control("LAB", "REF") == "; not the party in control"
    assert not_in_control("LOCAL:R4GV", "LOCAL:R4GV") == ""
    # at a strategic authority, "control" is its mayor's party (decision 19), and the mark says so
    assert not_in_control("CON", "MAYOR:LAB") == "; not the mayor's party"
    assert not_in_control("LAB", "MAYOR:LAB") == "" and not_in_control("CON", "SA:NONE") == ""
    lookup = lookup_for(ATTENDANCE, MEETINGS)
    s = record_source(1, passage("Councillor Green asked about the notice.", ["2"], control="NOC"), lookup)
    assert "Councillor Sam Green (Labour)" in s.title and "not the party" not in s.title


def test_a_councils_elected_mayor_is_read_from_its_own_attendance_lists():
    elected = people.is_elected_mayor
    assert elected("Elected Mayor Karen Clark", "Committee Member", "council")
    assert elected("Karen Clark", "Elected Mayor", "council")
    assert elected("Chris Cooke - Elected Mayor", "Chair", "council")
    assert elected("City Mayor Paul Dennett", "Committee Member", "council")
    assert elected("Mayor Jo Smith", "Chair", "cabinet")
    # "Mayor" and a name at full council may be a civic mayor; a civic, deputy or Lord Mayor never is the elected one
    assert not elected("Mayor Jo Smith", "Chair", "council")
    assert not elected("Councillor Jane Doe", "Mayor", "council")
    assert not elected("The Mayor, Councillor Jane Doe", "Chair", "council")
    assert not elected("Deputy Mayor Glyn Brown", "Committee Member", "cabinet")
    assert not elected("Lord Mayor Councillor Ann Grey", "Chair", "council")
    assert not elected("Civic Mayor Ann Grey", "Chair", "cabinet")
    assert [people.mayor_name(n) for n in ("Elected Mayor Karen Clark", "Chris Cooke - Elected Mayor",
                                           "City Mayor Paul Dennett", "Mayor Jo Smith")] == \
        ["Karen Clark", "Chris Cooke", "Paul Dennett", "Jo Smith"]


def test_a_council_that_gave_up_its_mayor_has_none_once_three_months_have_passed():
    c = people.build(ATTENDANCE, MEETINGS)[GSS]
    assert c.mayor_on(D) == "1" and c.mayor_on(date(2026, 5, 1)) == "1" and c.mayor_on(date(2026, 1, 1)) == "1"
    assert c.mayor_on(date(2026, 7, 1)) == "" and c.mayor_on(date(2025, 6, 1)) == ""
    lookup = lookup_for(ATTENDANCE, MEETINGS)
    later = passage("The Mayor welcomed the report.", [], date="2026-09-01")
    assert "directly elected mayor" not in record_source(1, later, lookup).title


def test_a_strategic_authoritys_mayor_is_never_read_as_a_councils():
    lookup = lookup_for(ATTENDANCE, MEETINGS)
    r = passage("The Mayor presented the budget.", [], council_type="strategic_authority", control="MAYOR:LAB")
    s = record_source(1, r, lookup)
    assert "its mayor on the date: Labour" in s.title and "directly elected mayor of the council" not in s.title


def test_the_instructions_never_give_a_point_to_the_party_in_control_unless_its_speaker_is_of_it():
    system = system_prompt(D)
    assert "12. Never present a point as the position of the party in control of a council" in system
    assert "Control is a fact about the council, not about who spoke" in system
    assert "A group says whose councils they are, never whose views" in system
    assert "Barchester (Reform UK control; directly elected mayor: Labour)" in GROUP_BY_INSTRUCTIONS["control"]
    assert GROUP_BY_INSTRUCTIONS["control"] in user_instruction("Section 114 notices?", "summary", "", "")
    # raised with the instructions, so that no briefing written under the old ones is served again
    assert INSTRUCTIONS_VERSION == "4"
