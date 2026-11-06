"""The reader for strategic authorities' own websites (sources/docsite.py), on pages saved from Tees Valley's, Hull and
East Yorkshire's, Cumbria's and Hampshire and the Solent's sites in November 2026, and the opening of minutes
published there."""

from datetime import date
from pathlib import Path

from councils import authority, committees
from councils.registry import councils
from councils.sources import docsite
from councils.sources.docsite import Document, Meeting

FIXTURES = Path(__file__).parent / "fixtures" / "docsite"
TV, HEY, CUMBRIA, HS = "E47000006", "E47000016", "SA-CUMBRIA", "SA-HAMPSHIRE-SOLENT"
TV_PAGE = "https://teesvalley-ca.gov.uk/about/leadership/cabinet-boards-committees/meetings/cabinet-meetings-and-papers/"


def page(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def minutes(name: str) -> list[docsite.Attendee]:
    return docsite.attendees(page(f"{name}_minutes.txt"))


def test_registry_and_committees():
    for gss in (TV, HEY, CUMBRIA, HS):
        c = councils()[gss]
        assert (c.system, c.modgov_status, c.reason) == ("docsite", "ok", "")
        own = docsite.sites()[gss]
        assert [committees.kind(x.title, gss) for x in own] == ["board", "scrutiny"]
    assert committees.kind("Audit & Governance Committee", TV) is None
    assert committees.kind("Transport Committee", TV) is None


def test_dates():
    assert docsite.leading_date("31st July 2026") == date(2026, 7, 31)
    assert docsite.leading_date("28 September 2026 @ 2.30pm Venue: Portsmouth Guildhall") == date(2026, 9, 28)
    assert docsite.leading_date("14th May 2025 (Extraordinary Meeting)") == date(2025, 5, 14)
    assert docsite.leading_date("Previous meetings 28 September 2026") is None
    assert docsite.text_date("2025.09.26 - Executive Board") == date(2025, 9, 26)
    assert docsite.text_date("Cumbria Combined Authority Board: 17 July 2026") == date(2026, 7, 17)
    d = docsite.document_dates
    assert date(2026, 9, 25) in d("Draft Minutes", "https://x/Draft-TVCA-Cabinet-minutes-25th-Sept-2026.pdf")
    assert date(2019, 6, 28) in d("Minutes", "https://x/2023/05/Minutes-280619.pdf")
    assert date(2025, 6, 18) in d("Minutes", "https://x/Confirmed-Minutes-OS-18.06.25.pdf")
    # Hampshire and the Solent's files start with the year, month and day
    assert date(2026, 9, 28) in d("Draft HSCCA Board Minutes", "https://x/2026/11/260928_Board-Minutes-Final.pdf")
    assert date(2025, 9, 26) in d("Access minutes here", "https://x/downloads/file/142/20250926-heyca-executive-board-minutes")


def test_sections_page_and_minutes_chosen():
    ms = docsite.parse_sections(page("teesvalley_cabinet_archive.html"), TV_PAGE)
    by = {m.date: m for m in ms}
    assert len(ms) == 39 and min(by) == date(2019, 6, 28) and max(by) == date(2026, 3, 20)
    ms.sort(key=lambda m: m.date)

    def chosen(d: date) -> list[str]:
        n = next(i for i, m in enumerate(ms) if m.date == d)
        return [x.url.rsplit("/", 1)[-1] for x in docsite.choose_minutes(ms[n], ms[n + 1:])]

    assert chosen(date(2019, 6, 28)) == ["Minutes-280619.pdf"]
    # the approved minutes, not the draft on the next meeting's agenda
    assert chosen(date(2024, 3, 15)) == ["Final-Cabinet-minutes-15th-March-2024-1.pdf"]
    # the annual meeting's minutes and the ordinary meeting's, held the same day
    assert chosen(date(2025, 6, 27)) == ["AGM-minutes-27-June-2025-1.pdf", "Cabinet-minutes-27-June-2025-2.pdf"]
    # no minutes of its own: the draft attached to the next meeting
    assert chosen(date(2024, 12, 20)) == ["003-DRAFT-Cabinet-minutes-20th-December-2024-1.pdf"]
    assert chosen(date(2025, 5, 14)) == []


def test_minutes_with_another_meetings_date_are_not_taken():
    own = Meeting(date(2025, 10, 15), "p", [Document("Minutes", "https://x/2025/12/DRAFT-Minutes-OS-19-November-2025.pdf")])
    assert docsite.choose_minutes(own, []) == []
    undated = Meeting(date(2026, 7, 17), "p", [Document("Board minutes", "https://x/minutes.pdf"),
                                               Document("Agenda", "https://x/agenda.pdf")])
    assert docsite.choose_minutes(undated, []) == [undated.documents[0]]


def test_sections_page_on_hampshire_and_the_solent():
    ms = docsite.parse_sections(page("hampshire_solent_board.html"), "https://hantsandsolent-ca.gov.uk/b/")
    by = {m.date: m for m in ms}
    assert set(by) == {date(2026, 7, 13), date(2026, 9, 28), date(2026, 11, 16), date(2027, 1, 11), date(2027, 3, 8)}
    assert [d.url.rsplit("/", 1)[-1] for d in docsite.choose_minutes(by[date(2026, 9, 28)], [])] == \
        ["260928_Board-Minutes-Final.pdf"]


def test_listing_pages():
    base = "https://www.cumbria-ca.gov.uk/committees/meetings-agendas-and-minutes/" \
           "cumbria-combined-authority-board-agendas-and-minutes"
    got, more = docsite.parse_listing(page("cumbria_board.html"), base, "Cumbria Combined Authority Board")
    assert got[0] == (date(2026, 3, 18), f"{base}/cumbria-combined-authority-board-18-march-2026")
    assert len(got) == 10 and more == [f"{base}?page=1"]       # the year filters aren't followed
    docs = docsite.parse_meeting_page(page("cumbria_board_2026-07-17.html"), f"{base}/x")
    assert [d.label for d in docs] == ["Cumbria Combined Authority Board agenda - 17 July 2026",
                                       "Cumbria Combined Authority Board minutes - 17 July 2026"]
    hey = "https://www.hullandeastyorkshire.gov.uk/directory/1/meetings/category/"
    got, more = docsite.parse_listing(page("hey_executive_board.html"), f"{hey}2", "Executive Board")
    assert got == [] and more == [f"{hey}15", f"{hey}8", f"{hey}21"]       # council years
    got, _ = docsite.parse_listing(page("hey_executive_board_2025-26.html"), f"{hey}8", "Executive Board")
    assert len(got) == 10 and got[3][0] == date(2025, 9, 26)
    docs = docsite.parse_meeting_page(page("hey_executive_board_2025-09-26.html"), "https://www.hullandeastyorkshire.gov.uk/r")
    m = Meeting(date(2025, 9, 26), "r", docs)
    assert [d.url.rsplit("/", 1)[-1] for d in docsite.choose_minutes(m, [])] == ["20250926-heyca-executive-board-minutes"]


def _people(found: list[docsite.Attendee]) -> list[tuple[str, str, str]]:
    return [(a.name, a.role, a.attendance) for a in found]


def test_attendance_with_a_column_of_roles():
    found = minutes("teesvalley_cabinet_2025-07-25")
    assert [(a.name, a.representing) for a in found] == [
        ("Mayor Ben Houchen", "Tees Valley Mayor"), ("Councillor Brenda Harrison", "Leader Hartlepool Borough Council"),
        ("Mayor Chris Cooke", "Leader, Middlesbrough Council"),
        ("Councillor Alec Brown", "Leader, Redcar and Cleveland Borough Council"),
        ("Councillor Lisa Evans", "Leader, Stockton-on-Tees Borough Council")]     # officers aren't kept
    found = minutes("teesvalley_cabinet_2022-07-22")      # the roles come after the list, past the first minute number
    assert [(a.name, a.representing) for a in found if a.attendance == "Present"][5:] == [
        ("Councillor Mieka Smiles", "Deputy Mayor of Middlesbrough"), ("Siobhan McArdle", "Chair of Tees Valley LEP")]
    assert ("Mayor Andy Preston", "", "Apologies") in _people(found)
    # councillors among "Officers and Others in Attendance" are kept; officers aren't
    assert [a.name for a in found if a.attendance == "In attendance"] == ["Councillor John Hobson",
                                                                          "Councillor Sandra Smith"]
    found = minutes("teesvalley_cabinet_2019-06-28")
    assert ("Mayor Andy Preston", "Mayor of Middlesbrough") in [(a.name, a.representing) for a in found]
    assert ("Darren Hankey", "Associate member", "Present") in _people(found)
    # the apologies are local enterprise partnership members and officers, not written as councillors: not kept
    assert not any(a.attendance == "Apologies" for a in found)


def test_attendance_with_councils_in_brackets():
    found = minutes("teesvalley_scrutiny_2025-06-18")
    assert len(found) == 12
    assert (found[0].name, found[0].role, found[0].representing) == ("Councillor Ian Blades", "Chair",
                                                                     "Middlesbrough Council")
    assert found[8].name == "Councillor Margaret O'Donoghue"


def test_attendance_in_sentences():
    assert _people(minutes("hey_executive_board_2025-09-26")) == [
        ("Mayor Luke Campbell", "", "Present"), ("Councillor Handley", "", "Present"),
        ("Councillor Ross", "", "Present"), ("Councillor Tock", "Substitute", "Present"),
        ("Councillor Tucker", "", "Present"), ("J. Evison", "", "Present"), ("J. Adamson", "", "Present"),
        ("J. Speedy", "", "Present"), ("Councillor Dad", "", "Apologies")]
    assert minutes("hey_executive_board_2025-09-26")[5].representing == "Humberside Police and Crime Commissioner"
    assert _people(minutes("cumbria_board_2026-07-17")) == [
        ("Councillor M Fryer", "Chair", "Present"), ("Councillor J Brook", "Vice Chair", "Present"),
        ("Councillor L Hinton", "", "Present"), ("Councillor A Jarvis", "", "Present")]
    assert _people(minutes("hampshire_solent_board_2026-09-28")) == [
        ("Councillor Adams-King", "Chair", "Present"), ("Councillor Bacon", "Vice Chair", "Present"),
        ("Councillor Bogle", "", "Present"), ("Councillor Madgwick", "", "Present"),
        ("Councillor Pitt", "", "Present"), ("Councillor Neighbour", "", "In attendance")]
    found = _people(minutes("hampshire_solent_scrutiny_2026-10-12"))
    assert found[-3:] == [("Councillor Gerald Vernon-Jackson", "Substitute", "Present"),
                          ("Councillor Steve Andrews", "", "Apologies"), ("Councillor Reuben Loake", "", "Apologies")]
    assert ("Councillor Paul Kenny", "Vice Chair", "Present") in found


def test_members_classified(tmp_path):
    """Councillors and the mayor are named; a police and crime commissioner and business board chairs are counted
    but not named (decision 20)."""
    d = date(2025, 9, 26)
    rows = [{"meeting_id": "m", "gss": HEY, "date": d, "year": 2025, "member_id": docsite.cmis.slug(a.name),
             "member_type": "", "name": a.name, "role": a.role, "attendance": a.attendance, "party_label": "",
             "ward": "", "representing": a.representing} for a in minutes("hey_executive_board_2025-09-26")]
    out, removed = authority.classify(rows, councils()[HEY], tmp_path)
    roles = [(a["name"], a["member_role"]) for a in out]
    assert roles[0] == ("Mayor Luke Campbell", "mayor") and out[0]["party"] == "REF"
    assert ("Councillor Tock", "substitute") in roles
    assert [r for n, r in roles if n == "[name removed]"] == ["appointed"] * 3
    assert set(removed) == {"J. Adamson", "J. Speedy", "J. Evison"}
    assert authority.remove_names("J. Evison asked about policing.", removed) == "[name removed] asked about policing."
    # a councillor named with the council in a column beside them is that council's member
    a = {"meeting_id": "m", "gss": TV, "date": d, "year": 2025, "member_id": "x", "member_type": "",
         "name": "Councillor Brenda Harrison", "role": "", "attendance": "Present", "party_label": "", "ward": "",
         "representing": docsite.representing_council("Leader Hartlepool Borough Council")}
    out, _ = authority.classify([a], councils()[TV], tmp_path)
    assert (out[0]["home_gss"], out[0]["member_role"]) == ("E06000001", "constituent")


def test_attendance_with_councils_after_commas():
    """Tees Valley's scrutiny minutes of 8 November 2023 write each member's council after a comma. A council is never
    read as a person (it would then be removed from the minutes as an appointed member's name)."""
    text = """Present

Members:

 Councillor Ian Haszeldine, (Chair) Darlington Borough Council

 Councillor Margaret O'Donoghue, Redcar and Cleveland Borough Council

 Councillor Steve Nelson, (Vice Chair) Hartlepool Borough Council

Officers in attendance:

 Tom Bryant, TVCA Assistant Director of Infrastructure

Apologies for absence:

Mayor Ben Houchen, Tees Valley Mayor, Councillor Stephen Harker, Darlington Borough Council,
Councillor Dennis McCabe, Middlesbrough Council, and Councillor Glyn Nightingale, Redcar
and Cleveland Borough Council.

 OSC
12/23
"""
    found = docsite.attendees(text)
    assert [(a.name, a.role, a.attendance, a.representing) for a in found] == [
        ("Councillor Ian Haszeldine", "Chair", "Present", "Darlington Borough Council"),
        ("Councillor Margaret O'Donoghue", "", "Present", "Redcar and Cleveland Borough Council"),
        ("Councillor Steve Nelson", "Vice Chair", "Present", "Hartlepool Borough Council"),
        ("Mayor Ben Houchen", "", "Apologies", "Tees Valley Mayor"),
        ("Councillor Stephen Harker", "", "Apologies", "Darlington Borough Council"),
        ("Councillor Dennis McCabe", "", "Apologies", "Middlesbrough Council"),
        ("Councillor Glyn Nightingale", "", "Apologies", "Redcar and Cleveland Borough Council")]


def test_councillors_without_their_council_are_found_at_home(tmp_path):
    """"Cllr M Fryer" and "Councillor Brook" are matched to their councils' stored records by surname and initial,
    taking their full name, council and party on the date; two who fit, or none, match nothing."""
    from councils import store

    d = date(2026, 7, 17)
    rows = {"E06000063": [("145", "Councillor Mark Fryer", "LAB"), ("170", "Councillor Lisa Hinton", "LAB"),
                          ("300", "Councillor Anne Brook", "CON")],
            "E06000064": [("2745", "Councillor Jonathan Brook", "LD")]}
    for gss, people_ in rows.items():
        store.parquet.write(tmp_path, "meetings", gss, [{"meeting_id": f"{gss}:1", "gss": gss, "kind": "council",
                                                         "date": date(2026, 5, 20), "year": 2026}])
        store.parquet.write(tmp_path, "attendance", gss, [
            {"meeting_id": f"{gss}:1", "gss": gss, "date": date(2026, 5, 20), "year": 2026, "member_id": mid,
             "member_type": "", "name": name, "role": "", "attendance": "Present", "party_label": party,
             "party": party, "ward": ""} for mid, name, party in people_])
    assert authority.find_member(tmp_path, CUMBRIA, "Councillor M Fryer", d) == ("E06000063", "145", "Mark Fryer")
    assert authority.find_member(tmp_path, CUMBRIA, "Councillor J Brook", d) == ("E06000064", "2745",
                                                                                  "Jonathan Brook")
    assert authority.find_member(tmp_path, CUMBRIA, "Councillor Brook", d) is None      # two Brooks
    assert authority.find_member(tmp_path, CUMBRIA, "Councillor Smith", d) is None
    assert authority.find_member(tmp_path, CUMBRIA, "Councillor M Fryer", date(2028, 1, 1)) is None   # over a year
    att = [{"meeting_id": "m", "gss": CUMBRIA, "date": d, "year": 2026, "member_id": "x", "member_type": "",
            "name": "Councillor Mark Fryer", "role": "Chair", "attendance": "Present", "party_label": "", "ward": "",
            "representing": "Cumberland Council"}]
    out, _ = authority.classify(att, councils()[CUMBRIA], tmp_path)
    assert (out[0]["member_role"], out[0]["party"], out[0]["party_source"]) == ("constituent", "LAB", "home council")
