"""What the model is asked for a briefing: the request the pipeline hands to the model client.

The client itself is the Where They Stand sites' shared one (wts-core, ``wts_core.adapters``): the provider named in
``[answer] provider`` (Anthropic), the key from ``COUNCILS_ANTHROPIC_API_KEY`` (then ``ANTHROPIC_API_KEY``, then the
file ``anthropic_api_key`` in the data folder), five minutes without a byte before giving up, the streaming, the
citations and the fallback. What is this site's own is here and in rag/prompts.py: its instructions, the words of
its question to the model, how a source becomes a document, and its models, efforts and ``max_tokens`` (settings).
"""

from __future__ import annotations

from datetime import date

from wts_core.ports import Document, ModelRequest

from councils.config import Settings
from councils.rag.prompts import system_prompt, user_instruction
from councils.rag.sources import Source


def briefing_request(settings: Settings, question: str, sources: list[Source], mode: str = "summary",
                     plan_note: str = "", history: list[dict[str, str]] | None = None, today: date | None = None,
                     group_by: str = "control") -> ModelRequest:
    """The request for one briefing: the instructions (the same for every request but for the date, so the
    provider may cache them), the sources as numbered documents the model can cite, and the question."""
    cfg = settings.answer
    history_note = ""
    if history:
        history_note = "If this question follows on from an earlier one, answer what it asks, building on the " \
            "earlier briefing rather than repeating it (do not restate points already made unless the new " \
            "records change them). Earlier in this conversation (for context only; cite only the search " \
            "results below):\n" + \
            "\n".join(f"Q: {h['question']}\nA (summary): {h.get('answer', '')[:600]}" for h in history[-3:])
    return ModelRequest(
        model=cfg.get("model", "claude-sonnet-5-5"),
        instructions=system_prompt(today or date.today()),
        question=user_instruction(question, mode, plan_note, history_note, group_by),
        documents=tuple(Document(number=s.n, title=s.title, source=s.url, passages=tuple(s.blocks)) for s in sources),
        max_tokens=int(cfg.get("max_tokens", 16000)),
        effort=cfg.get("comprehensive_effort" if mode == "comprehensive" else "summary_effort", "medium"),
        # "short" is the provider's ordinary cache of the instructions, as before; "off" or "long" in settings
        cache_instructions=cfg.get("cache_instructions", "short"),
        fallbacks=bool(cfg.get("use_fallbacks", True)),
    )
