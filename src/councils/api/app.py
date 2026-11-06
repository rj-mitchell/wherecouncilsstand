"""The web service: questions answered as streamed briefings, search, council and vote pages, saved briefings and
problem reports. Serves the built web pages (web/dist) too. Run with ``councils serve``.

Adapted from Where MPs Stand's service, without accounts: the site is public, so new briefings are limited per
visitor and overall (api/usage.py). Over a limit, the sources are still shown, which costs nothing.
"""

from __future__ import annotations

import hashlib
import json
import logging
import queue
import threading
from collections.abc import Iterator
from datetime import date
from pathlib import Path
from typing import Any, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from councils.api.data import Data
from councils.api.state import StateDB
from councils.api.usage import (
    InFlight,
    RateLimiter,
    blocked,
    count_question,
    record_usage,
    site_paused,
    visitor_key,
)
from councils.config import Settings, load_settings
from councils.rag.neutral import still_loaded
from councils.rag.pipeline import AskRequest, Pipeline
from councils.rag.query_parse import QueryPlan, parse_offline
from councils.rag.verify import recheck_flags
from councils.registry import REGION_NAMES, TYPE_NAMES

log = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[3]
KEEP_ALIVE_SECONDS = 15
# Bump when the briefing instructions or the answer's shape change, so cached answers aren't reused.
INSTRUCTIONS_VERSION = "2"
EXAMPLES = [
    "What have councils decided about weekly bin collections since 2023?",
    "How have Reform UK councillors voted on council budgets?",
    "What have councils said about closing public toilets?",
    "What have councils in Wales decided about second homes and council tax?",
    "How did councillors vote on declaring a climate emergency?",
    "What has Barnsley's full council decided about libraries?",
]


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    mode: Literal["summary", "comprehensive"] = "summary"
    plan: dict[str, Any] | None = None
    history: list[dict[str, str]] = Field(default_factory=list, max_length=6)
    sources_only: bool = False


class ReportBody(BaseModel):
    kind: Literal["error", "takedown", "other"] = "error"
    page: str = Field(default="", max_length=500)
    message: str = Field(min_length=5, max_length=5000)
    contact: str = Field(default="", max_length=300)


def sse(events: Iterator[dict[str, Any]], keep_alive: float = KEEP_ALIVE_SECONDS) -> Iterator[bytes]:
    """Server-sent events, with a comment line after each few seconds of silence (while the model thinks), so proxies
    don't close the connection. The events are worked out in their own thread, which stops once the reader has gone."""
    q: queue.Queue = queue.Queue()
    gone = threading.Event()
    end = object()

    def work() -> None:
        try:
            for ev in events:
                q.put(ev)
                if gone.is_set():
                    break
        except Exception as exc:  # passed on, to be raised where the response is being sent
            q.put(exc)
        finally:
            if hasattr(events, "close"):
                events.close()
            q.put(end)

    threading.Thread(target=work, name="sse", daemon=True).start()
    try:
        while True:
            try:
                ev = q.get(timeout=keep_alive)
            except queue.Empty:
                yield b": still working\n\n"
                continue
            if ev is end:
                return
            if isinstance(ev, Exception):
                raise ev
            yield f"event: {ev['type']}\ndata: {json.dumps(ev, default=str)}\n\n".encode()
    finally:
        gone.set()


class HeadAsGet:
    """HEAD is answered as GET, without the body. FastAPI's GET routes answer GET alone, and uptime checkers and link
    checkers that send HEAD read the 405 they got as the site being down."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["method"] != "HEAD":
            await self.app(scope, receive, send)
            return

        async def without_body(message):
            if message["type"] == "http.response.body":
                message = {**message, "body": b""}
            await send(message)

        await self.app({**scope, "method": "GET"}, receive, without_body)


def rechecked(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """A saved or cached briefing's marks, judged again by the current checks (as Where MPs Stand): text since
    recognised as a date, a join or a note about the evidence is no longer marked unsupported, and a word since taken
    off the loaded-words list is no longer flagged. Nothing is ever newly marked."""
    return [{**e, "answer": still_loaded(recheck_flags(e["answer"]))}
            if e.get("type") == "final" and e.get("answer") else e for e in events]


def cache_key(parts: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps(parts, sort_keys=True, default=str).encode()).hexdigest()[:32]


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None,
               state: StateDB | None = None) -> FastAPI:
    settings = settings or load_settings()
    state = state or StateDB(settings.data_dir / "state.db")
    data = Data(settings)
    usage_cfg = settings.usage
    limiter = RateLimiter(int(usage_cfg.get("requests_per_minute", 20)))
    inflight = InFlight(int(usage_cfg.get("briefings_at_once_per_visitor", 2)),
                        int(usage_cfg.get("briefings_at_once", 8)), float(usage_cfg.get("briefing_estimate_usd", 0.15)))
    cache_hours = float(usage_cfg.get("answer_cache_hours", 168))
    site = settings.section("site")
    dist = Path(settings.section("paths").get("web_dist", REPO_ROOT / "web" / "dist"))
    holder: dict[str, Pipeline] = {"p": pipeline} if pipeline is not None else {}
    lock = threading.Lock()
    # No interactive API pages: FastAPI's Swagger and ReDoc pages load their scripts from a CDN, which the site's
    # content security policy blocks, so they showed a blank page. The machine-readable description stays.
    app = FastAPI(title="Where Councils Stand", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")

    def get_pipeline() -> Pipeline:
        with lock:
            if "p" not in holder:
                holder["p"] = Pipeline(settings)
            return holder["p"]

    def offline_plan(body: AskBody) -> QueryPlan:
        if body.plan:
            return QueryPlan.from_dict({"question": body.question, **body.plan})
        return parse_offline(body.question, date.today(), int(settings.archive.get("default_years", 4)),
                             settings.start_date)

    def visitor(request: Request) -> str:
        """The visitor's daily code; 429 when over the per-minute limit."""
        # behind the proxy, uvicorn takes the address from X-Forwarded-For, which Caddy overwrites (deploy/Caddyfile);
        # a header the visitor could set themselves is never trusted
        v = visitor_key(state, request.client.host if request.client else None)
        if not limiter.allow(v):
            raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
        return v

    app.add_middleware(HeadAsGet)

    @app.middleware("http")
    async def headers(request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        return response

    # ---- about the site ------------------------------------------------------------------------------
    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/meta")
    def meta():
        p = get_pipeline()
        return {"site": {"name": site.get("name", "Where Councils Stand"), "url": site.get("url"),
                         "donate_url": site.get("donate_url") or None},
                "totals": data.totals(), "last_update": data.last_update(), "briefings": p.has_model(),
                "default_years": int(settings.archive.get("default_years", 4)),
                "start": settings.start_date.isoformat(), "examples": EXAMPLES,
                "regions": REGION_NAMES, "types": TYPE_NAMES}

    @app.get("/api/status")
    def status():
        """For the status page (as Where MPs Stand): how up to date the record is and whether briefings are being
        written. The last update is summarised; its list of councils that failed is not shown."""
        p = get_pipeline()
        totals = data.totals()
        model_on = p.has_model()
        paused = site_paused(state, usage_cfg) if model_on else None
        last = data.last_update()
        return {
            "councils": totals.get("councils", 0), "loaded": totals.get("loaded", 0),
            "meetings": totals.get("meetings", 0), "named_votes": totals.get("named_votes", 0),
            "start": settings.start_date.isoformat(), "latest_meeting": totals.get("to"),
            "last_update": {"finished": last.get("finished"), "councils": last.get("councils"),
                            "changed": last.get("changed"), "new_meetings": last.get("new_meetings"),
                            "failed": len(last.get("failed") or []),
                            "ok": not last.get("needs_attention")} if last else None,
            "briefings": "unavailable" if not model_on else ("paused" if paused else "available"),
            "briefings_note": paused,
        }

    # ---- questions -----------------------------------------------------------------------------------
    @app.post("/api/ask")
    def ask(body: AskBody, request: Request):
        v = visitor(request)
        p = get_pipeline()
        req = AskRequest(question=body.question, mode=body.mode, plan=body.plan, history=body.history)
        options = body.model_dump(exclude={"question"})
        key = cache_key({"q": " ".join(body.question.lower().split()), **options, "data": data.stamp(),
                         "model": settings.answer.get("model"), "v": INSTRUCTIONS_VERSION})
        hit = state.cached(key, cache_hours) if p.has_model() and not body.sources_only else None
        why_not = None if hit is not None or body.sources_only or not p.has_model() else blocked(state, v, usage_cfg)

        def sources_only(note: str, free: bool) -> Iterator[dict[str, Any]]:
            if free:      # over a limit: the question is read by the free rules
                plan = offline_plan(body)
            else:         # the model reads the question better, for a fraction of a penny
                plan, used = p.make_plan(req)
                record_usage(state, v, "parse", settings.answer.get("query_parse_model"), used, usage_cfg)
            result, sources = p.find(plan, req)
            yield {"type": "plan", "plan": plan.to_dict(), "usage": None}
            yield {"type": "sources", "sources": [s.card() for s in sources], "candidates": result.candidates,
                   "semantic": result.semantic_available, "evidence": result.evidence}
            yield {"type": "final", "answer": None, "usage": None, "note": note}

        def events() -> Iterator[dict[str, Any]]:
            if hit is not None:
                yield from rechecked(hit)
                return
            if body.sources_only:
                yield from sources_only("Sources only: no briefing was written. Ask again without 'Sources only' "
                                        "for a written briefing.", free=False)
                return
            if why_not:
                yield from sources_only(f"{why_not} The sources found are shown below.", free=True)
                return
            kept: list[dict[str, Any]] = []
            text: list[str] = []
            try:
                for ev in p.run(req):
                    if ev["type"] == "plan":
                        record_usage(state, v, "parse", settings.answer.get("query_parse_model"), ev.get("usage"),
                                     usage_cfg)
                        ev = {k: val for k, val in ev.items() if k not in ("usage", "parse_error")}
                    if ev["type"] == "final":
                        if ev.get("usage"):
                            record_usage(state, v, "answer", ev.get("model"), ev["usage"], usage_cfg)
                            count_question(state, v)
                        ev = {k: val for k, val in ev.items() if k != "usage"}
                        if ev.get("answer") and not ev["answer"].get("no_records"):
                            replay = [e for e in kept if e["type"] in ("plan", "sources")]
                            replay.append({"type": "text", "text": "".join(text)})
                            ev["briefing_id"] = state.new_briefing_id()
                            state.save_briefing(ev["briefing_id"], body.question, options, replay + [ev])
                    if ev["type"] == "text":
                        text.append(ev["text"])
                    else:
                        kept.append(ev)
                    yield ev
            except Exception:  # never leave the reader hanging
                log.exception("ask failed")
                yield {"type": "error", "message": "The briefing could not be written just now. Any sources found "
                                                   "are shown above; please try again later."}
                return
            final = kept[-1] if kept else {}
            if final.get("type") == "final" and final.get("answer"):
                replay = [e for e in kept if e["type"] in ("plan", "sources")]
                replay += [{"type": "text", "text": "".join(text)}, {**final, "cached": True}]
                state.store_cached(key, replay, cache_hours)

        def guarded() -> Iterator[dict[str, Any]]:
            """A briefing about to be written is reserved at its estimated cost while it runs, and the limits are
            checked again counting the others in progress, so many questions at once can't all slip past the caps
            (as Where MPs Stand)."""
            if hit is not None or body.sources_only or why_not or not p.has_model():
                yield from events()
                return
            refused = inflight.start(v)
            if refused:
                yield from sources_only(f"{refused} The sources found are shown below.", free=True)
                return
            try:
                late = blocked(state, v, usage_cfg, inflight.pending_usd(besides=1))
                if late:
                    yield from sources_only(f"{late} The sources found are shown below.", free=True)
                    return
                yield from events()
            finally:
                inflight.finish(v)

        return StreamingResponse(sse(guarded()), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.post("/api/search")
    def search(body: AskBody, request: Request):
        """The plan and ranked sources for a question, read by the free built-in rules: no model call."""
        visitor(request)
        p = get_pipeline()
        plan = offline_plan(body)
        result, sources = p.find(plan, AskRequest(question=body.question, mode=body.mode))
        return {"plan": plan.to_dict(), "sources": [s.card() for s in sources], "candidates": result.candidates,
                "semantic": result.semantic_available, "evidence": result.evidence}

    @app.get("/api/briefings/{bid}")
    def briefing(bid: str):
        b = state.briefing(bid)
        if b is None:
            raise HTTPException(404, "There is no briefing at this address.")
        if b["withdrawn_at"]:
            why = (b["withdrawn_reason"] or "").strip()
            raise HTTPException(410, "This briefing has been withdrawn" + (f": {why}" if why else "."))
        return {"id": b["id"], "at": b["at"], "question": b["question"], "options": b["options"],
                "events": rechecked(b["events"])}

    # ---- councils and votes --------------------------------------------------------------------------
    @app.get("/api/councils")
    def council_list():
        return data.directory()

    @app.get("/api/councils/{gss}")
    def council(gss: str):
        c = data.council(gss.upper())
        if c is None:
            raise HTTPException(404, "There is no council with this code.")
        return c

    @app.get("/api/votes/{vote_id}")
    def vote(vote_id: str):
        v = data.vote(vote_id)
        if v is None:
            raise HTTPException(404, "There is no named vote at this address.")
        return v

    # ---- problems and takedown requests --------------------------------------------------------------
    @app.post("/api/report")
    def report(body: ReportBody, request: Request):
        visitor(request)
        rid = state.add_report(body.kind, body.page, body.message, body.contact)
        return {"ok": True, "id": rid}

    # ---- pages ---------------------------------------------------------------------------------------
    def page(name: str) -> FileResponse:
        path = dist / f"{name}.html"
        if not path.exists():
            raise HTTPException(404, "Not found.")
        return FileResponse(path, media_type="text/html")

    @app.get("/", include_in_schema=False)
    def home():
        return page("index")

    @app.get("/b/{bid}", include_in_schema=False)
    def shared(bid: str):
        return page("index")

    @app.get("/councils", include_in_schema=False)
    def councils_page():
        return page("councils")

    @app.get("/councils/{gss}", include_in_schema=False)
    def council_page(gss: str):
        return page("council")

    @app.get("/votes/{vote_id}", include_in_schema=False)
    def vote_page(vote_id: str):
        return page("vote")

    if (dist / "assets").exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    # the Where They Stand family kit (web/public/family: icons, the shared stylesheet and fonts, the link card)
    if (dist / "family").exists():
        app.mount("/family", StaticFiles(directory=dist / "family"), name="family")

    @app.get("/favicon.ico", include_in_schema=False)
    def favicon():
        """Browsers ask for /favicon.ico whatever the page says: the kit's icon, the site's spine in its cloth."""
        path = dist / "family" / "favicon.ico"
        if not path.is_file():
            raise HTTPException(404, "Not found.")
        return FileResponse(path, media_type="image/vnd.microsoft.icon")

    @app.get("/{name}", include_in_schema=False)
    def static_page(name: str):
        """about, methodology, privacy, corrections ..., and files such as robots.txt."""
        safe = Path(name).name
        if (dist / safe).is_file():
            return FileResponse(dist / safe)
        if (dist / f"{safe}.html").is_file():
            return FileResponse(dist / f"{safe}.html", media_type="text/html")
        missing = dist / "404.html"
        if missing.exists():
            return HTMLResponse(missing.read_text(encoding="utf-8"), status_code=404)
        raise HTTPException(404, "Not found.")

    return app
