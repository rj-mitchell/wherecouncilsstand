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
