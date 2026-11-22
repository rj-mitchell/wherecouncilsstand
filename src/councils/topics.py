"""Topic briefings: standing questions on what councils keep returning to, each with a page of its own at
``/topics/<slug>`` that holds its latest briefing, written afresh every week (docs/DECISIONS.md, 35; the charity's
review plan of 21 November 2026, C3; modelled on Where MPs Stand's ``topics.py``).

The topics are listed in ``config/topics.toml``. ``councils topics refresh`` (weekly, deploy/councils-topics.timer)
writes each one that is due through the same pipeline as a reader's briefing (``Pipeline.run``: the same search, the
same instructions and model, every check), and keeps it as a saved briefing, so it has its own address (``/b/<id>``)
and can be withdrawn, hidden or reported like any other. Each is shown through the same rules as a saved one: the
current checks, the display rule for quotations and what may be shown (``api/app.py``).

* A topic is due once its briefing is ``min_days`` old (six, so a weekly timer always finds it due and a second run
  the same week writes nothing), or has never been written; ``--force`` writes it anyway.
* Its question is read here, not by the model: ``search``, the dates (``months`` back from today) and any meetings
  come from the topic's own entry, so every week searches for the same thing and the reading costs nothing.
* Before anything is paid for, the record is searched (free). If it finds exactly the passages the current briefing
  was written from, nothing would change, and it is not written again.
* A briefing that fails (the model errs, declines, or nothing comes back), and a search that finds no records, leave
  the last good briefing in place: a version is only recorded once a briefing has been written and checked.
* Every model call is counted in the site's spending record (kind ``topic``) and against its caps. Before each
  topic the caps are asked, counting the briefing about to be written at its estimate (``[usage]
  briefing_estimate_usd``), and the run stops when a cap would be reached, or when the run itself has spent
  ``[topics] max_run_usd``. Two failures in one run stop it too: the same cause (a key, the provider's credit) would
  stop every other topic.

Which version is current is kept in the site's own table ``topic_versions`` in the state database (``councils.state``),
beside the package's tables, so it is in every backup with the briefings it points to.
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

from wts_core.briefing import DeskParts
from wts_core.briefing.stages import Stages, calling, marking
from wts_core.dates import long_date
from wts_core.ports import SYSTEM_CLOCK, Clock
from wts_core.replies.days import months_before
from wts_core.state import StateDB, iso
from wts_core.usage import SavedBriefings

from councils.config import Settings
from councils.rag.pipeline import AskRequest, Pipeline

SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
KIND = "topic"  # the kind of each of a topic briefing's rows in the spending record
KINDS = ("council", "cabinet", "policy", "board", "mayor", "scrutiny")  # the meetings a topic may name
DASHES = re.compile("[–—]")  # no en or em dashes in what readers see (the family's glossary)



@dataclass(frozen=True)
class Topic:
    slug: str
    title: str
    question: str
    description: str
    search: str
    months: int = 12
    kinds: tuple[str, ...] = ()

    @property
    def path(self) -> str:
        return f"/topics/{self.slug}"


def topics_file(settings: Settings) -> Path:
    """config/topics.toml, beside the settings file (``[topics] file`` names another)."""
    return settings.config_path.parent / str(settings.section("topics").get("file", "topics.toml"))


def load_topics(path: Path) -> list[Topic]:
    """The topics, in the order the file lists them (the order of /topics and the home page). Every entry is
    checked: a slug that is not lower-case words joined by hyphens or is used twice, a missing field, a question
    that does not end in a question mark, a dash, a period of no months or an unknown kind of meeting stops it, with
    the entry named."""
    if not Path(path).exists():
        return []
    raw = tomllib.loads(Path(path).read_text(encoding="utf-8"))
    out: list[Topic] = []
    seen: set[str] = set()
    for n, t in enumerate(raw.get("topic", []), start=1):
        where = f"{path}: topic {n} ({t.get('slug', 'no slug')})"
        missing = [k for k in ("slug", "title", "question", "description", "search") if not str(t.get(k, "")).strip()]
        if missing:
            raise ValueError(f"{where} has no {', '.join(missing)}")
        topic = Topic(slug=t["slug"], title=t["title"].strip(), question=" ".join(t["question"].split()),
                      description=t["description"].strip(), search=t["search"].strip(),
                      months=int(t.get("months", 12)), kinds=tuple(t.get("kinds") or ()))
        if not SLUG.match(topic.slug) or topic.slug in seen:
            raise ValueError(f"{where}: a slug must be unique, lower-case words joined by hyphens")
        if not topic.question.endswith("?"):
            raise ValueError(f"{where}: the question must end with a question mark")
        if any(DASHES.search(s) for s in (topic.title, topic.question, topic.description)):
            raise ValueError(f"{where}: use commas or colons, not dashes")
        if topic.months < 1:
            raise ValueError(f"{where}: months must be 1 or more")
        if set(topic.kinds) - set(KINDS):
            raise ValueError(f"{where}: kinds are some of {', '.join(KINDS)}")
        seen.add(topic.slug)
        out.append(topic)
    return out


def site_topics(settings: Settings) -> list[Topic]:
    return load_topics(topics_file(settings))


def find(settings: Settings, slug: str) -> Topic | None:
    return next((t for t in site_topics(settings) if t.slug == slug), None)


def plan_for(topic: Topic, today: date, start: date) -> dict[str, Any]:
    """The topic's question as read: its own search, from ``months`` before ``today`` to today, in the meetings it
    names (or those a reader's question with no filters searches), balanced across councils run by different
    parties. Given to the pipeline as a plan, so no model reads it."""
    since = max(months_before(datetime.combine(today, time()), topic.months).date(), start)
    return {"search_text": topic.search, "group_by": "control", "parser": "topic", "wants_votes": False,
            "filters": {"date_from": since.isoformat(), "date_to": today.isoformat(), "kinds": list(topic.kinds)},
            "interpretation": f"{topic.title}, in the minutes of councils across the UK from {long_date(since)} to "
                              f"{long_date(today)}, with the evidence balanced across councils run by different "
                              "parties."}


# The versions


def versions(db: StateDB, archive: SavedBriefings, slug: str) -> list[dict[str, Any]]:
    """Every briefing written for a topic that still stands, newest first: a withdrawn one is not one."""
    with db.connect() as con:
        rows = con.execute("SELECT briefing_id, prepared_at, records_from, records_to FROM topic_versions "
                           "WHERE slug = ? ORDER BY prepared_at DESC, rowid DESC", (slug,)).fetchall()
    out = []
    for r in rows:
        b = archive.get(r["briefing_id"])
        if b is not None and b.withdrawn_at is None:
            out.append(dict(r))
    return out


def current(db: StateDB, archive: SavedBriefings, slug: str) -> dict[str, Any] | None:
    v = versions(db, archive, slug)
    return v[0] if v else None


def topic_of(db: StateDB, briefing_id: str) -> str | None:
    """The topic a saved briefing was written for, if any."""
    with db.connect() as con:
        row = con.execute("SELECT slug FROM topic_versions WHERE briefing_id = ?", (briefing_id,)).fetchone()
    return row[0] if row else None


def last_checks(db: StateDB) -> dict[str, dict[str, str]]:
    with db.connect() as con:
        return {r["slug"]: dict(r) for r in con.execute("SELECT slug, checked_at, outcome FROM topic_checks")}


def _checked(db: StateDB, slug: str, outcome: str, clock: Clock) -> None:
    with db.connect() as con:
        con.execute("INSERT OR REPLACE INTO topic_checks (slug, checked_at, outcome) VALUES (?, ?, ?)",
                    (slug, iso(clock), outcome))


def is_due(topic: Topic, cur: Mapping[str, Any] | None, min_days: float, now: datetime) -> tuple[bool, str]:
    if cur is None:
        return True, "not written yet"
    age = now - datetime.fromisoformat(cur["prepared_at"])
    if age < timedelta(days=min_days):
        return False, f"not due: written {long_date(cur['prepared_at'][:10])}"
    return True, "due"


def _record_ids(events: Iterable[Mapping[str, Any]]) -> set[str]:
    for e in events:
        if e.get("type") == "sources":
            return {str(s.get("record_id")) for s in e.get("sources") or []}
    return set()


# Refreshing


@dataclass
class Outcome:
    slug: str
    outcome: str
    written: str | None = None      # the new briefing's id
    failed: bool = False


@dataclass
class Run:
    """What one run did: each topic's outcome, what it spent, and why it stopped early, if it did."""

    outcomes: list[Outcome] = field(default_factory=list)
    spent_usd: float = 0.0
    stopped: str | None = None

    @property
    def written(self) -> list[Outcome]:
        return [o for o in self.outcomes if o.written]

    @property
    def needs_attention(self) -> bool:
        """A topic failed, or the run stopped before it had been through them all: the timer's alert is sent."""
        return self.stopped is not None or any(o.failed for o in self.outcomes)


def _without_counts(event: Mapping[str, Any]) -> dict[str, Any]:
    """An event as it is kept: no token counts, nor why the model could not read a question (as the briefing
    desk keeps a reader's, ``CouncilsHooks.on_event``)."""
    return {k: v for k, v in event.items() if k not in ("usage", "parse_error")}


def write_one(topic: Topic, pipeline: Pipeline, parts: DeskParts, req: AskRequest,
              clock: Clock) -> tuple[list[dict[str, Any]], dict[str, Any] | None, str | None, float]:
    """Write one topic's briefing through the pipeline, as the briefing desk writes a reader's: (the events to
    keep, the final event, what went wrong, what it cost). Every model call is recorded in the spending record as
    it is reported, and a call whose cost never came in an event (the pipeline failed part-way) is charged for
    what the model's adapter said it had used, or else at the estimate, as the desk does."""
    stages = Stages(clock)
    kept: list[dict[str, Any]] = []
    text: list[str] = []
    final: dict[str, Any] | None = None
    error: str | None = None
    cost = 0.0
    charged = False
    events: Iterator[dict[str, Any]] | None = None
    try:
        events = marking(stages, calling(stages, None, lambda: pipeline.run(req)))
        for ev in events:
            kind = ev.get("type")
            if kind in ("plan", "final", "error") and ev.get("usage"):
                cost += parts.spending.add(KIND, ev.get("model") if kind != "plan" else None, ev["usage"])
                charged = charged or kind != "plan"
            if kind == "text":
                text.append(str(ev.get("text") or ""))
            elif kind == "citation":
                continue
            elif kind == "error":
                error = str(ev.get("message") or "the model declined to answer")
                charged = True
            else:
                kept.append(_without_counts(ev))
                if kind == "final":
                    final = kept[-1]
    except Exception as exc:  # the provider failed, or the pipeline did: the last good briefing stays
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if events is not None:
            close = getattr(events, "close", None)
            if close is not None:
                close()
    if not charged:
        for call in stages.model_calls:
            if call.usage:
                cost += parts.spending.add(KIND, call.model, call.usage)
            else:
                cost += parts.spending.add(KIND, call.model, None, cost_usd=parts.in_progress.estimate_usd)
    if final is not None:
        kept = [e for e in kept if e.get("type") in ("plan", "sources")] + [
            {"type": "text", "text": "".join(text)}, final]
    return kept, final, error, cost


def refresh(settings: Settings, db: StateDB, pipeline: Pipeline, parts: DeskParts, *,
            without_councils: Sequence[str] = (), without_votes: Sequence[str] = (),
            only: Sequence[str] | None = None, force: bool = False, today: date | None = None,
            clock: Clock = SYSTEM_CLOCK, say: Callable[[str], None] = lambda _: None) -> Run:
    """Write the topic briefings that are due (see the module's docstring). ``without_councils`` and
    ``without_votes`` are what is hidden while a concern is decided, left out of the search as for a reader."""
    cfg = settings.section("topics")
    min_days = float(cfg.get("min_days", 6))
    max_run = float(cfg.get("max_run_usd", 2.0))
    mode = str(cfg.get("mode", "summary"))
    failures_to_stop = int(cfg.get("failures_to_stop", 2))
    topics = site_topics(settings)
    if only:
        unknown = sorted(set(only) - {t.slug for t in topics})
        if unknown:
            raise ValueError(f"no topic called {', '.join(unknown)} in {topics_file(settings)}")
        topics = [t for t in topics if t.slug in set(only)]
    now = clock.now()
    day = today or now.astimezone(UTC).date()
    run = Run()
    failures = 0

    def note(t: Topic, outcome: str, *, written: str | None = None, failed: bool = False, keep: bool = True) -> None:
        run.outcomes.append(Outcome(t.slug, outcome, written, failed))
        if keep:
            _checked(db, t.slug, outcome, clock)
        say(f"  {t.slug}: {outcome}")

    for t in topics:
        if run.stopped:
            note(t, f"not written: {run.stopped}", keep=False)
            continue
        cur = current(db, parts.archive, t.slug)
        due, why = (True, "forced") if force else is_due(t, cur, min_days, now)
        if not due:
            note(t, why, keep=False)
            continue
        if not pipeline.has_model():
            note(t, "not written: no API key is set, so no briefing can be written", keep=False)
            continue
        paused = parts.caps.site_paused(pending_usd=parts.in_progress.estimate_usd)
        if paused is not None:
            run.stopped = f"the site's spending cap would be reached ({paused.message})"
            note(t, f"not written: {run.stopped}", keep=False)
            continue
        if run.spent_usd >= max_run:
            run.stopped = f"this run has spent ${run.spent_usd:.2f}, its limit ([topics] max_run_usd ${max_run:.2f})"
            note(t, f"not written: {run.stopped}", keep=False)
            continue
        req = AskRequest(question=t.question, mode=mode, plan=plan_for(t, day, settings.start_date),
                         without_councils=tuple(without_councils), without_votes=tuple(without_votes))
        if cur is not None and not force:
            plan, _ = pipeline.make_plan(req)
            _, sources = pipeline.find(plan, req)
            old = parts.archive.get(cur["briefing_id"])
            found = {str(s.card().get("record_id")) for s in sources}
            if old is not None and found and found == _record_ids(old.events):
                note(t, "evidence unchanged: the same passages as the current briefing, which stays")
                continue
        kept, final, error, cost = write_one(t, pipeline, parts, req, clock)
        run.spent_usd += cost
        answer = (final or {}).get("answer")
        if error or not answer:
            failures += 1
            note(t, f"failed, so the previous briefing stays: {error or 'no briefing was written'}", failed=True)
            if failures >= failures_to_stop:
                run.stopped = f"{failures} topics failed in this run"
            continue
        if answer.get("no_records"):
            note(t, "no records found, so the previous briefing stays" if cur else "no records found: not written")
            continue
        plan_ev = next((e for e in kept if e.get("type") == "plan"), {})
        filters = (plan_ev.get("plan") or {}).get("filters") or {}
        bid = parts.archive.new_id()
        final["briefing_id"] = bid
        saved = parts.archive.save(t.question, {"mode": mode, "topic": t.slug}, kept, id=bid)
        with db.connect() as con:
            con.execute("INSERT INTO topic_versions (briefing_id, slug, prepared_at, records_from, records_to) "
                        "VALUES (?, ?, ?, ?, ?)", (saved.id, t.slug, saved.created_at, filters.get("date_from"),
                                                   filters.get("date_to")))
        note(t, f"written ({saved.id}, ${cost:.3f})", written=saved.id)
    return run


def listing(settings: Settings, db: StateDB, archive: SavedBriefings) -> list[dict[str, Any]]:
    """Every topic with its current version (or None) and how many versions stand, in the file's order."""
    checks = last_checks(db)
    out = []
    for t in site_topics(settings):
        vs = versions(db, archive, t.slug)
        out.append({"topic": t, "current": vs[0] if vs else None, "versions": vs, "last_check": checks.get(t.slug)})
    return out
