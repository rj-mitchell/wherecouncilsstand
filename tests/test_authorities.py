"""England's strategic authorities (decisions 17 to 20): the registry, which of their committees are read, their members'
roles and parties, and their "control". Committee lists and meetings are real responses from the authorities' web
services (6 November 2026), trimmed, in tests/fixtures/modgov."""

import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from councils import ingest
from councils.config import load_settings
from councils.registry import (
    authorities,
    authorities_of,
    councils,
    get,
    mayor_on,
    members_of,
    shares_site_with_council,
    site_sharers,
)
from councils.sources import modgov

FIXTURES = Path(__file__).parent / "fixtures" / "modgov"
PILOT = {"greater_manchester": "E47000001", "west_midlands": "E47000007", "liverpool_city_region": "E47000004",
         "west_yorkshire": "E47000003", "south_yorkshire": "E47000002", "north_east": "E47000014",
         "west_of_england": "E47000009", "cambridgeshire_peterborough": "E47000008",
         "york_north_yorkshire": "E47000012", "east_midlands": "E47000013", "greater_lincolnshire": "E47000017",
         "devon_torbay": "E47000015", "lancashire": "E47000018"}


def test_the_registry_lists_the_twenty_authorities_and_the_pilot_by_rule():
    sa = authorities()
    assert len(sa) == 20 and all(a.nation == "england" and a.type == "strategic_authority" for a in sa)
    pilot = {a.gss for a in sa if a.modgov_status == "ok"}
    assert pilot == set(PILOT.values())
    assert get("E12000007").name == "Greater London Authority" and get("E12000007").withheld
    assert get("SA-SUSSEX-BRIGHTON").withheld                       # on East Sussex's site, which forbids reading
    assert get("E47000017").regions == ("E12000004", "E12000003")  # Greater Lincolnshire spans two regions
    assert not any(c.is_authority for c in councils().values() if c.gss.startswith(("E06", "E07", "E08")))


def test_constituent_councils_and_mayors_are_dated():
    wy = members_of("E47000003")
    assert [m.council for m in wy if m.role == "constituent"][:1] == ["E08000032"]   # Bradford, by name
    assert any(m.council == "E06000014" and m.role == "non_constituent" for m in wy)  # York
    assert {m.authority for m in authorities_of("E06000014")} == {"E47000003", "E47000012"}
    assert mayor_on("E47000007", date(2023, 1, 1)).party == "CON"      # Andy Street
    assert mayor_on("E47000007", date(2025, 1, 1)).party == "LAB"      # Richard Parker
    assert mayor_on("E47000001", date(2026, 7, 1)) is None              # between Andy Burnham and Bev Craig
    assert mayor_on("E47000003", date(2020, 1, 1)) is None              # West Yorkshire had no mayor before 2021
    assert mayor_on("E47000015", date(2026, 1, 1)) is None              # Devon and Torbay has none


def test_an_authority_on_a_councils_site_doesnt_change_the_councils_committees():
    lancs_cc, lancs_ca = get("E10000017"), get("E47000018")
    assert site_sharers(lancs_cc) == [] and shares_site_with_council(lancs_ca)


@pytest.fixture
def cached(tmp_path):
    s = replace(load_settings(), data_dir=tmp_path)

    def client(name: str, gss: str) -> modgov.Client:
        dest = tmp_path / "raw" / "modgov" / gss / "committees.xml"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(FIXTURES / f"{name}_committees.xml", dest)
        return modgov.Client(s, gss, get(gss).modgov_url)

    return client


EXPECTED = {   # committee id -> kind, as documented in data_static/committees.csv
    "greater_manchester": {136: "board", 361: "board", 424: "scrutiny", 354: "scrutiny", 355: "scrutiny",
                           363: "scrutiny", 216: "scrutiny", 148: "scrutiny", 247: "scrutiny"},
    "west_midlands": {137: "board", 138: "scrutiny", 356: "scrutiny", 240: "scrutiny", 153: "scrutiny"},
    "liverpool_city_region": {364: "board", 365: "scrutiny"},
    "west_yorkshire": {133: "board", 247: "scrutiny", 135: "scrutiny", 226: "scrutiny", 228: "scrutiny",
                       227: "scrutiny"},
    "south_yorkshire": {137: "board", 138: "scrutiny"},
    "north_east": {137: "board", 143: "scrutiny"},
    "west_of_england": {141: "board", 192: "board", 143: "scrutiny"},
    "cambridgeshire_peterborough": {141: "board", 139: "scrutiny", 182: "scrutiny"},
    "york_north_yorkshire": {138: "board", 139: "scrutiny"},
    "east_midlands": {137: "board", 138: "scrutiny"},
    "greater_lincolnshire": {137: "board", 143: "scrutiny"},
    "devon_torbay": {139: "board", 140: "scrutiny"},
    "lancashire": {1988: "board", 1990: "scrutiny"},
}


@pytest.mark.parametrize("name", sorted(PILOT))
def test_each_pilot_authoritys_board_and_scrutiny_committees_are_read(cached, name):
    gss = PILOT[name]
    with cached(name, gss) as client:
        chosen = ingest.selected_committees(client, get(gss))
    assert {cid: kind for cid, (_, kind) in chosen.items()} == EXPECTED[name]


def test_lancashire_county_councils_own_committees_are_unchanged(cached):
    with cached("lancashire", "E10000017") as client:
        chosen = ingest.selected_committees(client, get("E10000017"))
    assert sorted(kind for _, kind in chosen.values()) == ["cabinet", "council"]


def _meeting_rows(name: str, gss: str, mid: int, committee: int, title: str, kind: str = "board"):
    from lxml import etree

    from councils.sources import meeting as meeting_rows

    root = etree.fromstring((FIXTURES / f"{name}_meeting_{mid}.xml").read_bytes())
    ctx = meeting_rows.Context(gss, get(gss).name, get(gss).modgov_url, committee, title, kind)
    return meeting_rows.rows(root, ctx)


def test_members_roles_parties_and_who_is_named(tmp_path):
    """West Yorkshire's board, 22 January 2026: the mayor, the five councils' leaders, York's members (a
    non-constituent council), members for political balance, substitutes, the business board's chair and her
    substitute (not councillors), a guest and an officer. Leeds is stored here (one made-up row), so Alan Lamb's party
    is taken from Leeds' record, not the authority's."""
    from councils import authority, store
    from councils.parse.redact import REMOVED

    leeds = "E08000035"
    store.parquet.write(tmp_path, "meetings", leeds, [{"meeting_id": f"{leeds}:9", "gss": leeds, "kind": "council",
                                                       "date": date(2025, 11, 12)}])
    store.parquet.write(tmp_path, "attendance", leeds, [
        {"meeting_id": f"{leeds}:9", "gss": leeds, "date": date(2025, 11, 12), "year": 2025, "member_id": "77",
         "member_type": "U", "name": "Councillor Alan Lamb", "role": "Committee Member", "attendance": "Present",
         "party_label": "Conservative", "party": "CON", "ward": ""}])
    meeting, items, att = _meeting_rows("west_yorkshire", "E47000003", 1501, 133, "Combined Authority Board")
    rows, removed = authority.classify(att, get("E47000003"), tmp_path)
    by = {r["name"]: r for r in rows}
    assert by["Mayor Tracy Brabin"]["member_role"] == "mayor" and by["Mayor Tracy Brabin"]["party"] == "LAB"
    hinchcliffe = by["Councillor Susan Hinchcliffe"]
    assert hinchcliffe["member_role"] == "constituent" and hinchcliffe["home_gss"] == "E08000032"
    assert hinchcliffe["party"] == "LAB" and hinchcliffe["party_source"] == "authority"   # Bradford isn't stored here
    assert by["Councillor Claire Douglas"]["member_role"] == "non_constituent"                # York
    assert by["Councillor Matthew Morley"]["member_role"] == "substitute"
    lamb = by["Councillor Alan Lamb"]
    assert lamb["party"] == "CON" and lamb["party_source"] == "home council" and lamb["home_gss"] == leeds
    appointed = [r for r in rows if r["member_role"] == "appointed"]
    assert len(appointed) == 2 and all(r["name"] == REMOVED and not r["member_id"] for r in appointed)
    assert removed == ["Mandy Ridyard", "Asma Iqbal"] or sorted(removed) == ["Asma Iqbal", "Mandy Ridyard"]
    assert not any(r["role"] in ("Officer", "Guest") for r in rows)
    text = "Mandy Ridyard reported on the Business Board. Ms Ridyard thanked members. M Ridyard left."
    assert "Ridyard" not in authority.remove_names(text, removed)


def test_the_mayor_is_told_by_name_on_the_date():
    """Greater Manchester, 27 June 2025: "GM Mayor Andy Burnham"; leaders listed by their council's short name or
    abbreviation ("Tameside MBC", "Trafford")."""
    from councils import authority

    meeting, items, att = _meeting_rows("greater_manchester", "E47000001", 5831, 136,
                                        "Greater Manchester Combined Authority")
    assert meeting["items_with_minutes"] == 0       # its minutes are published as a document on a later agenda
    rows, removed = authority.classify(att, get("E47000001"), Path("/nonexistent"))
    roles = {r["name"]: r["member_role"] for r in rows}
    assert roles["GM Mayor Andy Burnham"] == "mayor"
    assert roles["Councillor Eleanor Wills"] == "constituent"
    assert {r["home_gss"] for r in rows if r["name"] == "Councillor Tom Ross"} == {"E08000009"}   # Trafford
    assert removed == [] and all(r["member_id"] for r in rows)


def test_home_councils_are_found_from_the_body_named():
    from councils.authority import home_council

    assert home_council("Tameside MBC", "E47000001") == "E08000008"
    assert home_council("Bradford Council", "E47000003") == "E08000032"
    assert home_council("City of York Council", "E47000003") == "E06000014"
    assert home_council("West Yorkshire Business Board", "E47000003") == ""
    assert home_council("Leeds City Council", "E47000003") == "E08000035"


def test_an_authority_is_loaded_like_a_council(tmp_path, monkeypatch):
    """West Yorkshire through the reader, from its own responses: the board and scrutiny committees, its meeting of
    22 January 2026 with members' roles, and no appointed member's name stored anywhere."""
    from councils import store

    s = replace(load_settings(**{"modgov.read_documents": False}), data_dir=tmp_path)

    def fake_get(self, op, **params):
        if op == "GetCommittees":
            return (FIXTURES / "west_yorkshire_committees.xml").read_text()
        if op == "GetMeetings":
            if params["lCommitteeId"] == 133:
                return (FIXTURES / "west_yorkshire_meetings_133.xml").read_text()
            return "<getmeetings></getmeetings>"
        assert params["lMeetingId"] == 1501
        return (FIXTURES / "west_yorkshire_meeting_1501.xml").read_text()

    monkeypatch.setattr(modgov.Client, "_get", fake_get)
    res = ingest.load(s, get("E47000003"), start=date(2026, 1, 1), end=date(2026, 1, 31))
    assert res.error == "" and res.meetings == 1
    assert sorted({k for _, k in res.committees.values()}) == ["board", "scrutiny"]
    (m,) = store.parquet.read(s.parquet_dir, "meetings", "E47000003")
    assert m["kind"] == "board" and m["committee_title"] == "Combined Authority Board"
    att = store.parquet.read(s.parquet_dir, "attendance", "E47000003")
    stored = repr(att) + repr(store.parquet.read(s.parquet_dir, "items", "E47000003"))
    assert "Ridyard" not in stored and "Iqbal" not in stored
    assert {a["member_role"] for a in att} >= {"mayor", "constituent", "non_constituent", "substitute", "appointed"}
