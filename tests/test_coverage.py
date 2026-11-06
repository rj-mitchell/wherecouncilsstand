"""The councils page's coverage: full, partial (a gap) or not yet (not loaded)."""

from datetime import date

from councils.api.data import coverage

TODAY = date(2026, 11, 5)
GOOD = {"gss": "E07000223", "loaded": True, "with_minutes": 0.95, "from": "2018-05-24", "to": "2026-10-22"}


def test_full_when_nothing_is_missing():
    r, why = coverage(GOOD, 1000, 990, TODAY)
    assert r == "full" and "May 2018" in why[0]


def test_partial_names_each_gap():
    r, why = coverage({**GOOD, "with_minutes": 0.4, "from": "2022-03-01", "to": "2026-01-10"}, 100, 30, TODAY)
    assert r == "partial" and len(why) == 4
    assert any("40%" in w for w in why) and any("January 2026" in w for w in why)
    assert any("March 2022" in w for w in why) and any("30%" in w for w in why)
    r, why = coverage(GOOD, 0, 0, TODAY)
    assert r == "partial" and "attendance" in why[0]


def test_a_new_council_starting_late_is_not_a_gap():
    assert coverage({**GOOD, "gss": "E06000066", "from": "2023-04-03"}, 100, 100, TODAY)[0] == "full"


def test_not_yet_gives_the_reason():
    r, why = coverage({"loaded": False, "status": "robots"}, today=TODAY)
    assert r == "not_yet" and "robots.txt" in why[0]
    assert "refuses" in coverage({"loaded": False, "status": "blocked"}, today=TODAY)[1][0]


def test_no_full_council_meetings_is_a_gap():
    """Sunderland was loaded once with its Cabinet's meetings alone, and shown as fully covered."""
    r, why = coverage({**GOOD, "council_meetings": 0, "cabinet_meetings": 88}, 1000, 990, TODAY)
    assert r == "partial" and "full council" in why[0]
    assert coverage({**GOOD, "council_meetings": 70, "cabinet_meetings": 88}, 1000, 990, TODAY)[0] == "full"


def test_a_council_whose_robots_txt_forbids_reading_is_withheld_not_deleted(tmp_path, monkeypatch):
    """East Sussex was loaded before robots.txt was checked on Modern.gov sites (decision 21): its stored record is
    kept, but not shown, not indexed, not updated and not offered in the sitemap, until permission is given."""
    from dataclasses import replace
    from datetime import date

    from test_pipeline import item, meeting, member

    from councils import load, store
    from councils.api.data import Data
    from councils.config import load_settings
    from councils.index.build import passage_rows
    from councils.registry import get

    east_sussex = get("E10000011")
    assert east_sussex.withheld
    s = replace(load_settings(), data_dir=tmp_path)
    d = date(2025, 2, 11)
    gss = east_sussex.gss
    store.parquet.write(s.parquet_dir, "meetings", gss, [meeting(gss, 1, d)])
    store.parquet.write(s.parquet_dir, "items", gss, [item(gss, 1, 10, d, "Budget", "RESOLVED that the budget be "
                                                                                  "approved.")])
    store.parquet.write(s.parquet_dir, "attendance", gss, [member(gss, 1, d, "1", "Councillor A Smith", "CON")])
    store.parquet.write(s.parquet_dir, "votes", gss, [{"vote_id": f"{gss}:1:10:0", "item_id": f"{gss}:1:10",
                                                       "meeting_id": f"{gss}:1", "gss": gss, "date": d, "year": 2025,
                                                       "question": "motion", "outcome": "carried", "member_id": "1",
                                                       "name": "Smith", "vote": "for", "excerpt": ""}])
    data = Data(s)
    row = next(r for r in data.directory()["councils"] if r["gss"] == gss)
    assert not row["loaded"] and row["coverage"] == "not_yet" and row["withheld"] == {"meetings": 1}
    assert row["reasons"][0].startswith("Permission asked") and "kept" in row["reasons"][1]
    assert data.vote(f"{gss}:1:10:0") is None and data.vote_ids() == []
    assert data.council(gss)["votes"] == [] and passage_rows(gss, s) == []
    assert list(load.update(s, [east_sussex])) == []          # not asked at all
    assert store.parquet.read(s.parquet_dir, "meetings", gss)  # and nothing deleted
