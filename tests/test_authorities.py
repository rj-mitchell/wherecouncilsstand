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
