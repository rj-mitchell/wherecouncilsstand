"""Question -> plan -> evidence -> grounded briefing -> verification (adapted from Where Countries Stand).

``Pipeline.run`` yields events as it goes (the plan, the sources, text as it is written, then the verified answer),
so a web page can show each step; ``answer_once`` collects them into one result for the command line and tests.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from wts_core.adapters import has_model, model_client
from wts_core.briefing import current_stages
from wts_core.checks import check_briefing, to_british
from wts_core.events import Block, Completed, blocks_as_today, to_reader
from wts_core.observe import SqliteBriefingLog, briefing_config
from wts_core.ports import BriefingConfig, Document, ModelClient

from councils.config import INSTRUCTIONS_VERSION, SITE, Settings
from councils.engine import Engine
from councils.rag.answer import briefing_request
from councils.rag.checks import LOADED_WORDS, VERIFIER
from councils.rag.prompts import NO_RECORDS
from councils.rag.query_parse import QueryPlan, parse_model, parse_offline, parse_with_model
from councils.rag.sources import build_sources
from councils.registry import councils

log = logging.getLogger(__name__)

# what an evaluation run keeps of a briefing, to check again later: the documents the model was given, the blocks
# it wrote, and each document's heading (a quotation is looked for there too)
Keep = Callable[[tuple[Document, ...], tuple[Block, ...], tuple[str, ...]], None]


def configuration(settings: Settings, log: SqliteBriefingLog | None = None) -> BriefingConfig:
    """What this site's briefings run with, and the short id the record of briefings and an evaluation run both
    know it by: the two models, the version of the instructions, and everything else that could change a
    briefing (how the question is read and written, and how the evidence is found and chosen). Never a key, and
    nothing about a reader. With ``log`` the parts behind the id are kept there (the web app does); without, as
    for an evaluation run, nothing is written."""
    return briefing_config(
        log=log, model=str(settings.answer.get("model")), parse_model=parse_model(settings),
        instructions=INSTRUCTIONS_VERSION, site_version=SITE.version,
        also={"answer": {k: v for k, v in settings.answer.items() if k not in ("model", "query_parse_model")},
              "embedding": dict(settings.embedding), "ranking": dict(settings.ranking)})


@dataclass
class AskRequest:
    question: str
    mode: str = "summary"                       # summary | comprehensive
    plan: dict[str, Any] | None = None          # an edited plan from the reader, used instead of parsing
    recency: float | None = None
    history: list[dict[str, str]] = field(default_factory=list)


def plan_note(plan: QueryPlan) -> str:
    """The filters, in words, for the model (so it knows what the evidence was limited to)."""
    f = plan.filters
    bits = []
    if f.councils:
        bits.append("councils: " + ", ".join(councils()[g].name for g in f.councils if g in councils()))
    council_control = [c for c in f.control if not c.startswith(("MAYOR:", "SA:"))]
    if council_control:
        bits.append("councils in overall control of: " + ", ".join(council_control))
    mayors = [c.removeprefix("MAYOR:") for c in f.control if c.startswith("MAYOR:")]
    if mayors:
        bits.append("strategic authorities whose mayor's party is: " + ", ".join(mayors))
    if "SA:NONE" in f.control:
        bits.append("strategic authorities without a mayor")
    if f.parties:
        bits.append("passages naming councillors of: " + ", ".join(f.parties))
    for label, values in (("nations", f.nations), ("kinds of council", f.council_types), ("meetings", f.kinds)):
        if values:
            bits.append(f"{label}: " + ", ".join(values))
    if f.date_from or f.date_to:
        bits.append("dates: " + (f.date_from.isoformat() if f.date_from else "the start") + " to " +
                    (f.date_to.isoformat() if f.date_to else "today"))
    return "; ".join(bits)


class Pipeline:
    def __init__(self, settings: Settings, engine: Engine | None = None, model: ModelClient | None = None,
                 today: date | None = None):
        self.settings = settings
        self.engine = engine or Engine(settings, today=today)
        self._model = model
        self.today = today

    @property
    def model(self) -> ModelClient:
        """The model client, made once and kept for the life of the process (it remembers what the provider
        refused)."""
        if self._model is None:
            self._model = model_client(self.settings, SITE)
        return self._model

    def has_model(self) -> bool:
        """Whether there is a model to ask. Without a key the site shows the evidence only."""
        return self._model is not None or has_model(self.settings, SITE)

    def make_plan(self, req: AskRequest) -> tuple[QueryPlan, dict[str, int] | None]:
        if req.plan:
            return QueryPlan.from_dict({"question": req.question, **req.plan}), None
        today = self.today or date.today()
        offline = parse_offline(req.question, today, int(self.settings.archive.get("default_years", 4)),
                                self.settings.start_date)
        if not self.has_model():
            return offline, None
        try:
            plan, usage = parse_with_model(self.model, self.settings, req.question, today)
            plan.interpretation = to_british(plan.interpretation)
            return plan, usage.as_stored()
        except Exception as exc:
            log.warning("model query parsing failed (%s); using offline rules", exc)
            offline.parse_error = f"{type(exc).__name__}: {exc}"
            return offline, None

    def find(self, plan: QueryPlan, req: AskRequest):
        """The evidence for a plan: (search result, numbered sources). Free: no model call."""
        limit = int(self.settings.answer.get(
            "comprehensive_sources" if req.mode == "comprehensive" else "summary_sources", 24))
        result = self.engine.search(plan.search_text, plan.filters, req.recency, limit, diversify=True,
                                    group_by=plan.group_by)
        return result, build_sources(self.settings, result.records, plan.group_by)

    def run(self, req: AskRequest, keep: Keep | None = None) -> Iterator[dict[str, Any]]:
        """``keep``, where given, is handed what the model was given and what it wrote, before the checks: an
        evaluation run keeps them as a fixture. Nothing a reader asks is ever kept this way."""
        plan, parse_usage = self.make_plan(req)
        ev: dict[str, Any] = {"type": "plan", "plan": plan.to_dict(), "usage": parse_usage}
        if plan.parse_error:
            ev["parse_error"] = plan.parse_error
        yield ev
        result, sources = self.find(plan, req)
        # The briefing desk sees for itself when the question was read, the sources sent and the first words
        # written; the search and the model finishing happen in here, so the pipeline marks them for the
        # briefing's record (the engine searches and ranks in one step, so the two are marked together).
        stages = current_stages()
        stages.mark("searched")
        stages.mark("ranked")
        yield {"type": "sources", "sources": [s.card() for s in sources], "candidates": result.candidates,
               "semantic": result.semantic_available, "evidence": result.evidence}
        if not result.records:
            yield {"type": "final", "answer": {"segments": [{"text": NO_RECORDS + " The minutes contain no records "
                   "matching this question and these filters.", "sources": [], "cited": [], "status": "connective"}],
                   "markdown": NO_RECORDS, "no_records": True, "citations_total": 0, "citations_invalid": 0,
                   "grounded_ratio": 1.0, "unsupported_segments": 0}, "usage": None}
            return
        if not self.has_model():
            yield {"type": "final", "answer": None, "usage": None,
                   "note": "Showing the evidence only (no Anthropic API key set)."}
            return
        request = briefing_request(self.settings, plan.question, sources, req.mode, plan_note(plan), req.history,
                                   self.today or date.today(), plan.group_by)
        done: Completed | None = None
        stream = self.model.stream(request)
        try:
            for event in stream:
                if isinstance(event, Completed):
                    done = event
                else:
                    yield to_reader(event)          # text and citations, as the reader is sent them
        finally:
            stream.close()                          # the reader has gone, or the model has finished: stop it
        if done is None:
            raise RuntimeError("the model returned no answer")
        stages.mark("written")
        usage = done.usage.as_stored()              # the site's own form: input_tokens includes the cache writes
        if done.stop_reason == "refusal":
            # The model declined (as Where MPs Stand): an error for the reader, never an empty briefing saved and
            # shown as fully grounded. The call was still paid for, so its token counts go with the event.
            yield {"type": "error", "message": "The model declined to answer this question.",
                   "usage": usage, "model": done.model}
            return
        if keep is not None:
            keep(tuple(request.documents), tuple(done.blocks), tuple(str(x.meta.get("heading") or "") for x in sources))
        # every check, in the family's one order: citations, openers about the records, spelling, loaded words,
        # quotations (wts_core.checks; what is this site's own is in rag/checks.py)
        answer = check_briefing(blocks_as_today(done), sources, VERIFIER, LOADED_WORDS)
        yield {"type": "final", "answer": answer, "usage": usage, "model": done.model,
               "stop_reason": done.stop_reason}


def answer_once(pipeline: Pipeline, req: AskRequest) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ev in pipeline.run(req):
        if ev["type"] in ("plan", "sources", "final", "error"):
            out[ev["type"]] = ev
    return out
