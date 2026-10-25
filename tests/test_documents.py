"""Minutes published only as a document."""

import json
from datetime import date

from councils.sources.documents import choose, dates_in, split_into_items


def test_dates_in_titles():
    assert date(2023, 11, 1) in dates_in("02 Minutes 011123")
    assert date(2024, 1, 17) in dates_in("Minutes 17 January 2024")
    assert date(2024, 1, 17) in dates_in("Minutes of 17th Jan 2024")
    assert date(2024, 1, 17) in dates_in("Council minutes 17.01.24")
    assert date(2024, 1, 17) in dates_in("2024-01-17 Council minutes")
    assert dates_in("Minutes") == set()


def later(d, *titles):
    return {"date": d, "earlier_minutes": json.dumps([{"title": t, "url": f"u/{t}"} for t in titles])}


def test_choose_by_date():
    ms = [later(date(2024, 2, 21), "02 Minutes 170124", "Minutes of extraordinary meeting 31 January 2024")]
    assert choose(date(2024, 1, 17), ms)["title"] == "02 Minutes 170124"
    assert choose(date(2024, 1, 31), ms)["title"].startswith("Minutes of extraordinary")
    assert choose(date(2023, 12, 1), ms) is None


def test_single_undated_document_only_from_the_next_meeting():
    assert choose(date(2024, 1, 17), [later(date(2024, 2, 21), "Minutes")])["title"] == "Minutes"
    assert choose(date(2024, 1, 17), [later(date(2024, 2, 21)), later(date(2024, 3, 1), "Minutes")]) is None


def test_split_into_items():
    items = [{"item_id": "a", "title": "Apologies for Absence"}, {"item_id": "b", "title": "Declarations of Interest"},
             {"item_id": "c", "title": "Council Tax Support Scheme 2024-25"}]
    text = ("NORTHUMBERLAND COUNTY COUNCIL\n1. APOLOGIES FOR ABSENCE\nApologies were received from Councillor X.\n"
            "2. DECLARATIONS OF INTEREST\nNone.\n3. COUNCIL TAX SUPPORT SCHEME 2024-25\nRESOLVED that the scheme be "
            "approved.")
    parts = split_into_items(text, items)
    assert parts["a"].startswith("APOLOGIES") and "Councillor X" in parts["a"]
    assert parts["c"].endswith("approved.")


def test_split_gives_up_when_titles_are_missing():
    items = [{"item_id": "a", "title": "Something else entirely"}, {"item_id": "b", "title": "Nothing like it"}]
    assert split_into_items("1. Apologies\n2. Minutes", items) is None
