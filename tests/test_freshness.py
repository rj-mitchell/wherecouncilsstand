"""What the site keeps between requests while the nightly update rewrites the store one council at a time
(src/councils/api/data.py): each council's pages are kept until that council's own files change, so a change to one
never throws away another's; the suppression list and hiding a page still take effect at once; and the sitemaps are
made once and kept until the record or what is hidden changes.

On the made-up record of test_pipeline (Barnsley and Guildford), with Barnsley's named vote from test_statements."""

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import pytest
from test_hidden import VOTE_PAGE, site  # noqa: F401 - the fixture
from test_pages import every_sitemap
from test_pipeline import BARNSLEY, GUILDFORD, meeting, settings  # noqa: F401 - the fixture
from test_statements import VOTE, with_vote

from councils import store, suppress
from councils.api.data import COUNCIL_TABLES, Data


def rewrite(cfg, table: str, gss: str, change=lambda r: r, more=()) -> None:
    """Write a council's file of one table again, as the update does: the same rows (or changed), and any more."""
    rows = store.parquet.read(cfg.parquet_dir, table, gss)
    store.parquet.write(cfg.parquet_dir, table, gss, [change(r) for r in rows] + list(more))


def counted(owner, name: str) -> list:
    """Count the calls of one of ``owner``'s methods (the arguments of each), still doing what it did."""
    calls, real = [], getattr(owner, name)

    def counting(*args):
        calls.append(args)
        return real(*args)

    setattr(owner, name, counting)
    return calls


@pytest.fixture
def record(settings):  # noqa: F811
    with_vote(settings)
    return Data(settings), settings


def test_a_change_to_another_council_keeps_this_councils_votes(record):
    data, cfg = record
    votes, page = data.votes(BARNSLEY), data.council(BARNSLEY)
    made = counted(data, "_votes")
    for table in COUNCIL_TABLES:
        rewrite(cfg, table, GUILDFORD)
    rewrite(cfg, "meetings", GUILDFORD, more=[meeting(GUILDFORD, 3, date(2025, 4, 2))])
    # the directory is built again (it is every council's) ...
    assert next(r for r in data.directory()["councils"] if r["gss"] == GUILDFORD)["meetings"] == 2
    # ... but Barnsley's named votes and page are as they were made, not made again
    assert data.votes(BARNSLEY) is votes and data.council(BARNSLEY)["votes"] is page["votes"] is votes
    assert data.vote(VOTE)["outcome"] == "lost" and made == []


@pytest.mark.parametrize("table", COUNCIL_TABLES)
def test_a_change_to_a_councils_own_files_makes_its_votes_again(record, table):
    data, cfg = record
    before = data.votes(BARNSLEY)
    rewrite(cfg, table, BARNSLEY)
    again = data.votes(BARNSLEY)
    assert again is not before and again == before


def test_a_changed_vote_is_shown_at_once(record):
    data, cfg = record
    assert data.vote(VOTE)["outcome"] == "lost" and data.council(BARNSLEY)["votes"][0]["outcome"] == "lost"
    rewrite(cfg, "votes", BARNSLEY, lambda r: {**r, "outcome": "carried"})
    assert data.vote(VOTE)["outcome"] == "carried" and data.council(BARNSLEY)["votes"][0]["outcome"] == "carried"
    store.parquet.write(cfg.parquet_dir, "votes", BARNSLEY, [])     # and a vote read no more is gone at once
    assert data.vote(VOTE) is None and data.council(BARNSLEY)["votes"] == []
    assert data.vote_dates() == []


def test_an_entry_on_the_suppression_list_changes_the_pages_at_once(record):
    data, cfg = record
    assert "Weekly Bin Collections" in data.council(BARNSLEY)["votes"][0]["item"]
    assert "Weekly Bin Collections" in data.vote(VOTE)["item"]
    suppress.add(cfg.data_dir, BARNSLEY, "Weekly Bin Collections")
    assert "Weekly Bin Collections" not in data.council(BARNSLEY)["votes"][0]["item"]
    page = data.vote(VOTE)
    assert "Weekly Bin Collections" not in page["item"] and "[name removed]" in page["item"]


def test_one_thread_makes_a_councils_votes_while_the_others_wait(record):
    data, _ = record
    made, real = [], data._votes

    def slowly(gss):
        made.append(gss)
        time.sleep(0.2)
        return real(gss)

    data._votes = slowly
    with ThreadPoolExecutor(8) as pool:
        got = list(pool.map(lambda _: data.votes(BARNSLEY), range(8)))
    assert made == [BARNSLEY] and all(v is got[0] for v in got) and got[0][0]["vote_id"] == VOTE


def test_the_directory_as_it_was_is_given_while_another_thread_builds_it(record):
    data, cfg = record
    assert next(r for r in data.directory()["councils"] if r["gss"] == GUILDFORD)["meetings"] == 1
    rewrite(cfg, "meetings", GUILDFORD, more=[meeting(GUILDFORD, 3, date(2025, 4, 2))])
    with data._lock:            # as if another thread were building it
        given = threading.Thread(target=lambda: data.directory())
        given.start()
        given.join(2)
        assert not given.is_alive()                 # it didn't wait
        assert next(r for r in data.directory()["councils"] if r["gss"] == GUILDFORD)["meetings"] == 1
    assert next(r for r in data.directory()["councils"] if r["gss"] == GUILDFORD)["meetings"] == 2


def test_every_named_vote_is_read_again_only_when_named_votes_change(record):
    data, cfg = record
    read = counted(data, "_read_vote_dates")
    assert [v for v, _ in data.vote_dates()] == [VOTE] and data.vote_ids() == [VOTE] and len(read) == 1
    rewrite(cfg, "meetings", GUILDFORD)
    rewrite(cfg, "attendance", BARNSLEY)
    assert data.vote_dates() == [(VOTE, "2025-02-26")] and len(read) == 1
    rewrite(cfg, "votes", GUILDFORD)
    assert data.vote_dates() == [(VOTE, "2025-02-26")] and len(read) == 2


# The sitemaps


def test_the_sitemaps_are_made_once_until_the_record_changes(site):  # noqa: F811
    c, _, parts, _ = site
    data = parts.data
    asked, read = counted(data, "vote_dates"), counted(data, "_read_vote_dates")
    first = every_sitemap(c)
    assert VOTE in first and len(asked) == 1        # the index and each sitemap it lists: made once
    assert every_sitemap(c) == first and c.get("/sitemap.xml").status_code == 200 and len(asked) == 1
    rewrite(data.settings, "meetings", GUILDFORD, more=[meeting(GUILDFORD, 3, date(2026, 4, 2))])
    again = every_sitemap(c)
    assert "<lastmod>2026-04-02</lastmod>" in again and len(asked) == 2     # made again: a council changed ...
    assert len(read) == 1                           # ... but no named vote did, so they weren't read again
    assert every_sitemap(c) == again and len(asked) == 2


def test_a_page_hidden_leaves_the_sitemaps_at_once_and_comes_back_when_shown(site):  # noqa: F811
    c, _, parts, run = site
    read = counted(parts.data, "_read_vote_dates")
    assert VOTE in every_sitemap(c)
    assert run("hide", VOTE_PAGE, "--note", "Checking a report.").exit_code == 0
    assert VOTE not in every_sitemap(c)
    assert parts.data.council(BARNSLEY)["votes"][0]["vote_id"] == VOTE     # what is kept never leaves it out
    assert run("unhide", VOTE_PAGE).exit_code == 0
    assert VOTE in every_sitemap(c) and len(read) == 1
