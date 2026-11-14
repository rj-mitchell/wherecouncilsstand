"""The web service: questions answered as streamed briefings, search, council and vote pages, saved briefings, problem
reports and statements under the right of reply. Serves the built web pages (web/dist) too. Run with ``councils serve``.

The routes, the request bodies and the pages are this site's own. The flow of a briefing (the per-minute limit, the
answer cache, the daily limit and the spending caps, the briefings in progress, saving, the record of each
briefing) is the Where They Stand sites' shared package's (wts-core, ``wts_core.briefing``: its briefing desk), and
so are the rules of reports and the right of reply (``wts_core.replies``; src/councils/replies.py). The site is
public, so new briefings are limited per visitor and overall. Over a limit, the sources are still shown, which
costs nothing.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import date
from html import escape
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationInfo, field_validator
from wts_core.briefing import (
    Ask,
    BriefingDesk,
    DeskParts,
    Event,
    Hooks,
    TooManyRequests,
    current_stages,
    desk_parts,
    sse,
)
from wts_core.observe import LOGGER, SqliteBriefingLog, json_logging
from wts_core.ports import SYSTEM_CLOCK, SYSTEM_RANDOM, Clock, Random
from wts_core.replies import Refused, Replies
from wts_core.settings import Messages, require
from wts_core.state import StateDB
from wts_core.usage import cache_key, visitor_code

from councils import replies as right_of_reply
from councils import state as state_database
from councils.api import plaintext
from councils.api.data import Data
from councils.config import INSTRUCTIONS_VERSION, REPO_ROOT, SITE, Settings, load_settings
from councils.rag.checks import rechecked
from councils.rag.pipeline import AskRequest, Pipeline, configuration
from councils.rag.query_parse import QueryPlan, parse_model, parse_offline
from councils.registry import REGION_NAMES, TYPE_NAMES

log = logging.getLogger(__name__)

# so that a proxy passes each event on as it is written
STREAM_HEADERS = {"Cache-Control": "no-cache", "X-Accel-Buffering": "no"}
# How many visitors the per-minute limiter holds before it forgets the idle ones
FORGET_IDLE_VISITORS_OVER = 10_000

# Every word of the briefing flow that a reader can be shown (the shared package has none of its own)
MESSAGES = Messages(
    too_many_requests="Too many requests. Please wait a minute and try again.",
    visitor_daily_limit="You have asked a lot of questions today, so new briefings are paused until tomorrow.",
    daily_cap="The site has reached today's limit on new briefings, which keeps its costs down.",
    monthly_cap="The site has reached this month's limit on new briefings, which keeps its costs down.",
    busy_visitor="A briefing is already being written for you; please wait for it to finish.",
    busy_site="Many briefings are being written at the moment; please try again in a minute.",
    sources_follow="{reason} The sources found are shown below.",
    sources_only="Sources only: no briefing was written. Ask again without 'Sources only' for a written briefing.",
    briefing_failed="The briefing could not be written just now. Any sources found are shown above; please try "
                    "again later.",
    model_declined="The model declined to answer this question.",     # said by the pipeline (rag/pipeline.py)
)
EXAMPLES = [
    "What have councils decided about weekly bin collections since 2023?",
    "How have Reform UK councillors voted on council budgets?",
    "What have councils said about closing public toilets?",
    "What have councils in Wales decided about second homes and council tax?",
    "How did councillors vote on declaring a climate emergency?",
    "What has Barnsley's full council decided about libraries?",
]


class HistoryItem(BaseModel):
    """An earlier question in the conversation, as a follow-up sends it back (as Where MPs Stand). Each part is cut
    to a fixed length, so a request cannot inflate the prompt: the question to the longest a question may be, the
    answer to more than the briefing instructions use of it (rag/answer.py)."""

    question: str = ""
    answer: str = ""

    @field_validator("question", "answer", mode="before")
    @classmethod
    def _trimmed(cls, v: Any, info: ValidationInfo) -> str:
        return str(v or "")[:HISTORY_LIMITS[info.field_name]]


HISTORY_LIMITS = {"question": 500, "answer": 1000}
BRIEFING_PAGE = re.compile(r"/b/([A-Za-z0-9_-]{6,40})/?(?:[?#].*)?$")   # a saved briefing's address, in a report
PLAN_MAX_CHARS = 20_000  # an edited plan is a few hundred characters; this is far more than any reader needs


class AskBody(BaseModel):
    question: str = Field(min_length=3, max_length=500)
    mode: Literal["summary", "comprehensive"] = "summary"
    plan: dict[str, Any] | None = None
    history: list[HistoryItem] = Field(default_factory=list, max_length=6)
    sources_only: bool = False

    @field_validator("plan")
    @classmethod
    def _plan_size(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(json.dumps(v, default=str)) > PLAN_MAX_CHARS:
            raise ValueError("the search plan is too large")
        return v

    def history_dicts(self) -> list[dict[str, str]]:
        return [h.model_dump() for h in self.history]


class ReportBody(BaseModel):
    # the policy's routes (impartiality policy 7.1): "error" is "Something is wrong", "unfair" is "You've been
    # characterised unfairly"; a statement in someone's own words has its own form (StatementBody). "takedown" is a
    # request about someone who isn't a councillor, dealt with first. Links such as ?kind=takedown rely on these.
    kind: Literal["error", "unfair", "takedown", "other"] = "error"
    page: str = Field(default="", max_length=500)
    message: str = Field(min_length=5, max_length=5000)
    contact: str = Field(default="", max_length=300)


class StatementBody(BaseModel):
    """A statement under the right of reply (src/councils/replies.py): checked again by the shared package, with
    this site's words for the reader."""
    page: str = Field(max_length=500)
    name: str = Field(min_length=2, max_length=200)
    role: str = Field(min_length=2, max_length=200)
    text: str = Field(max_length=right_of_reply.MAX_CHARS + 100)
    link: str = Field(default="", max_length=500)
    email: str = Field(max_length=300)
    acting: bool = False


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


class CouncilsHooks(Hooks):
    """This site's own steps in the flow of a briefing (``wts_core.briefing.Hooks``)."""

    def on_cached(self, ask: Ask, events: list[Event]) -> list[Event]:
        """A cached briefing's marks are judged again by the current checks before it is shown."""
        return rechecked(events)

    def on_event(self, ask: Ask, event: Event) -> Event | None:
        """Token counts are for the spending record, which has them by now: this site sends none to the reader,
        and none is in the saved or cached copy. Nor is why the model could not read a question."""
        if event["type"] in ("plan", "final"):
            return {k: v for k, v in event.items() if k not in ("usage", "parse_error")}
        return event


def answer_key(body: AskBody, data_stamp: float, model: str | None) -> str:
    """The answer cache's key for a question: everything that would make an old answer wrong. The question (its
    case and spacing aside), what the reader chose, the earlier questions a follow-up carries, the model, the
    version of the instructions, and when the record last changed. 32 characters, as this site has always kept."""
    return cache_key({"q": " ".join(body.question.lower().split()), **body.model_dump(exclude={"question"}),
                      "data": data_stamp, "model": model, "v": INSTRUCTIONS_VERSION}, length=32)


@dataclass(frozen=True)
class Councils:
    """Everything the routes work with, made once by ``build``: the state database, what the briefing desk is made
    of (the spending record, the caps, the answer cache, saved briefings), the desk, the record of each briefing,
    and reports and statements."""

    settings: Settings
    db: StateDB
    data: Data
    parts: DeskParts
    log: SqliteBriefingLog
    desk: BriefingDesk
    replies: Replies
    clock: Clock
    random: Random


def new_briefing_id(chance: Random) -> str:
    return state_database.new_briefing_id(chance)


def build(settings: Settings, state: StateDB | None = None, *, clock: Clock = SYSTEM_CLOCK,
          random: Random = SYSTEM_RANDOM) -> Councils:
    """The site's working parts, from its settings. This is also the start-up check: every limit, price and
    message the flow of a briefing needs, and a price for each model the settings name, with whatever is missing
    named together in one error."""
    db = state or state_database.open_state(settings, clock)
    data = Data(settings)
    parts = desk_parts(
        settings, db, MESSAGES,
        new_id=lambda chance: new_briefing_id(chance),
        at_once_per_visitor="briefings_at_once_per_visitor", forget_over=FORGET_IDLE_VISITORS_OVER,
        keep_failures=False,     # a failed briefing is logged, never kept: the privacy notice promises nothing else
        # each model named must have prices of its own, so a new model is never costed at another's
        require_prices_for=(settings.answer.get("model"), parse_model(settings)),
        clock=clock, random=random)
    log = SqliteBriefingLog(db, clock=clock)
    config = configuration(settings, log)       # its id worked out, and the parts behind it kept
    desk = parts.desk(config, log=log, hooks=CouncilsHooks(),
                      # the record counts each briefing's sources by the group the evidence was balanced across
                      group_of=lambda card: card.get("group"))
    replies = right_of_reply.open_replies(db, lambda: data, parts.archive, clock)
    return Councils(settings=settings, db=db, data=data, parts=parts, log=log, desk=desk, replies=replies,
                    clock=clock, random=random)


def start_logging(settings: Settings, clock: Clock = SYSTEM_CLOCK) -> logging.Handler:
    """Turn the structured log on for this process (``councils serve`` does): one line of JSON for each stage a
    briefing reached and one for how it ended, in ``<data>/logs/briefings.jsonl``, within the limits in ``[logs]``.
    A line holds the record's id, a stage's name, a time and an error's class name, and nothing else: never a
    question, an address or a visitor's code. The handler is returned so that whoever started it can take it off."""
    logs = require(settings, "logs", ("max_bytes", "keep", "days"))
    handler = json_logging(settings.logs_dir / "briefings.jsonl", site=SITE, max_bytes=int(logs["max_bytes"]),
                           keep=int(logs["keep"]), days=int(logs["days"]), clock=clock)
    lines = logging.getLogger(LOGGER)
    lines.addHandler(handler)
    lines.setLevel(logging.INFO)
    lines.propagate = False
    return handler


def create_app(settings: Settings | None = None, pipeline: Pipeline | None = None,
               state: StateDB | None = None, *, clock: Clock = SYSTEM_CLOCK,
               random: Random = SYSTEM_RANDOM) -> FastAPI:
    settings = settings or load_settings()
    site_parts = build(settings, state, clock=clock, random=random)
    data, parts, desk, replies = site_parts.data, site_parts.parts, site_parts.desk, site_parts.replies
    archive, items = parts.archive, replies.items
    site = settings.section("site")
    dist = Path(settings.section("paths").get("web_dist", REPO_ROOT / "web" / "dist"))
    holder: dict[str, Pipeline] = {"p": pipeline} if pipeline is not None else {}
    lock = threading.Lock()
    # No interactive API pages: FastAPI's Swagger and ReDoc pages load their scripts from a CDN, which the site's
    # content security policy blocks, so they showed a blank page. The machine-readable description stays.
    app = FastAPI(title="Where Councils Stand", docs_url=None, redoc_url=None, openapi_url="/api/openapi.json")
    app.state.councils = site_parts

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
        v = visitor_code(site_parts.db, request.client.host if request.client else None, clock=clock, random=random)
        try:
            desk.allow(v)
        except TooManyRequests as exc:
            raise HTTPException(429, exc.message) from None
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
        refusal = parts.caps.site_paused() if model_on else None
        paused = refusal.message if refusal else None
        last = data.last_update()
        return {
            "councils": totals.get("councils", 0), "loaded": totals.get("loaded", 0),
            "authorities": totals.get("authorities", 0), "authorities_loaded": totals.get("authorities_loaded", 0),
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
        req = AskRequest(question=body.question, mode=body.mode, plan=body.plan, history=body.history_dicts())

        def sources_only(note: str, free: bool) -> Iterator[Event]:
            if free:      # over a limit, or the site's spending cap is reached: the question is read by the free rules
                plan = offline_plan(body)
            else:         # the model reads the question better, for a fraction of a penny
                plan, used = p.make_plan(req)
                # these events carry no token counts, so the desk cannot see this call: the site records the
                # spending itself, and tells the briefing's record what it cost
                cost = parts.spending.add("parse", parse_model(settings), used, visitor=v)
                current_stages().spent(used, cost)
            result, sources = p.find(plan, req)
            yield {"type": "plan", "plan": plan.to_dict(), "usage": None}
            yield {"type": "sources", "sources": [s.card() for s in sources], "candidates": result.candidates,
                   "semantic": result.semantic_available, "evidence": result.evidence}
            yield {"type": "final", "answer": None, "usage": None, "note": note}

        # A follow-up's answer depends on the earlier questions it was given, so they are part of the cache key. They
        # are not kept with the saved briefing: a shared page should not carry an earlier conversation.
        events = desk.handle(Ask(
            question=body.question, visitor=v, write=lambda: p.run(req), sources_only=sources_only,
            cache_key=answer_key(body, data.stamp(), settings.answer.get("model")),
            only_sources=body.sources_only, model_available=p.has_model(), follow_up=bool(body.history),
            mode=body.mode,
            filters_set=tuple(sorted(k for k, val in ((body.plan or {}).get("filters") or {}).items() if val)),
            options=body.model_dump(exclude={"question", "history"})))
        return StreamingResponse(sse(events), media_type="text/event-stream", headers=STREAM_HEADERS)

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
        b = archive.get(bid)
        if b is None:
            raise HTTPException(404, "There is no briefing at this address.")
        if b.withdrawn_at:
            why = (b.withdrawn_reason or "").strip()
            raise HTTPException(410, "This briefing has been withdrawn" + (f": {why}" if why else "."))
        # a briefing saved before follow-up questions were left out of its options is served without them
        return {"id": b.id, "at": b.created_at, "question": b.question,
                "options": {k: val for k, val in b.options.items() if k != "history"},
                "events": rechecked(b.events)}

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
        visitor(request)      # the per-minute limit only: nobody's reports are counted, and no code is kept with one
        about = BRIEFING_PAGE.search(body.page)
        try:
            rid = replies.report(kind=body.kind, page=body.page, message=body.message, contact=body.contact,
                                 briefing_id=about.group(1) if about else None)
        except Refused as exc:
            raise HTTPException(422, str(exc)) from None
        if about:
            site_parts.log.mark(about.group(1), reported=True)      # what happened next, on that briefing's record
        return {"ok": True, "id": rid}

    # ---- statements under the right of reply (decision 22) -------------------------------------------
    def site_hosts(request: Request) -> tuple[str, ...]:
        own = urlsplit(site.get("url") or "").hostname
        return (*SITE.hosts, *([own, f"www.{own}"] if own else []), request.url.hostname or "")

    def with_about(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Each statement with the name of the item it is about, for a council's page, which gathers them all."""
        out = []
        for r in rows:
            kind, key = r["page"].split("/")[1:3]
            try:
                if kind == "votes":
                    v = data.vote(key)
                    about = f"{v.get('item') or 'Named vote'}, {plaintext.long_date(v.get('date'))}" if v else None
                elif kind == "councils":
                    about = (data.council(key) or {}).get("name")
                else:
                    saved = archive.get(key)
                    about = f"Briefing: {saved.question if saved else ''}"
            except Exception:  # noqa: BLE001 - a name is a courtesy; the link still works without it
                about = None
            out.append({**r, "about": about or r["page"]})
        return out

    @app.post("/api/statements")
    def add_statement(body: StatementBody, request: Request):
        """A statement as sent: held until the owner has confirmed who sent it, then published or declined."""
        visitor(request)      # the per-minute limit only, as for a report
        if not body.acting:
            raise HTTPException(422, "Please confirm that you are the person or organisation the item is about, or "
                                     "act for them.")
        try:
            # the address first, read with the host the request came to among the site's own; then the package's
            # checks, in its order: the words, the name, the role, the link, the email address, and that the item
            # is on the site and shown
            item = items.resolve(body.page, site_hosts(request))
            sid = replies.submit(name=body.name, role=body.role, item=item, text=body.text, link=body.link,
                                 email=body.email)
        except Refused as exc:
            raise HTTPException(422, str(exc)) from None
        return {"ok": True, "id": sid}

    @app.get("/api/statements")
    def published_statements(page: str = "", council: str = ""):
        """The published statements beside one item (``page``, its path) or on one council's page (``council``)."""
        if not page and not council:
            raise HTTPException(422, "Give a page or a council.")
        try:
            item = items.resolve(page) if page else None
        except Refused as exc:
            raise HTTPException(422, str(exc)) from None
        rows = right_of_reply.published(replies, item, council.upper() or None)
        return {"statements": with_about(rows) if council else rows, "note": right_of_reply.NOT_ENDORSED}

    # ---- pages ---------------------------------------------------------------------------------------
    def page(name: str) -> FileResponse:
        path = dist / f"{name}.html"
        if not path.exists():
            raise HTTPException(404, "Not found.")
        return FileResponse(path, media_type="text/html")

    def site_url(request: Request) -> str:
        """The site's own address, for canonical links and the sitemap: the configured one, so a page reached by
        another name (the server's address, www) still points search engines to the one address."""
        return (site.get("url") or str(request.base_url)).rstrip("/")

    def readable(name: str, build) -> Response:
        """A page with its own title, description, canonical link and structured data, and its content as plain
        HTML for readers without scripts and search engines (api/plaintext.py), which the app replaces when it
        starts. ``build`` gives (status, title, description, url, data, text). If the record can't be read, the page
        is sent as it is: it still works with scripts on."""
        path = dist / f"{name}.html"
        if not path.exists():
            raise HTTPException(404, "Not found.")
        html = path.read_text(encoding="utf-8")
        try:
            status, title, description, url, ld, text = build()
        except Exception:  # noqa: BLE001 - the readable copy is a courtesy; never fail the page for it
            log.exception("readable page text not built for %s", name)
            return HTMLResponse(html)
        html = plaintext.page_with_meta(html, title=title, description=description, url=url, data=ld,
                                        noindex=status != 200)
        return HTMLResponse(plaintext.with_text(html, text), status_code=status)

    @app.get("/", include_in_schema=False)
    def home(request: Request):
        base = site_url(request)

        def build():
            totals = data.totals()
            ld = {"@context": "https://schema.org", "@type": "WebSite", "name": "Where Councils Stand",
                  "url": base + "/", "inLanguage": "en-GB",
                  "description": "Sourced briefings on what councils across the UK have discussed, decided and voted "
                                 "on, from their own minutes.",
                  "publisher": {"@type": "Organization", "name": "Where They Stand", "url": "https://wheretheystand.uk"}}
            return (200, "Where Councils Stand",
                    "Sourced briefings on what councils across the UK have discussed, decided and voted on. Every "
                    "point cites the council's own minutes.", base + "/", ld, plaintext.home_text(totals, EXAMPLES))

        return readable("index", build)

    @app.get("/b/{bid}", include_in_schema=False)
    def shared(bid: str):
        return page("index")

    @app.get("/councils", include_in_schema=False)
    def councils_page(request: Request):
        base = site_url(request)

        def build():
            directory = data.directory()
            t = directory["totals"]
            return (200, "Councils — Where Councils Stand",
                    f"The {t['councils']:,} principal councils in the UK and England's {t.get('authorities', 0):,} "
                    f"strategic authorities: which {t['loaded']:,} councils and {t.get('authorities_loaded', 0):,} "
                    "authorities are covered, from when, and which party is in overall control (or, for an "
                    "authority, its mayor's party).", base + "/councils", None,
                    plaintext.councils_text(directory))

        return readable("councils", build)

    @app.get("/councils/{gss}", include_in_schema=False)
    def council_page(gss: str, request: Request):
        base = site_url(request)

        def build():
            c = data.council(gss.upper())
            if c is None:
                return (404, "Council not found — Where Councils Stand", "There is no council at this address.",
                        base + plaintext.council_path(gss), None,
                        "<h1>Council not found</h1><p>There is no council at this address. See the "
                        '<a href="/councils">list of councils</a>.</p>')
            url = base + plaintext.council_path(c["gss"])
            # statements are shown after the record, never in its description or structured data (decision 22)
            return (200, f"{c['name']} — Where Councils Stand", plaintext.council_description(c), url,
                    plaintext.council_data(c, url, base), plaintext.council_text(c) + plaintext.statements_text(
                        with_about(right_of_reply.published(replies, council=c["gss"])),
                        here=plaintext.council_path(c["gss"])))

        return readable("council", build)

    @app.get("/votes/{vote_id}", include_in_schema=False)
    def vote_page(vote_id: str, request: Request):
        base = site_url(request)

        def build():
            v = data.vote(vote_id)
            if v is None:
                return (404, "Named vote not found — Where Councils Stand", "There is no named vote at this address.",
                        base + plaintext.vote_path(vote_id), None,
                        "<h1>Named vote not found</h1><p>There is no named vote at this address. Each council's "
                        'named votes are listed on its page: see the <a href="/councils">list of councils</a>.</p>')
            url = base + plaintext.vote_path(vote_id)
            mine = right_of_reply.published(replies, items.resolve(plaintext.vote_path(vote_id)))
            return (200, f"{plaintext.vote_title(v)} — Where Councils Stand", plaintext.vote_description(v), url,
                    plaintext.vote_data(v, url, base),
                    plaintext.vote_text(v) + plaintext.statements_text(mine, here=plaintext.vote_path(vote_id)))

        return readable("vote", build)

    @app.get("/sitemap.xml", include_in_schema=False)
    def sitemap(request: Request):
        """Every page worth finding: the home page, the pages of text, every council and every named vote."""
        base = site_url(request)
        fixed = ["/", "/councils"] + [f"/{p.stem}" for p in sorted(dist.glob("*.html"))
                                      if p.stem not in ("index", "councils", "council", "vote", "404")]
        urls = [base + p for p in fixed]
        urls += [base + plaintext.council_path(r["gss"]) for r in data.directory()["councils"]]
        urls += [base + plaintext.vote_path(v) for v in data.vote_ids()]
        body = "".join(f"<url><loc>{escape(u)}</loc></url>" for u in urls[:50000])
        return Response('<?xml version="1.0" encoding="UTF-8"?>'
                        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>',
                        media_type="application/xml")

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
