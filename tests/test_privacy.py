"""The three walls the shared package checks for every site, run against this site's real pipeline, index and
tables: nothing about a reader is kept where it should not be (ADR 0012); once its day is over, a briefing's record
is tied to no one (ADR 0012 as amended for wts-core 0.3.0); and a statement under the right of reply never reaches
the model, the embedder, the search index, the record of briefings or a log (ADR 0008; decision 22).

The pipeline is the site's own (the indexer, the engine, the planner, the briefing desk and the web app) and so is
its search index (``councils.index.lance.open_index``: LanceDB, in the site's data folder), over the package's
stand-ins for the model and the embedder: a scripted model, and an embedder that records what it is given."""

import logging
import shutil

import pytest
from fastapi.testclient import TestClient
from test_api import events, rows
from test_pipeline import BARNSLEY, TODAY, FakeClient, as_model, settings  # noqa: F401 - the fixture
from typer.testing import CliRunner
from wts_core.adapters.hashing import HashingEmbedder
from wts_core.events import Block, Citation, CitationDelta, Completed, TextDelta
from wts_core.observe import LOGGER
from wts_core.ports import Usage
from wts_core.testing import (
    FixedClock,
    assert_briefings_tied_to_no_one,
    assert_no_reader_data,
    assert_statements_stay_out,
)
from wts_core.testing.index import RecordingEmbedder
from wts_core.testing.models import ScriptedModel

from councils import cli
from councils.api.app import create_app, start_logging
from councils.engine import Engine
from councils.index.build import Indexer, embed_pending
from councils.index.lance import open_index
from councils.rag.pipeline import Pipeline

QUOTED = "Councillor Kitching moved that weekly bin collections be restored."
QUESTION = "What did Barnsley decide about restoring weekly bin collections, asks Quillfeather?"
SCRIPT = [
    CitationDelta(document=0, quoted=QUOTED),      # the first source, counted from 0
    TextDelta("A motion to restore weekly bin collections was moved at Barnsley's full council."),
    TextDelta(" It was lost when put to the vote."),
    Completed(blocks=(Block("A motion to restore weekly bin collections was moved at Barnsley's full council.",
                            (Citation(0, QUOTED),)),
                      Block(" It was lost when put to the vote.", ())),
              model="claude-sonnet-5-5", stop_reason="end_turn", usage=Usage(input_uncached=900, output=60)),
]
PLAN = {"search_text": "weekly bin collections", "date_from": None, "date_to": None, "councils": ["Barnsley"],
        "control": [], "parties": [], "nations": [], "council_types": [], "kinds": [], "group_by": "control",
        "wants_votes": False, "interpretation": "What Barnsley's minutes record about weekly bin collections."}


class Lines(logging.Handler):
    """Everything any logger wrote, as lines: what a log file or the server's journal would have held."""

    def __init__(self) -> None:
        super().__init__(logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def site(settings):  # noqa: F811
    """The site on the made-up record, indexed and embedded through the stand-ins, with all logging caught: its
    test client, its working parts, the stand-ins, and a function giving every log line so far (the structured
    log's files and whatever any logger wrote)."""
    embedder = RecordingEmbedder(16)
    # the site's own index, where the site keeps it, made afresh with the recording embedder (the fixture built
    # one with another): wts-core 0.3.0 reads everything in it, and everything written to it, through
    # ``LanceIndex.everything()``, where the site had a look-alike in memory for 0.2.1
    shutil.rmtree(settings.index_dir)
    index = open_index(settings, embedder)
    indexer = Indexer(settings, index=index)
    assert indexer.index_all() == 2
    assert embed_pending(settings, index, indexer.state, embedder) == 2 and index.stats()["vectors"] == 2
    # which searches the engine made, so that a check that passes is seen to have been through both
    searched: list[str] = []
    for name in ("search_words", "search_meaning"):
        real = getattr(index, name)
        setattr(index, name, lambda *a, _real=real, _name=name, **k: searched.append(_name) or _real(*a, **k))
    model = ScriptedModel(SCRIPT, structured=PLAN, structured_usage=Usage(input_uncached=300, output=40))
    pipeline = Pipeline(settings, Engine(settings, embedder, TODAY, index=index), model=model, today=TODAY)

    caught = Lines()
    root = logging.getLogger()
    before = root.level
    root.addHandler(caught)
    root.setLevel(logging.DEBUG)
    structured = start_logging(settings)
    logging.getLogger(LOGGER).addHandler(caught)        # the structured log does not pass its lines up
    app = create_app(settings, pipeline=pipeline)

    def lines() -> list[str]:
        structured.flush()
        files = [line for f in sorted(settings.logs_dir.glob("*")) for line in f.read_text().splitlines()]
        return files + caught.lines

    yield TestClient(app), app.state.councils, model, embedder, index, lines, searched
    root.removeHandler(caught)
    root.setLevel(before)
    logging.getLogger(LOGGER).removeHandler(caught)
    logging.getLogger(LOGGER).removeHandler(structured)
    structured.close()


def test_nothing_about_a_reader_is_kept_where_it_should_not_be(site):
    c, parts, model, embedder, _, lines, _ = site
    final = events(c.post("/api/ask", json={"question": QUESTION}))[-1]
    assert final["type"] == "final" and final["answer"]["citations_total"] == 1
    assert (final["answer"]["citations_invalid"], final["answer"]["quotes_unverified"]) == (0, 0)
    assert final["answer"]["segments"][0]["status"] == "cited"
    assert len(model.requests) == 1
    c.post("/api/ask", json={"question": QUESTION})                       # and again, from the cache
    c.post("/api/report", json={"kind": "error", "message": "The vote was in February, not March.",
                                "page": f"/b/{final['briefing_id']}", "contact": "reader@example.org"})
    (code,) = {v for (v,) in rows(parts, "SELECT visitor FROM wts_spending WHERE visitor != ''")}
    assert [r[0] for r in rows(parts, "SELECT outcome FROM wts_briefing_log ORDER BY rowid")] == ["completed",
                                                                                                 "cached"]
    assert any('"briefing.completed"' in line for line in lines())      # the structured log was on and written
    # the question only where the privacy notice says it is kept; the address nowhere; the day's code only on the
    # day's spending rows (where it is forgotten after its day: tests/test_observe.py)
    assert_no_reader_data(parts.db, lines(), question=QUESTION, address="testclient", visitor=code)
    # the address a reporter chose to give for a reply is kept with the report, and in no log
    kept = rows(parts, "SELECT contact FROM wts_reports")
    assert kept == [("reader@example.org",)] and not any("reader@example.org" in line for line in lines())


def test_a_statement_never_reaches_the_model_the_index_the_record_or_a_log(site):
    c, parts, model, embedder, index, lines, searched = site

    def ask(question: str) -> list[dict]:
        return events(c.post("/api/ask", json={"question": question}))

    assert_statements_stay_out(replies=parts.replies, ask=ask, model=model, embedder=embedder, index=index,
                               state=parts.db, log_lines=lines, item=f"/councils/{BARNSLEY}", question=QUESTION)
    # the check proved something: the model was asked (to read the question, then to write), the question was
    # embedded, both kinds of search ran, and the statement is on the council's page for a reader
    assert len(model.requests) == 1 and len(model.structured_requests) == 1
    assert embedder.queries and {"search_words", "search_meaning"} <= set(searched)
    assert len(list(index.everything())) >= 2                # and the index it looked in holds the passages
    shown = c.get(f"/api/statements?council={BARNSLEY}").json()["statements"]
    assert len(shown) == 1 and shown[0]["name"].startswith("Marker wtsmarker")


def test_once_its_day_is_over_a_briefings_record_is_tied_to_no_one(settings, monkeypatch):  # noqa: F811
    """wts-core 0.3.0 (ADR 0012, "the record's time, the spending rows, and what can be promised"; its CHANGELOG, "A
    spending row says who it was for, and what time of day it was made, for its own day only"). Two visitors each
    ask for a briefing of the same cost on one day: while that day lasts each spending row holds its visitor's
    code and its second, for the daily limit. That night the backup's unit runs `councils tidy`. From then on no
    record of that day can be tied to who asked: the record keeps its hour, the spending rows their day and no
    code, and the package's own attack gives no record to anyone. (This site has no accounts; the second asker is
    there because the check is only meaningful with more than one, as it says.)"""
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(settings.data_dir))
    (settings.data_dir / "settings.local.toml").write_text('[embedding]\nbackend = "hashing"\ndim = 64\n')
    clock = FixedClock("2026-11-16T10:41:07+00:00")
    monkeypatch.setattr(cli, "CLOCK", clock)
    pipeline = Pipeline(settings, Engine(settings, HashingEmbedder(64), TODAY), model=as_model(FakeClient()),
                        today=TODAY)
    app = create_app(settings, pipeline=pipeline, clock=clock)
    parts = app.state.councils
    me, other = TestClient(app), TestClient(app, client=("203.0.113.7", 50000))
    for reader, question in ((me, "What have councils decided about bin collections?"),
                             (other, "What have councils said about the recycling strategy?")):
        assert events(reader.post("/api/ask", json={"question": question}))[-1]["type"] == "final"
        clock.advance(minutes=17)
    day = "SELECT visitor, at FROM wts_spending WHERE at >= '2026-11-16' ORDER BY rowid"
    assert len({visitor for visitor, _ in rows(parts, day)} - {""}) == 2    # two readers, while the day lasts
    assert [at for (at,) in rows(parts, "SELECT at FROM wts_briefing_log")] == ["2026-11-16T10:00:00+00:00"] * 2

    # the next morning, before the night's forgetting has run, the check fails: it is not just looking for nothing
    clock.set("2026-11-17T04:29:00+00:00")
    with pytest.raises(AssertionError, match="still hold a visitor's code"):
        assert_briefings_tied_to_no_one(parts.db, clock=clock)
    clock.set("2026-11-17T04:31:00+00:00")
    tidied = CliRunner().invoke(cli.app, ["tidy"])
    assert tidied.exit_code == 0, tidied.output
    assert "Forgot the visitor codes on" in tidied.output
    assert_briefings_tied_to_no_one(parts.db, clock=clock)
    assert {(visitor, at) for visitor, at in rows(parts, day)} == {("", "2026-11-16T00:00:00+00:00")}
