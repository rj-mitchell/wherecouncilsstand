"""The daily update: cached responses are refreshed by age, a failing server never removes what is stored, and new
meetings appear. A fake web service stands in for Modern.gov (no network)."""

import os
import time
from dataclasses import replace
from datetime import date, timedelta

import pytest

from councils import ingest, load, store
from councils.config import load_settings
from councils.registry import get
from councils.sources import modgov
from councils.sources.modgov import ModgovError

GUILDFORD = "E07000209"


def committees_xml() -> str:
    return ("<committees><committee><committeeid>1</committeeid><committeetitle>Council</committeetitle>"
            "<committeedeleted>False</committeedeleted><committeeexpired>False</committeeexpired></committee>"
            "</committees>")


def meetings_xml(ids_dates) -> str:
    rows = "".join(f"<meeting><meetingid>{i}</meetingid><meetingdate>{d:%d/%m/%Y}</meetingdate>"
                   "<meetingstatus>Confirmed</meetingstatus></meeting>" for i, d in ids_dates)
    return f"<getmeetings><committee><committeemeetings>{rows}</committeemeetings></committee></getmeetings>"


def meeting_xml(i: int, d: date) -> str:
    return (f"<meeting><meetingid>{i}</meetingid><meetingdate>{d:%d/%m/%Y}</meetingdate>"
            "<meetingstatus>Confirmed</meetingstatus><minutepublished>True</minutepublished><agendaitems>"
            f"<agendaitem><agendaitemid>{i}0</agendaitemid><agendaitemtitle>Motion</agendaitemtitle>"
            "<minutesnonemptyhtmlbody>&lt;p&gt;RESOLVED that the motion be agreed by the council.&lt;/p&gt;"
            "</minutesnonemptyhtmlbody></agendaitem></agendaitems><attendees>"
            '<attendee memberid="7" name="Councillor Julia McShane" roledescription="Committee Member" '
            'attendance="Present, as expected" politicalparty="Liberal Democrat"/></attendees></meeting>')


class FakeService:
    """GetCommittees, GetMeetings and GetMeeting for one council, with a switch to make the server fail."""

    def __init__(self):
        self.meetings = [(101, date(2019, 3, 1))]
        self.down = False
        self.calls = []

    def get(self, client, op, **params):
        self.calls.append(op)
        if self.down:
            raise ModgovError("502 Bad Gateway")
        if op == "GetCommittees":
            return committees_xml()
        if op == "GetMeetings":
            return meetings_xml(self.meetings)
        return meeting_xml(int(params["lMeetingId"]), dict(self.meetings)[int(params["lMeetingId"])])


@pytest.fixture
def env(tmp_path, monkeypatch):
    s = replace(load_settings(**{"modgov.read_documents": False}), data_dir=tmp_path)
    fake = FakeService()
    monkeypatch.setattr(modgov.Client, "_get", lambda self, op, **p: fake.get(self, op, **p))
    return s, fake


def stored(s):
    return sorted(m["meeting_id"] for m in store.parquet.read(s.parquet_dir, "meetings", GUILDFORD))


def test_cached_copy_is_used_when_the_server_fails(env):
    s, fake = env
    with modgov.Client(s, GUILDFORD, "https://example.org") as c:
        assert len(c.committees()) == 1
        fake.down = True
        assert len(c.committees(refresh=True)) == 1          # the server failed: the cached copy is used
        with pytest.raises(ModgovError):
            c.meetings(1, date(2018, 5, 1), date(2019, 1, 1))  # nothing cached to fall back on


def test_responses_are_cached_gzipped_and_plain_copies_still_read(env):
    """The cache was plain XML until November 2026: an old plain copy is read, and judged by its age, as before; a
    fresh fetch replaces it with a gzipped copy."""
    import gzip

    s, fake = env
    folder = s.raw_dir / "modgov" / GUILDFORD
    with modgov.Client(s, GUILDFORD, "https://example.org") as c:
        c.committees()
        assert (folder / "committees.xml.gz").exists() and not (folder / "committees.xml").exists()
        assert "<committees>" in gzip.decompress((folder / "committees.xml.gz").read_bytes()).decode()

        (folder / "committees.xml.gz").unlink()            # as cached before November 2026
        (folder / "committees.xml").write_text(committees_xml().replace("Council", "Full Council"))
        assert c.committees(max_age_days=7)[0].title == "Full Council" and fake.calls.count("GetCommittees") == 1
        old = time.time() - 8 * 86_400
        os.utime(folder / "committees.xml", (old, old))
        assert c.committees(max_age_days=7)[0].title == "Council" and fake.calls.count("GetCommittees") == 2
        assert (folder / "committees.xml.gz").exists() and not (folder / "committees.xml").exists()


def test_meeting_list_to_today_is_fetched_again_after_a_day(env):
    s, fake = env
    with modgov.Client(s, GUILDFORD, "https://example.org") as c:
        c.meetings(1, date(2018, 5, 1), date.today())
        c.meetings(1, date(2018, 5, 1), date.today())
        assert fake.calls.count("GetMeetings") == 1
        old = time.time() - 2 * 86_400
        for p in (s.raw_dir / "modgov" / GUILDFORD / "meetings").iterdir():
            os.utime(p, (old, old))
        c.meetings(1, date(2018, 5, 1), date.today())
        assert fake.calls.count("GetMeetings") == 2


def test_update_adds_new_meetings_and_keeps_stored_ones_when_the_server_is_down(env):
    s, fake = env
    council = get(GUILDFORD)
    ingest.load(s, council)
    assert stored(s) == [f"{GUILDFORD}:101"]

    # a new meeting is held: the next day's update lists it
    fake.meetings.append((102, date.today() - timedelta(days=3)))
    old = time.time() - 2 * 86_400
    for p in (s.raw_dir / "modgov" / GUILDFORD / "meetings").iterdir():
        os.utime(p, (old, old))
    lines = list(load.update(s, [council], workers=1))
    assert lines[0]["changed"] and lines[0]["new_meetings"] == 1 and not lines[0].get("error")
    assert stored(s) == [f"{GUILDFORD}:101", f"{GUILDFORD}:102"]

    # the server is down and a meeting it would list isn't cached: nothing stored is lost
    fake.meetings.append((103, date.today() - timedelta(days=1)))
    for p in (s.raw_dir / "modgov" / GUILDFORD / "meetings").iterdir():
        os.utime(p, (old, old))
    fake.down = True
    lines = list(load.update(s, [council], workers=1))
    assert not lines[0]["changed"]
    assert stored(s) == [f"{GUILDFORD}:101", f"{GUILDFORD}:102"]

    # unchanged since the last run: reported as such, nothing parsed again
    fake.down = False
    fake.meetings.pop()
    lines = list(load.update(s, [council], workers=1))
    assert lines[0]["changed"] is False and not lines[0].get("error")


def test_a_meeting_record_without_its_date_takes_the_listed_date(env, monkeypatch):
    """Six councils failed to load (November 2026) on a meeting record whose date couldn't be read: the date the
    committee's list gave is used, and the council loads."""
    s, fake = env
    fake.meetings = [(101, date(2019, 3, 1)), (102, date(2020, 6, 4))]
    real = fake.get

    def blank_date(client, op, **params):
        text = real(client, op, **params)
        if op == "GetMeeting" and params["lMeetingId"] in (102, "102"):
            text = text.replace("<meetingdate>04/06/2020</meetingdate>", "<meetingdate></meetingdate>")
        return text

    monkeypatch.setattr(modgov.Client, "_get", lambda self, op, **p: blank_date(self, op, **p))
    council = replace(get(GUILDFORD), modgov_url="https://example.org")
    res = ingest.load(s, council)
    assert res.error == "" and res.meetings == 2 and not res.failed
    dates = {m["meeting_id"]: m["date"] for m in store.parquet.read(s.parquet_dir, "meetings", GUILDFORD)}
    assert dates[f"{GUILDFORD}:102"] == date(2020, 6, 4)


def test_a_committee_whose_meetings_cant_be_listed_stores_nothing(env, monkeypatch):
    """East Hampshire loaded with its Cabinet but not its Council (November 2026): a listing that fails is tried
    again, and if it fails twice nothing is stored, so the next load tries again."""
    s, fake = env
    monkeypatch.setattr(ingest.time, "sleep", lambda secs: None)
    real = fake.get
    failures = {"left": 2}

    def flaky(client, op, **params):
        if op == "GetMeetings" and failures["left"]:
            failures["left"] -= 1
            raise ModgovError("502 Bad Gateway")
        return real(client, op, **params)

    monkeypatch.setattr(modgov.Client, "_get", lambda self, op, **p: flaky(self, op, **p))
    council = replace(get(GUILDFORD), modgov_url="https://example.org")
    res = ingest.load(s, council)
    assert res.error.startswith("committee Council:") and stored(s) == []
    failures["left"] = 1
    res = ingest.load(s, council)
    assert res.error == "" and stored(s) == [f"{GUILDFORD}:101"]


def test_a_council_whose_meetings_keep_timing_out_is_stopped(env, monkeypatch):
    """Epping Forest's service took about 40 seconds a meeting and timed out on most (November 2026): after two
    meetings in a row time out the council is stopped, nothing is stored, and the next load tries again. A meeting
    that fails some other way, or one that loads, starts the count again."""
    import httpx

    s, fake = env
    fake.meetings = [(101 + i, date(2019, 3, 1) + timedelta(days=i)) for i in range(6)]
    real = fake.get
    timing_out = {102, 104, 105, 106}     # 103 fails another way, so 102 alone isn't two in a row
    tried = []

    def slow(client, op, **params):
        if op == "GetMeeting":
            mid = int(params["lMeetingId"])
            tried.append(mid)
            if mid in timing_out:
                raise ModgovError("The read operation timed out") from httpx.ReadTimeout("The read operation timed out")
            if mid == 103:
                raise ModgovError("502 Bad Gateway")
        return real(client, op, **params)

    monkeypatch.setattr(modgov.Client, "_get", lambda self, op, **p: slow(self, op, **p))
    council = replace(get(GUILDFORD), modgov_url="https://example.org")
    res = ingest.load(s, council)
    assert res.error.startswith("stopped after 2 meetings in a row timed out (104, 105)")
    assert tried == [101, 102, 103, 104, 105] and stored(s) == []      # 106 never asked for

    timing_out.clear()
    monkeypatch.setattr(modgov.Client, "_get", lambda self, op, **p: real(self, op, **p))
    res = ingest.load(s, council)
    assert res.error == "" and len(stored(s)) == 6


def test_timeouts_are_recognised_through_the_readers_errors():
    import httpx

    from councils.sources.streak import is_timeout

    try:
        try:
            raise httpx.ReadTimeout("The read operation timed out")
        except httpx.HTTPError as e:
            raise ModgovError(str(e)) from e
    except ModgovError as e:
        assert is_timeout(e)
    assert is_timeout(RuntimeError("E07000072: ConnectTimeout: https://example.org/x"))   # how CMIS names it
    assert not is_timeout(ModgovError("502 Bad Gateway"))
