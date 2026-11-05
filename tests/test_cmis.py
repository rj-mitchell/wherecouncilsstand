"""The CMIS reader (sources/cmis.py), on pages saved from Norwich, Sunderland, Warwick and Nottinghamshire's sites
(November 2026), trimmed of their scripts and styles."""

import json
from datetime import date
from pathlib import Path

import pytest

from councils.config import load_settings
from councils.sources import cmis, robots

FIX = Path(__file__).parent / "fixtures" / "cmis"
NORWICH = "https://cmis.norwich.gov.uk/live"
SUNDERLAND = "https://committees.sunderland.gov.uk/committees/cmis5"


def page(name: str) -> str:
    return (FIX / name).read_text(encoding="utf-8")


def test_committees_are_found_on_the_committees_page():
    found = {c.id: c.title for c in cmis.committee_links(page("norwich_committees.html"), f"{NORWICH}/Committees.aspx")}
    assert found[2] == "Council" and found[1] == "Cabinet" and len(found) == 19


def test_other_pages_of_committees_are_followed_but_not_years_before_the_start():
    pages = cmis.committee_pages(page("sunderland_home.html"), f"{SUNDERLAND}/", SUNDERLAND)
    assert f"{SUNDERLAND}/CommitteesandNotices/CommitteesfromMay2016.aspx" in pages
    assert cmis._before(f"{SUNDERLAND}/CommitteesandNotices/2015-16.aspx", date(2018, 5, 1))
    assert not cmis._before(f"{SUNDERLAND}/CommitteesandNotices/CommitteesfromMay2016.aspx", date(2018, 5, 1))


def test_a_committees_meetings_are_paged_by_postback():
    text = page("sunderland_committee_1966.html")
    url = f"{SUNDERLAND}/CommitteesandNotices/CommitteesfromMay2016/tabid/140/ctl/ViewCMIS_CommitteeDetails/mid/585/id/1966/Default.aspx"
    refs = cmis.meeting_links(text, url)
    assert (refs[0].id, refs[0].committee_id, refs[0].date) == (11503, 1966, date(2026, 3, 4))
    assert cmis.pager(text, "gridMeetings") == (9, 10)
    assert cmis.pager_target(text, "gridMeetings", 8).endswith("gridMeetings$ctl00$ctl03$ctl01$ctl09")
    form = cmis.form_fields(text)
    assert "__VIEWSTATE" in form and not any(k.endswith("btnSubmitMeetingsFilter") for k in form)


def test_a_meeting_page_with_an_agenda_and_its_own_minutes():
    p = cmis.meeting_page(page("norwich_meeting_1506.html"), f"{NORWICH}/x")
    assert (p["committee"], p["date"], p["status"], p["location"]) == ("Council", date(2026, 1, 27), "Occurred",
                                                                       "Council chamber")
    numbers = [it["number"] for it in p["items"]]
    assert numbers[:4] == ["1", "2", "3", "4"] and "11D" in numbers
    assert p["items"][3]["title"] == "Minutes" and p["items"][8]["is_decision"]
    assert p["items"][0]["agenda_text"] == "To receive apologies for absence"
    own = cmis.own_minutes(cmis.all_documents(p), p["date"])
    assert own["title"] == "Minutes of the Full Council meeting held on 27 January 2026"
    # the minutes approved at item 4 are the previous meeting's, offered to it
    assert [d["title"] for d in cmis.earlier_minutes(p, p["date"])] == ["Minutes"]
    status = {a["name"]: a["attendance"] for a in p["attendance"]}
    assert status["Councillor Caroline Ackroyd"] == "Present" and status["Councillor Toby Bolton"] == "Apologies"
    assert status["Councillor Ash Haynes"] == "Absent"
    assert cmis.pager(page("norwich_meeting_1506.html"), "gridAttended") == (1, 2)   # 32 attended, 25 a page
    assert p["declarations"] == [{"name": "Councillor Adam Giles", "person_id": "163", "item": "11B"}]


def test_meeting_rows_have_the_columns_of_the_modern_gov_path():
    ref = cmis.MeetingRef(1506, 2, date(2026, 1, 27), f"{NORWICH}/m1506")
    committee = cmis.CommitteeRef(2, "Council", f"{NORWICH}/c2")
    m, items, att = cmis.meeting_rows("E07000148", "Norwich City Council", committee, "council", ref,
                                      page("norwich_meeting_1506.html"))
    m.pop("_documents")
    assert set(m) == {"meeting_id", "gss", "council", "committee_id", "committee_title", "kind", "date", "year",
                      "status", "location", "webcast", "minutes_published", "items", "items_with_minutes",
                      "earlier_minutes", "minutes_document", "attendees", "url"}
    assert set(items[0]) == {"item_id", "meeting_id", "gss", "date", "year", "position", "number", "title",
                             "agenda_text", "minutes_text", "minutes_source", "vote_tables", "is_decision",
                             "is_restricted", "is_call_in", "declaration_count", "documents", "url"}
    att[0].pop("_person_url")
    assert set(att[0]) == {"meeting_id", "gss", "date", "year", "member_id", "member_type", "name", "role",
                           "attendance", "party_label", "ward"}
    assert m["meeting_id"] == "E07000148:1506" and items[0]["item_id"] == "E07000148:1506:0"
    assert att[0]["member_id"] == "34"                      # CMIS's own id for the councillor
    assert next(i for i in items if i["number"] == "11B")["declaration_count"] == 1
    assert json.loads(m["earlier_minutes"])[0]["title"] == "Minutes"


def test_a_meeting_page_with_no_agenda_and_paged_attendance():
    """Sunderland enters no agenda items: the minutes are a document at the next meeting."""
    text = page("sunderland_meeting_9690.html")
    p = cmis.meeting_page(text, f"{SUNDERLAND}/x")
    assert p["items"] == [] and p["date"] == date(2019, 3, 6)
    assert cmis.pager(text, "gridAttended") == (1, 3)
    later = cmis.meeting_page(page("sunderland_meeting_9691.html"), f"{SUNDERLAND}/x")
    docs = cmis.earlier_minutes(later, later["date"])
    meetings = [{"date": later["date"], "earlier_minutes": json.dumps(docs)}]
    assert cmis.documents.choose(date(2019, 3, 6), meetings)["title"].endswith("held on 6 March 2019")
    more = cmis._root(page("sunderland_meeting_11503_attended_2.html"))
    assert cmis.pager(more, "gridAttended") == (2, 3)
    assert len(cmis.grid_attendance(more, "gridAttended", SUNDERLAND)) == 25


def test_document_titles_written_as_one_word_are_spaced_so_their_date_is_read():
    """Sunderland, 2021-22: "02-MinutesOfLastMeetingHeldOn3March2021"."""
    title = cmis.spaced("02-MinutesOfLastMeetingHeldOn3March2021")
    assert title == "02-Minutes Of Last Meeting Held On 3 March 2021"
    assert cmis.documents.dates_in(title) == {date(2021, 3, 3)} and cmis._is_minutes(title)
    assert cmis.spaced("Motion 11B - Green Amendment") == "Motion 11B - Green Amendment"
    assert cmis.spaced("Minutes 3rd March 2021") == "Minutes 3rd March 2021"


def test_variants_without_councillor_titles_and_with_exempt_sections():
    w = cmis.meeting_page(page("warwick_meeting_5272.html"), "https://estates10.warwickdc.gov.uk/cmis/x")
    assert w["attendance"][0]["name"] == "Kyn Aizlewood" and w["items"] == []
    assert cmis.own_minutes(cmis.all_documents(w), w["date"])["title"] == "Minutes Additonal Council 15 July 2026"
    n = cmis.meeting_page(page("nottinghamshire_meeting_5865.html"), "https://www.nottinghamshire.gov.uk/dms/x")
    assert n["committee"] == "Full Council" and n["webcast"]
    assert n["items"][0]["title"] == "Minutes of the meeting held on 7 December 2023"


def test_party_on_the_date_from_the_councillors_page():
    history = cmis.party_history(page("sunderland_person_1629.html"))
    assert history == [("Labour", date(2012, 5, 3), date(2016, 5, 4)), ("Labour", date(2016, 5, 5), date(2021, 5, 5))]
    assert cmis.on_date(history, date(2019, 3, 6)) == "Labour"
    assert cmis.on_date(history, date(2022, 1, 1)) == ""          # not a councillor then: never guessed
    norwich = cmis.party_history(page("norwich_person_34.html"))
    assert cmis.on_date(norwich, date(2026, 1, 27)) == "Liberal Democrats"
    assert cmis.on_date(cmis.party_history(page("norwich_person_34.html"), "grdRadWardHistory"),
                        date(2026, 1, 27)) == "Eaton"


def test_a_minutes_pdf_with_offsets_cmis_got_wrong_is_read():
    data = (FIX / "sunderland_minutes_2019-03-06.pdf").read_bytes()
    assert len(cmis.documents.pdf_text(data).strip()) < 200      # pdfminer alone can't
    text = cmis.pdf_text(data)
    assert "WEDNESDAY 6 MARCH 2019" in text
    present = cmis.present_list(text)
    assert present[0] == ("L Scanlan", "Mayor") and ("D Dixon", "") in present and len(present) == 57


def test_present_list_written_as_a_paragraph():
    text = ("Present:\n\nMINUTES\n\nFull Council\n\nTuesday, 27 January 2026\n\nCouncillors Kendrick (Lord Mayor), "
            "Wright (Deputy Lord Mayor), \nAckroyd, Caine, Sands \n(M), Sands (S), Worley-Smith \nand Young\n\n"
            "Apologies:\n\nCouncillors Bolton")
    assert cmis.present_list(text) == [("Kendrick", "Lord Mayor"), ("Wright", "Deputy Lord Mayor"), ("Ackroyd", ""),
                                       ("Caine", ""), ("Sands (M)", ""), ("Sands (S)", ""), ("Worley-Smith", ""),
                                       ("Young", "")]


def test_minutes_document_fills_the_items_or_one_minutes_item():
    meeting = {"meeting_id": "X:1", "gss": "X", "date": date(2019, 3, 6), "year": 2019, "items_with_minutes": 0,
               "attendees": 0}
    attendance: list[dict] = []
    extra = cmis.apply_minutes(meeting, [], attendance, "Present: Councillors Atkinson, Ball and Dixon, D\n\n"
                               "1. Minutes\n" + "The minutes were agreed. " * 20, "https://x/doc")
    assert [i["title"] for i in extra] == ["Minutes"] and meeting["items_with_minutes"] == 1
    assert meeting["minutes_document"] == "https://x/doc" and meeting["minutes_published"]
    # no attendance on the site: the "Present:" list, with ids made from the names
    assert [(a["member_id"], a["name"]) for a in attendance] == [
        ("atkinson", "Councillor Atkinson"), ("ball", "Councillor Ball"), ("d-dixon", "Councillor D Dixon")]


@pytest.fixture
def robots_txt(monkeypatch):
    def serve(text):
        class R:
            status_code, headers = 200, {"content-type": "text/plain"}

        R.text = text
        monkeypatch.setattr(robots.httpx, "get", lambda *a, **k: R())
        robots._parser.cache_clear()
    yield serve
    robots._parser.cache_clear()


def test_a_site_whose_robots_txt_forbids_crawling_is_not_read(robots_txt, tmp_path, monkeypatch):
    """Civica's hosted sites (*.cmis.uk.com) forbid all crawling."""
    from councils.registry import Council

    robots_txt("User-agent: *\nDisallow: /\n")
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    council = Council("E07000196", "SST", "South Staffordshire Council", "england", "district", "E12000005",
                      "https://southstaffs.cmis.uk.com", "robots", "cmis")
    res, meetings, items, attendance = cmis.fetch(load_settings(), council, date(2018, 5, 1), date(2026, 11, 5))
    assert res.error == "robots.txt forbids crawling" and meetings == items == attendance == []


def test_robots_rules_are_matched_ignoring_case(robots_txt, tmp_path, monkeypatch):
    """Nottinghamshire's robots.txt forbids its documents, /DMS/Document.ashx; the (IIS) site serves every case."""
    robots_txt("User-agent: *\nDisallow: /umbraco/\nDisallow: /DMS/Document.ashx\n")
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    with cmis.Client(load_settings(), "E10000024", "https://www.nottinghamshire.gov.uk/dms") as c:
        assert c.allowed("https://www.nottinghamshire.gov.uk/dms/Meetings.aspx")
        assert not c.allowed("https://www.nottinghamshire.gov.uk/DMS/Document.ashx?a=1")
        assert not c.allowed("https://www.nottinghamshire.gov.uk/dms/document.ashx?a=1")


def test_a_date_after_other_numbers_in_a_title_is_read():
    """Sunderland: "03-01 Minutes 15 May 2024" was read as "01 minutes 15", and the date missed (documents.py)."""
    assert cmis.documents.dates_in("03-01 Minutes 15 May 2024") == {date(2024, 5, 15)}
    assert cmis.documents.dates_in(cmis.spaced("03-01 Minutesof Last Meeting-19 th June 2024")) == {date(2024, 6, 19)}


def test_minutes_titled_without_a_year_are_matched_to_the_meeting_before():
    """Warwick: "Item 03 - Public Minutes of 7 December Cabinet meeting", at the meeting of 9 February 2023."""
    later = [{"date": date(2023, 2, 9), "docs": [
        {"title": "Item 03 - Public Minutes of 7 December Cabinet meeting", "url": "a"},
        {"title": "Item 03 - Appendices to Minute Number 64", "url": "b"}]}]
    assert cmis.choose(date(2022, 12, 7), later)["url"] == "a"
    assert cmis.choose(date(2022, 11, 2), later) is None
    assert not cmis._is_minutes("Item 03 - Appendices to Minute Number 64")
    own = [{"title": "Public Minutes of 9 February Cabinet meeting", "url": "c"}]
    assert cmis.own_minutes(own, date(2023, 2, 9))["url"] == "c"


def test_a_committees_pages_are_walked_back_to_the_start_date():
    first, page8 = page("sunderland_committee_1966.html"), page("sunderland_committee_1966_page8.html")
    posted = []

    class FakeClient:
        council = "E08000024"

        def cached(self, name):
            return None

        def page(self, name, url, refresh=False, max_age_days=None, postback=None):
            if postback is None:
                return first, True
            posted.append(postback[1])
            return page8, True

    committee = cmis.CommitteeRef(1966, "Council", f"{SUNDERLAND}/c1966")
    refs = cmis.list_meetings(FakeClient(), committee, date(2025, 6, 1), date(2026, 4, 1))
    assert posted == ["dnn$ctr585$ViewCommitteeDetails$gridMeetings$ctl00$ctl03$ctl01$ctl09"]   # page 8, once
    assert [r.id for r in refs] == [11499, 11500, 11501, 11502, 11503, 11699, 11504]
