"""The CoINS reader (sources/coins.py), on pages saved from Glasgow's, Falkirk's and Shetland's sites in November
2026, and one of Glasgow's minutes."""

from datetime import date
from functools import partial
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from councils import committees
from councils.config import load_settings
from councils.registry import councils
from councils.sources import coins, documents
from councils.store.parquet import SCHEMAS

FIXTURES = Path(__file__).parent / "fixtures" / "coins"
GLASGOW, FALKIRK = "S12000049", "S12000014"


def page(name: str) -> str:
    return coins._decode((FIXTURES / name).read_bytes())


def test_committees_in_scope():
    bodies = {b.title: b.id for b in coins.parse_committees(page("glasgow_committees.html"))}
    assert len(bodies) == 59
    chosen = {t for t in bodies if committees.kind(t, GLASGOW)}
    # full council is named as the council; its main committee is named in data_static/committees.csv
    assert chosen == {"Glasgow City Council", "City Administration Committee"}
    assert committees.kind("Glasgow City Council", GLASGOW) == "council"
    assert committees.kind("City Administration Committee", GLASGOW) == "policy"
    assert committees.kind("Executive (2013 - June 2024)", FALKIRK) == "cabinet"
    assert committees.kind("Policy and Resources Committee", "S12000027") == "policy"
    assert committees.kind("Council Executive", "S12000040") == "cabinet"


def test_meetings_list():
    refs = coins.parse_meetings(page("glasgow_council_meetings_2024.html"))
    assert [r.id for r in refs][:2] == [19332, 19333]
    assert refs[0].date == date(2024, 2, 15) and refs[0].location == "City Chambers, Glasgow"
    assert len(coins.parse_meetings(page("glasgow_cac_meetings_2024.html"))) == 19      # page=0: every meeting


def test_agenda():
    a = coins.parse_agenda(page("glasgow_agenda_19226.html"))
    assert a.title.startswith("City Administration Committee Agenda - 25 January 2024")
    assert {"Public Agenda", "Public Minutes"} <= set(a.packs)
    assert [(i.number, i.submissions) for i in a.items] == [("1", ["111821"]), ("2", ["111822"]), ("3", ["111994"])]
    assert a.items[0].title.startswith("Financial Inclusion")


def test_agenda_sub_items_and_exempt_items():
    a = coins.parse_agenda(page("falkirk_agenda_3671.html"))
    numbers = [i.number for i in a.items]
    assert numbers[:3] == ["", "1", "2"]                  # "Record of Votes" has papers but no number
    assert "3(c)" in numbers and "10(a)" in numbers
    assert not a.packs                                    # Falkirk's minutes are papers on the next agenda
    s = coins.parse_agenda(page("shetland_agenda_8212.html"))
    assert [i.number for i in s.items][:2] == ["(a)", "(b)"]
    knab = next(i for i in s.items if i.title.startswith("Knab"))
    assert knab.restricted and not any(i.restricted for i in s.items if i is not knab)


def test_minutes_paper_found_by_its_date():
    a = coins.parse_agenda(page("falkirk_agenda_3671.html"))
    papers = [i for i in a.items if coins.MINUTE_OF.search(i.title) and date(2024, 2, 28) in documents.dates_in(i.title)]
    assert [i.submissions for i in papers] == [["21440"]]
    assert coins.parse_submission(page("falkirk_submission_21440.html")) == [
        ("3c - Minutes - 28 February 2024.pdf", "viewDoc.asp?c=e%97%9Dc%92l%80%8E")]


def test_minutes_paper_on_another_sittings_agenda():
    """Falkirk's Executive approves its minutes at its next sitting, which may be under another title, and the paper
    may be titled just "Minute". A paper is taken from another committee's agenda only if it names the committee."""
    asked = []

    class Stub:
        def page(self, rel, name, **kw):
            asked.append(rel.rsplit("=", 1)[-1])
            return page("falkirk_submission_21440.html")

    day = date(2024, 6, 11)
    nxt = coins.Agenda("Executive (including Education) Agenda", "", items=[
        coins.AgendaItem(0, "3", "Minute", "Minute of Meeting of the Executive held on 11 June 2024.", ["21881"], False),
        coins.AgendaItem(1, "4", "Minute of Special Meeting of Falkirk Council held on 11 June 2024", "", ["999"], False),
        coins.AgendaItem(2, "5", "Referral from Executive - 11 June 2024", "", ["555"], False)])
    later = [coins.Sitting(coins.MeetingRef(2, date(2024, 8, 22), ""), nxt, coins.Body(295, "Executive (including Education)"))]
    exec_ = coins.Sitting(coins.MeetingRef(1, day, ""), coins.Agenda("", ""), coins.Body(240, "Executive (2013 - June 2024)"))
    council = coins.Sitting(coins.MeetingRef(3, day, ""), coins.Agenda("", ""), coins.Body(11, "Falkirk Council"))
    assert coins._minutes_paper(Stub(), exec_, later) == "viewDoc.asp?c=e%97%9Dc%92l%80%8E" and asked == ["21881"]
    assert coins._minutes_paper(Stub(), council, later) and asked[-1] == "999"


def test_viewer_frame():
    assert coins.viewer_frame(page("glasgow_viewpack_19226.html")) == "viewSelectedPack.asp?c=P6J5FQDX81Z3ZLDN"
    assert coins.viewer_frame("<html><body>An error has occured</body></html>") is None


def test_sederunt_from_minutes_document():
    text = documents.pdf_text((FIXTURES / "glasgow_minutes_19226.pdf").read_bytes())
    att = coins.sederunt(text)
    present = [a for a in att if a.attendance == "Present"]
    assert len(present) == 21
    assert (present[0].name, present[0].role) == ("Richard Bell", "Chair")
    assert next(a for a in att if a.name == "Laura Doherty").role == "Substitute"
    assert [a.name for a in att if a.attendance == "Apologies"] == ["Susan Aitken", "Jill Brown", "Allan Casey"]
    assert [a.name for a in att if a.attendance == "In attendance"] == ["Ann Jenkins"]
    assert not any(a.name in ("M Hughes", "M Booth", "M Millar") for a in att)   # officers under "Attending"


@pytest.mark.parametrize("text, names", [
    # Glasgow, full council: one name a line, in capitals, with an office between them
    ("MINUTES\n\nPresent: The Lord Provost, Jacqueline McLaren (Chair).\n\nSAQIB AHMED\nFRANK McAVEETY\n\n"
     "LORD DEAN OF GUILD\n\nCECILIA O’LONE\n\nAttending: M Millar, Director of Legal and Administration.\n",
     ["Jacqueline McLaren", "Saqib Ahmed", "Frank McAveety", "Cecilia O'Lone"]),
    # Falkirk: "Councillors:" and titles, then officers and the first minute
    ("FALKIRK COUNCIL\n\nCouncillors:  David Aitchison\n\nDepute Provost David Balfour\nBaillie James Kerr\n\n"
     "Officers:\n\nKaren Algie, Director of Transformation\n\nFC71.  Sederunt\n\nThe sederunt was taken.",
     ["David Aitchison", "David Balfour", "James Kerr"]),
    # Falkirk's older minutes: "Councillors:" and "Officers:" side by side come out before both lists
    ("Minute of meeting of the EXECUTIVE held remotely on Tuesday 9 March 2021\n\nCouncillors:\n\nOfficers:\n\n"
     "David Alexander\nCecil Meiklejohn (Convener)\n\nKaren Algie, Head of People\nKenneth Lawrie, Chief Executive\n\n"
     "EX32.  Apologies\n", ["David Alexander", "Cecil Meiklejohn"]),
    # Glasgow's committees 2021-23: the headers, then their lists; apologies run on into the officers
    ("Present:\n\nApologies:\nAttending:\n\nCITY ADMINISTRATION COMMITTEE'S MINUTES.\n\nBy video conference, 8th April "
     "2021.\n\nSusan Aitken (Chair), Richard Bell, Euan Blockley (substitute for Kyle\nThornton), Allan Young\n\n"
     "Maureen Burke and Kyle Thornton.\n\nN Lyttle (Clerk); M Booth, Executive Director of Finance.\n",
     ["Susan Aitken", "Richard Bell", "Euan Blockley", "Allan Young", "Maureen Burke", "Kyle Thornton"]),
    # Glasgow's council, where "Present:" didn't come out of the PDF: a run of names in capitals
    ("MINUTES\n\nOF\n\nGLASGOW CITY COUNCIL.\n\nGlasgow, 19th May 2022.\n\n" + "".join(
        f"{n}\n" for n in ["SAQIB AHMED", "SUSAN AITKEN", "IMRAN ALAM", "BLAIR ANDERSON", "KEN ANDREW", "NORMAN MacLEOD",
                           "ALEXANDER BELIC", "RICHARD BELL", "JACQUELINE MCLAREN  MARTHA WARDROP", "LEÒDHAS  MASSIE"])
     + "VICE DEAN OF GUILD\n\nApology:\n\nMargaret Morgan.\n\nAttending:  E Galletly, Director of Legal.\n",
     ["Saqib Ahmed", "Susan Aitken", "Imran Alam", "Blair Anderson", "Ken Andrew", "Norman MacLeod", "Alexander Belic",
      "Richard Bell", "Jacqueline McLaren", "Martha Wardrop", "Leòdhas Massie"]),
    # Shetland: initials, remote attendance, apologies, officers
    ("Present:\nA Armitage\nC Hughson\n\nPresent via Remote Link:\nJ Fraser\n\nApologies:\nR W Thomson\n\n"
     "In Attendance (Officers):\nM Sandison, Chief Executive\n", ["A Armitage", "C Hughson", "J Fraser", "R W Thomson"]),
    # West Lothian: one sentence, lines wrapping inside names
    ("Present – Provost Cathy Muldoon (Chair), Depute Provost Peter Heggie; Councillors\nAlison Adamson, Robert  De"
     "  Bold, Moira\nMcKee Shemilt and Kirsteen\nSullivan\n\n1.\n\nDECLARATIONS OF INTEREST\n",
     ["Cathy Muldoon", "Peter Heggie", "Alison Adamson", "Robert De Bold", "Moira McKee Shemilt", "Kirsteen Sullivan"]),
    # officers listed under a second "Present:" (a misprint for "Attending") aren't members
    ("Present:\n\nRichard Bell (Chair), Saqib Ahmed.\n\nApologies:\n\nImran Alam.\n\nPresent:\n\nE Rodger (Clerk), "
     "M Millar, Director of Legal and Administration; S Millar, Chief Executive.\n",
     ["Richard Bell", "Saqib Ahmed", "Imran Alam"]),
])
def test_sederunt_layouts(text, names):
    assert [a.name for a in coins.sederunt(text)] == names


def test_members_matched_by_name_and_initials():
    ms = coins.Members([coins.Member("1", "Robert Thomson", ""), coins.Member("2", "Ryan Thomson", ""),
                        coins.Member("3", "Alex Armitage", ""), coins.Member("4", "Cecilia O'Lone", "")])
    assert ms.match("A Armitage").id == "3"
    assert ms.match("Councillor Alex Armitage").id == "3"
    assert ms.match("CECILIA O’LONE").id == "4"
    assert ms.match("R Thomson") is None                    # two members: not guessed
    assert ms.match("Ryan Thomson").id == "2"
    assert ms.match("Allan Casey") is None
    assert coins.slug("Bailie Allan Casey") == "allan-casey"


def test_members_pages():
    rows = coins.parse_members(page("glasgow_members.html"))
    assert rows[0] == ("1297", "James Adams", "Partick East/Kelvindale")
    parties = dict((name, href) for href, name in coins.parse_parties(page("glasgow_political.html")))
    assert "Scottish National Party (SNP)" in parties and "Reform UK" in parties
    assert [m[1] for m in coins.parse_members(page("glasgow_party_50.html"))] == ["Audrey Dempsey", "Thomas Kerr"]


# The whole reader, on a site made of the saved pages -------------------------------------------------------------
def _site(request: httpx.Request) -> httpx.Response:
    u = urlparse(str(request.url))
    q = {k: v[0] for k, v in parse_qs(u.query).items()}
    name = u.path.rsplit("/", 1)[-1].lower()
    served = {"allcommittees.asp": "glasgow_committees.html", "political.asp": "glasgow_political.html"}
    if name == "allmembers.asp":          # the first page of members, and two more from a party's page
        party = (FIXTURES / "glasgow_party_50.html").read_bytes()
        rows = party[party.index(b"<tr>", party.index(b"resultsHeader")):party.index(b"</table>")]
        members = (FIXTURES / "glasgow_members.html").read_bytes()
        return httpx.Response(200, content=members.replace(b"</table>", rows + b"</table>", 1))
    if name in served:
        return httpx.Response(200, content=(FIXTURES / served[name]).read_bytes())
    if name == "partymembers.asp":
        return httpx.Response(200, content=(FIXTURES / "glasgow_party_50.html").read_bytes()
                              if q.get("id") == "50" else b"<html></html>")
    if name == "allbodymeetings.asp":
        assert q.get("bodytitle") and q.get("page") == "0"       # the committee's own title, every meeting
        if q.get("MeetingYear") == "2024":
            return httpx.Response(200, content=(FIXTURES / ("glasgow_cac_meetings_2024.html" if q["bodyid"] == "1875"
                                                            else "glasgow_council_meetings_2024.html")).read_bytes())
        return httpx.Response(200, content=b"<html><table class='results'></table></html>")
    if name == "agenda.asp" and q.get("meetingid") == "19226":
        return httpx.Response(200, content=(FIXTURES / "glasgow_agenda_19226.html").read_bytes())
    if name == "viewpack.asp":
        if "Agenda.asp?meetingid=19226" not in request.headers.get("referer", ""):
            return httpx.Response(302, headers={"Location": "err.asp"})
        return httpx.Response(200, content=(FIXTURES / "glasgow_viewpack_19226.html").read_bytes())
    if name == "viewselectedpack.asp":
        return httpx.Response(200, content=(FIXTURES / "glasgow_minutes_19226.pdf").read_bytes())
    return httpx.Response(404, content=b"not found")


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    monkeypatch.setattr(coins.robots, "allowed", lambda url, ua: True)
    monkeypatch.setattr(coins.httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(_site)))
    return load_settings(**{"modgov.min_interval_seconds": 0, "modgov.retries": 1})


def test_fetch_rows_have_the_modgov_keys(settings):
    res, meetings, items, attendance = coins.fetch(settings, councils()[GLASGOW], date(2024, 1, 1),
                                                   date(2024, 1, 31))
    assert res.error == "" and res.failed == [] and res.documents_read == 1
    assert set(res.committees) == {2, 1875}
    assert [m["meeting_id"] for m in meetings] == [f"{GLASGOW}:19226"]
    assert set(meetings[0]) == set(SCHEMAS["meetings"].names)
    assert {k for it in items for k in it} == set(SCHEMAS["items"].names)
    assert set(attendance[0]) == set(SCHEMAS["attendance"].names) - {"party"}
    m = meetings[0]
    assert m["kind"] == "policy" and m["committee_id"] == 1875 and m["minutes_published"]
    assert m["minutes_document"].endswith("viewPack.asp?c=P62AFQDX81Z3ZLDNB253YXYXQAJ5I77DJ52AFQDNUT2U2UZ3")
    assert sum(len(i["minutes_text"]) for i in items) > 5000
    assert all(i["minutes_source"] in ("", "document") for i in items)
    bell = next(a for a in attendance if a["name"] == "Richard Bell")
    assert (bell["member_id"], bell["role"], bell["attendance"]) == ("2394", "Chair", "Present")
    kerr = next(a for a in attendance if a["name"] == "Thomas Kerr")
    # a party is read only from the members pages, for a current councillor at a meeting since the last election
    assert kerr["party_label"] == "Reform UK"
    assert all(a["party_label"] in ("", "Reform UK") for a in attendance)
    # names that aren't on the members pages, or at full council, aren't kept from a committee's sederunt
    assert all(a["member_id"].isdigit() for a in attendance)
    assert m["attendees"] == len(attendance)
    # a second load is read from the cache
    cache = settings.raw_dir / "coins" / GLASGOW
    assert (cache / "agenda" / "19226.html").exists() and list((cache / "documents").glob("*.pdf"))


def test_party_left_blank_before_the_last_election(settings, monkeypatch):
    monkeypatch.setattr(coins, "SCOTTISH_ELECTIONS", [date(2022, 5, 5), date(2024, 3, 1)])
    _, _, _, attendance = coins.fetch(settings, councils()[GLASGOW], date(2024, 1, 1), date(2024, 1, 31))
    assert attendance and not any(a["party_label"] or a["ward"] for a in attendance)


def test_term_start():
    assert coins._term_start(date(2026, 11, 5)) == date(2022, 5, 5)
    assert coins._term_start(date(2021, 1, 1)) == date(2017, 5, 4)


def test_robots_refusal(settings, monkeypatch):
    monkeypatch.setattr(coins.robots, "allowed", lambda url, ua: False)
    res, meetings, items, attendance = coins.fetch(settings, councils()[GLASGOW], date(2024, 1, 1), date(2024, 1, 31))
    assert res.error == "robots.txt forbids crawling" and not meetings and not items and not attendance


def test_a_refused_document_keeps_the_meeting_without_minutes(settings, monkeypatch):
    def site(request):
        if "viewselected" in str(request.url).lower():
            return httpx.Response(403, content=b"Forbidden")
        return _site(request)

    monkeypatch.setattr(coins.httpx, "Client", partial(httpx.Client, transport=httpx.MockTransport(site)))
    res, meetings, items, attendance = coins.fetch(settings, councils()[GLASGOW], date(2024, 1, 1), date(2024, 1, 31))
    assert res.documents_refused and not res.failed and res.error == ""
    assert len(meetings) == 1 and not meetings[0]["minutes_published"] and not attendance
    assert not any(i["minutes_text"] for i in items)
