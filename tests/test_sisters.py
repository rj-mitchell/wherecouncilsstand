"""Where the record meets the sister sites' (decision 31) and the home page's latest named votes (decision 32).

The MPs whose seats overlap a council: the static file built from the ONS lookup (scripts/mp_links.py), Where MPs
Stand's list of MPs as this site keeps it, and the nightly update's refresh of that list, which keeps the last good
copy when the other site can't be had. No network: Where MPs Stand is stood in for."""

from __future__ import annotations

import csv
import json
import re
from datetime import date
from pathlib import Path

import pytest
from test_pages import VOTE, site  # noqa: F401 - the fixture
from test_pipeline import BARNSLEY, GUILDFORD, settings  # noqa: F401 - the fixture
from typer.testing import CliRunner

from councils import cli, sisters, store
from councils.api.data import Data
from councils.registry import councils

ROOT = Path(__file__).resolve().parents[1]
SHELF = ROOT / "web" / "public" / "family" / "shelf.html"


def people(n: int = 650, *, seat: str = "Seat {i}", house: str = "commons") -> dict:
    """Where MPs Stand's /api/people, made up: ``n`` sitting MPs, and a peer, who is never an MP."""
    rows = [{"number": 1000 + i, "name": f"Member {i}", "slug": f"member-{i}", "house": house,
             "constituency": seat.format(i=i), "party": "Independent", "current": True} for i in range(n)]
    rows.append({"number": 9, "name": "Lord Nine", "slug": "lord-nine", "house": "lords", "constituency": None,
                 "party": "Crossbench", "current": True})
    return {"people": rows}


# The static file

def test_every_council_and_authority_has_the_seats_that_overlap_it():
    with open(sisters.CONSTITUENCIES, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert list(rows[0]) == ["gss", "pcon_code", "pcon_name", "wards"]
    assert all(re.fullmatch(r"(?:E14|W07|S14|N05)\d{6}", r["pcon_code"]) and r["pcon_name"] and int(r["wards"]) > 0
               for r in rows)
    assert len({r["pcon_code"] for r in rows}) == 650                       # the House of Commons, 2024 boundaries
    assert len({(r["gss"], r["pcon_code"]) for r in rows}) == len(rows)    # each pair once
    every = councils()
    assert {r["gss"] for r in rows} == set(every)                          # every council and authority, no other
    seats = {gss: {r["pcon_name"] for r in rows if r["gss"] == gss} for gss in ("E08000038", "E12000007",
                                                                                 "E10000016", "E47000002")}
    assert seats["E08000038"] == {"Barnsley North", "Barnsley South", "Penistone and Stocksbridge"}  # 2019 code
    assert len(seats["E12000007"]) == 75                                  # the GLA: London's 75 seats
    assert seats["E08000038"] <= seats["E47000002"]                       # South Yorkshire: its councils' seats
    assert "Canterbury" in seats["E10000016"]                             # a county: its districts' seats


def test_the_kept_list_of_mps_has_an_mp_for_every_seat():
    listing = json.loads(sisters.MPS_SEED.read_text(encoding="utf-8"))
    assert listing["source"] == "https://wherempsstand.com/api/people" and date.fromisoformat(listing["fetched"])
    assert len(listing["mps"]) >= sisters.MIN_MPS
    assert all(set(m) == {"number", "name", "slug", "constituency", "party"} for m in listing["mps"])
    assert sisters.unmatched(listing) == []


def test_seats_are_matched_by_name_without_accents_case_or_punctuation():
    assert sisters.seat_key("Ynys Môn") == sisters.seat_key("ynys mon") == "ynys mon"
    assert sisters.seat_key("Brighton Kemptown & Peacehaven") == "brighton kemptown and peacehaven"
    assert sisters.seat_key("Weston-super-Mare") == sisters.seat_key("Weston super Mare")


def test_the_spine_is_the_family_kits_own():
    spine = sisters.spine("mps")
    assert spine.startswith('<svg class="wts-spine wts-cloth--mps"') and spine in SHELF.read_text(encoding="utf-8")


# A council's page

def test_a_councils_page_lists_the_mps_whose_seats_overlap_it(site, settings):  # noqa: F811
    listing = sisters.mps_listing({"people": [
        {"number": 1, "name": "Ann North", "slug": "ann-north", "house": "commons", "constituency": "Barnsley North",
         "party": "Labour", "current": True},
        {"number": 2, "name": "Ben South", "slug": "ben-south", "house": "commons", "constituency": "Barnsley South",
         "party": "Reform UK", "current": True},
        *people(500)["people"]]}, fetched="2026-11-21")
    sisters.mps_path(settings).write_text(json.dumps(listing), encoding="utf-8")    # the update's copy

    page = site.get(f"/api/councils/{BARNSLEY}").json()["mps"]
    assert page["site"] == "Where MPs Stand" and page["fetched"] == "2026-11-21"
    assert [s["name"] for s in page["seats"]] == ["Barnsley North", "Barnsley South", "Penistone and Stocksbridge"]
    assert page["seats"][0]["mp"] == {"name": "Ann North", "party": "Labour",
                                      "url": "https://wherempsstand.com/people/1/ann-north"}
    assert page["seats"][2]["mp"] is None                       # no MP on the list: named, never linked

    html = site.get(f"/councils/{BARNSLEY}").text
    app = html[html.index('<div id="app">'):html.index("</main>")]
    section = re.search(r'<section class="seats".*?</section>', app, re.S).group(0)
    assert '<h2 id="mps-heading">MPs whose seats overlap this council</h2>' in section
    assert '<p class="sister-name">On Where MPs Stand</p>' in section
    assert f'<span class="spine" aria-hidden="true">{sisters.spine("mps")}</span>' in section
    assert ('<li><a href="https://wherempsstand.com/people/1/ann-north">Ann North</a>, Labour, MP for Barnsley '
            "North</li>") in section
    assert "<li>Penistone and Stocksbridge: no MP listed on Where MPs Stand</li>" in section
    assert section.count("<a ") == 2
    # the seats come before the named votes, and the description and structured data say nothing of them
    assert app.index("MPs whose seats overlap") < app.index("<h2>Named votes")
    assert "Ann North" not in html[:html.index("<body")]


def test_an_authoritys_page_lists_the_mps_whose_seats_overlap_its_area(site):  # noqa: F811
    html = site.get("/councils/E12000007").text
    assert "MPs whose seats overlap this authority" in html and "75 Westminster constituencies" in html


# The nightly update's refresh

def test_the_update_refreshes_the_list_and_keeps_the_last_good_copy_if_it_cannot(settings, monkeypatch):  # noqa: F811
    path = sisters.mps_path(settings)
    assert not path.exists()
    assert sisters.refresh_mps(settings, fetch=lambda url: people(seat="{i} Town")) == {
        "mps": 650, "unmatched": sorted(sisters.all_seats().values())}       # made-up seats match none
    good = path.read_text(encoding="utf-8")
    assert json.loads(good)["mps"][0]["name"] == "Member 0" and "Lord Nine" not in good

    def down(url):
        raise OSError("Connection refused")

    for fetch in (down, lambda url: {"error": "maintenance"}, lambda url: people(100), lambda url: b"<html>"):
        before = path.stat().st_mtime_ns
        out = sisters.refresh_mps(settings, fetch=fetch)
        assert set(out) == {"error", "kept"} and out["kept"] == json.loads(good)["fetched"], out
        assert path.read_text(encoding="utf-8") == good and path.stat().st_mtime_ns == before
    # fewer than half the last copy is refused too, even when there are enough to be a list of MPs
    monkeypatch.setattr(sisters, "MIN_MPS", 100)
    assert "against 650 in the last copy" in sisters.refresh_mps(settings, fetch=lambda url: people(300))["error"]
    assert path.read_text(encoding="utf-8") == good
    # with no copy of its own yet, the one kept with the code is the last good copy
    path.unlink()
    out = sisters.refresh_mps(settings, fetch=down)
    assert out == {"error": "Connection refused", "kept": json.loads(sisters.MPS_SEED.read_text())["fetched"]}
    assert not path.exists()
    assert sisters.listed_mps(settings)["by_seat"]["barnsley north"]["constituency"] == "Barnsley North"


def test_the_nightly_update_records_the_refresh_in_its_summary(settings, monkeypatch):  # noqa: F811
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    monkeypatch.setattr("councils.load.update", lambda s, chosen, workers: iter([{"gss": BARNSLEY}]))
    monkeypatch.setattr("councils.index.build.update_index", lambda s, changed, embedder, max_seconds: {})
    monkeypatch.setattr("councils.index.lance.get_embedder", lambda s: None)
    monkeypatch.setattr(sisters, "_get", lambda url: (_ for _ in ()).throw(OSError("Network is unreachable")))
    CliRunner().invoke(cli.app, ["update", BARNSLEY])
    summary = json.loads((settings.data_dir / "updates.jsonl").read_text().splitlines()[-1])
    assert summary["mps"]["error"] == "Network is unreachable" and summary["mps"]["kept"]


# The home page's latest named votes

INDEX = ('<!doctype html><html lang="en-GB"><head><title>Where Councils Stand</title></head><body><main id="main">'
         '<div id="app"></div>\n      <div id="latest-votes"></div><noscript><p>This page needs JavaScript.</p>'
         "</noscript></main></body></html>")


def guildford_votes(settings, *days: date) -> list[str]:  # noqa: F811
    ids = [f"{GUILDFORD}:2:20:{n}" for n in range(len(days))]
    store.parquet.write(settings.parquet_dir, "votes", GUILDFORD, [
        {"vote_id": vote_id, "item_id": f"{GUILDFORD}:2:20", "meeting_id": f"{GUILDFORD}:2", "gss": GUILDFORD,
         "date": d, "year": d.year, "question": "motion", "outcome": "carried", "member_id": m, "name": n,
         "vote": side, "excerpt": "The motion was put to the vote and <carried>."}
        for vote_id, d in zip(ids, days, strict=True)
        for m, n, side in (("7", "McShane", "for"), ("8", "Anderson", "for"), ("9", "Spooner", "against"))])
    return ids


def test_the_home_page_lists_the_latest_named_votes_from_every_council(site, settings, tmp_path):  # noqa: F811
    (tmp_path / "dist" / "index.html").write_text(INDEX)
    guildford = guildford_votes(settings, date(2025, 3, 5))
    html = site.get("/").text
    section = re.search(r'<div id="latest-votes"><section class="latest-votes".*?</section></div>', html, re.S)
    assert section and html.index('<div id="app">') < section.start()         # outside the app, which leaves it
    text = section.group(0)
    assert '<h2 id="latest-votes-heading">Latest named votes</h2>' in text
    items = re.findall(r"<li>(.*?)</li>", text)
    assert len(items) == 2                                                    # newest first, across councils
    assert items[0].startswith(f'<a href="/votes/{guildford[0]}">Waste and Recycling Strategy</a>')
    assert '<p class="meta">Guildford Borough Council, <time datetime="2025-03-05">5 March 2025</time></p>' in items[0]
    assert '<p class="latest-result">Carried. For 2, Against 1, Abstained 0.</p>' in items[0]
    assert items[1].startswith(f'<a href="/votes/{VOTE}">Notice of Motion - Weekly Bin Collections</a>')
    assert "Barnsley Metropolitan Borough Council, <time datetime=\"2025-02-26\">26 February 2025</time>" in items[1]
    assert "Lost. For 1, Against 2, Abstained 0." in items[1]
    # each title is its vote's own page's heading
    heading = re.search(r"<h1>(.*?)</h1>", site.get(f"/votes/{guildford[0]}").text).group(1)
    assert f">{heading}</a>" in items[0]
    assert "This page needs JavaScript" not in html


def test_the_latest_named_votes_are_kept_until_the_record_changes_and_leave_out_what_is_hidden(settings):  # noqa: F811
    data = Data(settings)
    guildford_votes(settings, *[date(2025, 3, d) for d in range(1, 25)])      # 24 votes, newer than Barnsley's
    first = data.latest_votes(20)
    assert len(first) == 20 and data.latest_votes(20) is first               # kept: not made again
    assert [v["date"] for v in first] == sorted((v["date"] for v in first), reverse=True)
    assert first[0]["date"] == "2025-03-24" and all(v["council"] == "Guildford Borough Council" for v in first)
    hidden = {first[0]["vote_id"]}
    shown = data.latest_votes(20, lambda vote_id: vote_id in hidden, frozenset(hidden))
    assert first[0]["vote_id"] not in {v["vote_id"] for v in shown} and len(shown) == 20
    # the record changes: made again from it
    guildford_votes(settings, date(2025, 3, 1))
    again = data.latest_votes(20)
    assert again is not first and len(again) == 1


@pytest.mark.parametrize("partial", [False, True])
def test_a_votes_counts_are_as_the_record_has_them(partial):
    from councils.api.plaintext import latest_result

    v = {"counts": {"for": 0 if partial else 10, "against": 12, "abstain": 0}, "outcome": "lost", "partial": partial,
         "question": "motion"}
    assert latest_result(v) == ("Lost. Only one side could be read from the minutes: Against 12." if partial else
                                "Lost. For 10, Against 12, Abstained 0.")
    # a result the count contradicts is left out, as in a vote's title (api/titles.py, outcome)
    assert latest_result({**v, "counts": {"for": 30, "against": 12}, "partial": False}).startswith("For 30")
    scottish = {"counts": {"for": 20, "against": 18, "abstain": 1}, "outcome": "", "question": "motion or amendment"}
    assert latest_result(scottish) == "For the motion 20, For the amendment 18, Abstained 1."
