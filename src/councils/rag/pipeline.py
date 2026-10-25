"""Question -> plan -> evidence -> grounded briefing -> verification (adapted from Where Countries Stand).

``Pipeline.run`` yields events as it goes (the plan, the sources, text as it is written, then the verified answer),
so a web page can show each step; ``answer_once`` collects them into one result for the command line and tests.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from councils.config import Settings
from councils.engine import Engine
from councils.rag.british import britishise_segments, to_british
from councils.rag.neutral import flag_loaded
from councils.rag.prompts import NO_RECORDS
from councils.rag.query_parse import QueryPlan, parse_offline, parse_with_model
from councils.rag.sources import build_sources
from councils.rag.verify import check_quotes, drop_preambles, verify
from councils.registry import councils

log = logging.getLogger(__name__)


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
    if f.control:
        bits.append("councils in overall control of: " + ", ".join(f.control))
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
    def __init__(self, settings: Settings, engine: Engine | None = None, client=None, today: date | None = None):
        self.settings = settings
        self.engine = engine or Engine(settings, today=today)
        self._client = client
        self.today = today

    @property
    def client(self):
        if self._client is None:
            from councils.rag.answer import make_client

            self._client = make_client()
        return self._client

    def has_model(self) -> bool:
        if self._client is not None:
            return True
        import os

        from councils.rag.answer import api_key

        return bool(api_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"))

    def make_plan(self, req: AskRequest) -> tuple[QueryPlan, dict[str, int] | None]:
        if req.plan:
            return QueryPlan.from_dict({"question": req.question, **req.plan}), None
        today = self.today or date.today()
        offline = parse_offline(req.question, today, int(self.settings.archive.get("default_years", 4)),
                                self.settings.start_date)
        if not self.has_model():
            return offline, None
        try:
            from councils.rag.answer import usage_dict

            plan, usage = parse_with_model(self.client, self.settings, req.question, today)
            plan.interpretation = to_british(plan.interpretation)
            return plan, usage_dict(usage)
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

    def run(self, req: AskRequest) -> Iterator[dict[str, Any]]:
        plan, parse_usage = self.make_plan(req)
        ev: dict[str, Any] = {"type": "plan", "plan": plan.to_dict(), "usage": parse_usage}
        if plan.parse_error:
            ev["parse_error"] = plan.parse_error
        yield ev
        result, sources = self.find(plan, req)
        yield {"type": "sources", "sources": [s.card() for s in sources], "candidates": result.candidates,
               "semantic": result.semantic_available, "evidence": result.evidence}
        if not result.records:
            yield {"type": "final", "answer": {"segments": [{"text": NO_RECORDS + " The minutes contain no records "
                   "matching this question and these filters.", "sources": [], "cited": [], "status": "connective"}],
                   "markdown": NO_RECORDS, "no_records": True, "citations_total": 0, "citations_invalid": 0,
                   "grounded_ratio": 1.0}, "usage": None}
            return
        if not self.has_model():
            yield {"type": "final", "answer": None, "usage": None,
                   "note": "Showing the evidence only (no Anthropic API key set)."}
            return
        from councils.rag.answer import Answerer

        final = None
        for event in Answerer(self.settings, self.client).stream(
                plan.question, sources, req.mode, plan_note(plan), req.history, self.today or date.today(),
                plan.group_by):
            if event["type"] == "final":
                final = event
            else:
                yield event
        if final is None:
            raise RuntimeError("the model returned no answer")
        report = verify(final["blocks"], sources)
        drop_preambles(report.segments)
        britishise_segments(report.segments)
        loaded = flag_loaded(report.segments)
        check_quotes(report, sources)
        yield {"type": "final", "answer": {**report.to_dict(), "loaded_words": loaded}, "usage": final["usage"],
               "model": final.get("model"), "stop_reason": final.get("stop_reason")}


def answer_once(pipeline: Pipeline, req: AskRequest) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for ev in pipeline.run(req):
        if ev["type"] in ("plan", "sources", "final"):
            out[ev["type"]] = ev
    return out
