"""The two walls the shared package checks for every site, run against this site's real pipeline and tables: nothing
about a reader is kept where it should not be (ADR 0012), and a statement under the right of reply never reaches the
model, the embedder, the search index, the record of briefings or a log (ADR 0008; decision 22).

The pipeline is the site's own (the indexer, the engine, the planner, the briefing desk and the web app), over the
package's stand-ins: a scripted model, an embedder that records what it is given, and an index in memory."""

import logging

import pytest
from fastapi.testclient import TestClient
from test_api import events, rows
from test_pipeline import BARNSLEY, TODAY, settings  # noqa: F401 - the fixture
from wts_core.events import Block, Citation, CitationDelta, Completed, TextDelta
from wts_core.observe import LOGGER
from wts_core.ports import Usage
from wts_core.testing import assert_no_reader_data, assert_statements_stay_out
from wts_core.testing.index import MemoryIndex, RecordingEmbedder
from wts_core.testing.models import ScriptedModel

from councils.api.app import create_app, start_logging
from councils.engine import Engine
from councils.index.build import Indexer, embed_pending
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


class SiteIndex(MemoryIndex):
    """The package's index in memory, with the reads this site's engine and indexer make beyond the port's (the
    real index, ``wts_core.adapters.lancedb.LanceIndex``, has them): how much it holds, passages by id, and a
    council-year's rows and vectors. Everything is still read from, and written to, what the walls look in."""

    def stats(self) -> dict[str, int]:
        return {"passages": len(self.rows), "vectors": len(self.vectors)}

    def passages_for(self, ids):
        return {i: dict(self.rows[i]) for i in ids if i in self.rows}

    def rows_for_keys(self, keys):
        return [dict(r) for r in self.rows.values() if r.get("source_key") in keys]

    def vectors_for_keys(self, keys):
        return {i: v for i, v in self.vectors.items() if self.vector_rows[i].get("source_key") in keys}

    def search_meaning(self, vector, where, limit, **tuning):      # how hard a real store looks: nothing here
        return super().search_meaning(vector, where, limit)


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
    index = SiteIndex(embedder)
    indexer = Indexer(settings, index=index)
    indexer.state.data.clear()          # the fixture indexed the real store; this index starts empty
    assert indexer.index_all() == 2
    assert embed_pending(settings, index, indexer.state, embedder) == 2 and index.stats()["vectors"] == 2
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

    yield TestClient(app), app.state.councils, model, embedder, index, lines
    root.removeHandler(caught)
    root.setLevel(before)
    logging.getLogger(LOGGER).removeHandler(caught)
    logging.getLogger(LOGGER).removeHandler(structured)
    structured.close()


def test_nothing_about_a_reader_is_kept_where_it_should_not_be(site):
    c, parts, model, embedder, _, lines = site
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
    c, parts, model, embedder, index, lines = site

    def ask(question: str) -> list[dict]:
        return events(c.post("/api/ask", json={"question": question}))

    assert_statements_stay_out(replies=parts.replies, ask=ask, model=model, embedder=embedder, index=index,
                               state=parts.db, log_lines=lines, item=f"/councils/{BARNSLEY}", question=QUESTION)
    # the check proved something: the model was asked (to read the question, then to write), the question was
    # embedded, both kinds of search ran, and the statement is on the council's page for a reader
    assert len(model.requests) == 1 and len(model.structured_requests) == 1
    assert embedder.queries and {"search_words", "search_meaning"} <= set(index.calls)
    shown = c.get(f"/api/statements?council={BARNSLEY}").json()["statements"]
    assert len(shown) == 1 and shown[0]["name"].startswith("Marker wtsmarker")
