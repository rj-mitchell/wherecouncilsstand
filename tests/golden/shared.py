"""What the golden recorder (record.py, run on the site's code as it was before wts-core) and the parity tests
(tests/test_parity.py, run on the code as it is now) both need: a clock that is told the time, the made-up record
the scenarios run on, a scripted pipeline, a simulated Backblaze B2, and the scripts themselves. Nothing here
imports the site's code, so it reads the same under either.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import re
import sqlite3
import stat
import tempfile
import threading
from collections.abc import Callable, Iterator
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx

GOLDEN = Path(__file__).parent
START = "2026-11-13T12:00:00+00:00"          # where every scenario's clock starts, unless it says otherwise
SALT = "5a" * 16                             # the day's visitor secret, fixed so that visitors' codes are the same
ADDRESS = "testclient"                       # the address FastAPI's test client asks from
BARNSLEY, GUILDFORD = "E08000038", "E07000209"
VOTE = f"{BARNSLEY}:1:10:0"


class Clock:
    """A clock that says what it is told: ``now`` and ``monotonic`` move together (the shape of wts-core's
    ``ports.Clock``, so the same clock drives the site's code before and after)."""

    def __init__(self, start: str = START) -> None:
        self._now = datetime.fromisoformat(start)
        self._monotonic = 1000.0

    def now(self) -> datetime:
        return self._now

    def monotonic(self) -> float:
        return self._monotonic

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)
        self._monotonic += seconds

    def set(self, when: str) -> None:
        new = datetime.fromisoformat(when)
        self._monotonic += max((new - self._now).total_seconds(), 0.0)
        self._now = new


def frozen(clock: Clock) -> type[datetime]:
    """``datetime`` for a module of the old code, which reads the time itself: ``now`` is the scenario's clock."""

    class Frozen(datetime):
        @classmethod
        def now(cls, tz: Any = None) -> datetime:  # type: ignore[override]
            return clock.now()

    return Frozen


def read(name: str) -> Any:
    return json.loads((GOLDEN / name).read_text(encoding="utf-8"))


def write(out: Path, name: str, value: Any) -> None:
    (out / name).write_text(json.dumps(value, indent=1, ensure_ascii=False, sort_keys=True, default=str) + "\n",
                            encoding="utf-8")


def plain(value: Any, *folders: tuple[Path, str]) -> Any:
    """A value as it is stored: each scenario's own folder written as its name ("<tmp>", "<root>")."""
    text = json.dumps(value, default=str)
    for folder, name in folders:
        text = text.replace(json.dumps(str(folder))[1:-1], name)
    return json.loads(text)


# ---- settings ------------------------------------------------------------------------------------------------------

SAMPLE_CONFIG = """\
[paths]
data_dir = "{data_dir}"

[answer]
model = "sample-model"

[usage]
requests_per_minute = 5
price_input_per_mtok = 1.0

[usage.models."sample-model"]
price_input_per_mtok = 9.0
"""
LOCAL_SETTINGS = """\
[usage]
daily_spend_cap_usd = 1.5

[usage.models."claude-opus-5-5"]
price_input_per_mtok = 5.0

[site]
donate_url = "https://example.org/give"

[of_this_server]
only = true
"""
SETTINGS_CASES: list[dict[str, Any]] = [
    {"name": "the real settings file", "config": "real", "env": {}},
    {"name": "the real file, the data folder from the environment (absolute)", "config": "real",
     "env": {"COUNCILS_DATA_DIR": "<tmp>/elsewhere"}},
    {"name": "the real file, the data folder from the environment (relative)", "config": "real",
     "env": {"COUNCILS_DATA_DIR": "other/data"}},
    {"name": "the real file, an empty data folder in the environment", "config": "real",
     "env": {"COUNCILS_DATA_DIR": ""}},
    {"name": "the real file, with a local settings file in the data folder", "config": "real",
     "env": {"COUNCILS_DATA_DIR": "<tmp>/with-local"}, "local": LOCAL_SETTINGS},
    {"name": "the real file, with overrides", "config": "real", "env": {"COUNCILS_DATA_DIR": "<tmp>/elsewhere"},
     "overrides": {"embedding.backend": "hashing", "embedding.dim": 64, "usage.daily_spend_cap_usd": 0.0,
                   "made_up.key": "value"}},
    {"name": "the real file, a local settings file and overrides over it", "config": "real",
     "env": {"COUNCILS_DATA_DIR": "<tmp>/with-local"}, "local": LOCAL_SETTINGS,
     "overrides": {"usage.daily_spend_cap_usd": 9.0, "site.donate_url": ""}},
    {"name": "a sample file named by COUNCILS_CONFIG, with none of this site's sections", "config": SAMPLE_CONFIG,
     "data_dir": "<tmp>/sample-data", "env": {}},
    {"name": "a sample file with a relative data folder", "config": SAMPLE_CONFIG, "data_dir": "var/data", "env": {}},
    {"name": "a sample file, the data folder from the environment over the file's", "config": SAMPLE_CONFIG,
     "data_dir": "var/data", "env": {"COUNCILS_DATA_DIR": "<tmp>/from-env"}},
    {"name": "a sample file given as an argument", "config": SAMPLE_CONFIG, "data_dir": "var/data", "env": {},
     "as_argument": True},
]


def settings_given(s: Any) -> dict[str, Any]:
    """Everything the site's settings object gives: the file as read, and each of its own accessors."""
    return {"raw": s.raw, "data_dir": str(s.data_dir), "config_path": str(s.config_path), "overrides": s.overrides,
            "start_date": s.start_date.isoformat(), "modgov": s.modgov, "archive": s.archive, "ranking": s.ranking,
            "answer": s.answer, "embedding": s.embedding, "usage": s.usage, "raw_dir": str(s.raw_dir),
            "parquet_dir": str(s.parquet_dir), "index_dir": str(s.index_dir), "models_dir": str(s.models_dir),
            "site": s.section("site"), "no_such_section": s.section("no_such_section")}


# ---- the per-minute limit, and a visitor's code ---------------------------------------------------------------------

LIMITER_SCRIPT: list[list[Any]] = (
    [[0.0, "a"]] * 21 + [[0.0, "b"], [0.0, ""]] + [[30.0, "a"], [59.9, "a"], [60.0, "a"], [60.1, "a"]]
    + [[60.1, "a"]] * 20 + [[60.2, "b"]] * 20 + [[120.0, "b"], [120.3, "b"], [120.3, "b"], [200.0, "a"],
                                                 [200.0, "b"]])
ADDRESSES: list[str | None] = [
    None, "", "testclient", "203.0.113.7", "203.0.113.8", "2001:db8:1:2::1", "2001:db8:1:2:9::9", "2001:db8:1:3::1",
    "::ffff:203.0.113.7", "::1", "not an address"]

# ---- cost: a table of usages and models -----------------------------------------------------------------------------

USAGES: list[dict[str, Any] | None] = [
    None, {},
    {"input_tokens": 0, "output_tokens": 0, "cache_read_tokens": 0, "cache_write_tokens": 0},
    {"input_tokens": 1000, "output_tokens": 200, "cache_read_tokens": 0, "cache_write_tokens": 0},
    {"input_tokens": 9000, "output_tokens": 700, "cache_read_tokens": 3000, "cache_write_tokens": 2000},
    {"input_tokens": 31_000, "output_tokens": 1900, "cache_read_tokens": 0, "cache_write_tokens": 3600},
    {"input_tokens": 1_000_000, "output_tokens": 1_000_000, "cache_read_tokens": 1_000_000,
     "cache_write_tokens": 1_000_000},
    # the SDK's own names: input_tokens leaves out the cache writes and reads
    {"input_tokens": 1200, "output_tokens": 800, "cache_creation_input_tokens": 20_000,
     "cache_read_input_tokens": 5000},
    {"input_tokens": 1000, "output_tokens": 200, "cache_read_input_tokens": 3000, "cache_creation_input_tokens": 500},
    {"input_tokens": 1000, "cache_read_input_tokens": None},
    {"input_tokens": 1000, "output_tokens": None},
    {"input_tokens": 1500, "output_tokens": 200, "cache_read_tokens": 0, "cache_read_input_tokens": 3000,
     "cache_write_tokens": 500},
    {"output_tokens": 37},
    {"input_tokens": 105_123, "output_tokens": 2431, "cache_read_tokens": 3712, "cache_write_tokens": 0},
]
MODELS: list[str | None] = [None, "claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-5-5-20261001",
                            "claude-opus-5-5", "a-model-nobody-priced"]

# ---- the answer cache's key: a table of questions and options --------------------------------------------------------

EARLIER = [{"question": "What have councils decided about bin collections?", "answer": "Barnsley kept them weekly."}]
KEY_BODIES: list[dict[str, Any]] = [
    {"question": "What have councils decided about bin collections?"},
    {"question": "  what have councils   decided about BIN collections? "},
    {"question": "What have councils decided about bin collections?", "mode": "comprehensive"},
    {"question": "What have councils decided about bin collections?", "sources_only": True},
    {"question": "What have councils decided about bin collections?",
     "plan": {"search_text": "bin collections", "filters": {"councils": [BARNSLEY], "date_from": "2023-01-01"}}},
    {"question": "And what about Barnsley?", "history": EARLIER},
    {"question": "And what about Barnsley?", "history": [{"question": "Something else?", "answer": "B"}]},
    {"question": "And what about Barnsley?"},
    {"question": "Beth mae cynghorau wedi'i benderfynu am gasgliadau biniau? “Dyfyniad” – £5"},
]
KEY_STAMPS: list[float] = [0.0, 1731500000.25]

# ---- the caps, over scripted spending --------------------------------------------------------------------------------
# Each step: ["spend", kind, model, usage number (of USAGES), visitor], ["check", visitor, pending], ["paused",
# pending], ["count", visitor], ["spent"], ["set", time]. A step of kind "answer" is also counted as one of the
# visitor's briefings for the day, as the site's route does.

CAPS_LIMITS = {"per_visitor_daily_questions": 3, "daily_spend_cap_usd": 0.05, "monthly_spend_cap_usd": 0.12}
CAPS_START = "2026-11-29T22:00:00+00:00"
CAPS_SCRIPT: list[list[Any]] = [
    ["check", "v1", 0.0], ["paused", 0.0], ["count", "v1"], ["spent"],
    ["spend", "parse", "claude-haiku-5-5", 3, "v1"], ["spend", "answer", "claude-sonnet-5-5", 3, "v1"],
    ["count", "v1"], ["count", "v2"], ["spent"], ["check", "v1", 0.0],
    ["check", "v1", 0.04], ["check", "v1", 0.045], ["check", "v1", 0.0461], ["paused", 0.15],
    ["spend", "answer", "claude-sonnet-5-5", 3, "v1"], ["spend", "answer", "claude-sonnet-5-5", 3, "v1"],
    ["count", "v1"], ["check", "v1", 0.0], ["check", "v2", 0.0], ["check", None, 0.0], ["paused", 0.0],
    ["spend", "answer", "claude-sonnet-5-5", 4, "v2"], ["spent"], ["check", "v2", 0.0], ["check", "v1", 0.0],
    ["paused", 0.0],
    ["spend", "parse", None, 3, None], ["spend", "answer", "claude-sonnet-5-5", None, "v2"], ["count", "v2"],
    ["set", "2026-11-29T23:59:59+00:00"], ["check", "v2", 0.0], ["count", "v1"],
    ["set", "2026-11-30T00:00:00+00:00"], ["count", "v1"], ["spent"], ["check", "v1", 0.0], ["paused", 0.0],
    ["paused", 0.05],
    ["spend", "answer", "claude-sonnet-5-5", 5, "v3"], ["spent"], ["check", "v3", 0.0], ["paused", 0.0],
    ["set", "2026-11-30T23:59:59+00:00"], ["paused", 0.0],
    ["set", "2026-12-01T00:00:00+00:00"], ["spent"], ["paused", 0.0], ["check", "v3", 0.0], ["paused", 0.12],
    ["paused", 0.049], ["paused", 0.05],
]
# briefings in progress: ["start", key], ["finish", key], ["pending", besides]
IN_PROGRESS = {"per_key": 2, "total": 3, "estimate_usd": 0.15}
IN_PROGRESS_SCRIPT: list[list[Any]] = [
    ["pending", 0], ["start", "a"], ["start", "a"], ["start", "a"], ["pending", 0], ["pending", 1], ["start", "b"],
    ["start", "c"], ["pending", 1], ["finish", "a"], ["start", "c"], ["start", "c"], ["start", "a"], ["finish", "a"],
    ["finish", "b"], ["finish", "c"], ["finish", "c"], ["pending", 0], ["pending", 3], ["start", "d"],
]
# the answer cache: ["put", key, hours], ["get", key, hours], ["advance", seconds], ["keys"]
CACHE_EVENTS = [{"type": "plan", "plan": {"question": "Q"}}, {"type": "text", "text": "words"},
                {"type": "final", "answer": {"segments": []}, "cached": True, "when": date(2026, 11, 13)}]
CACHE_SCRIPT: list[list[Any]] = [
    ["get", "k1", 168], ["put", "k1", 168], ["get", "k1", 168], ["get", "k1", 0], ["advance", 3600.0],
    ["get", "k1", 168], ["get", "k1", 1], ["get", "k1", 0.5], ["put", "k2", 168], ["advance", 167 * 3600.0 - 1],
    ["get", "k1", 168], ["advance", 1.0], ["get", "k1", 168], ["advance", 1.0], ["get", "k1", 168], ["get", "k2", 168],
    ["keys"], ["put", "k3", 168], ["keys"], ["put", "k2", 168], ["get", "k2", 168], ["advance", 200 * 3600.0],
    ["put", "k4", 0], ["keys"], ["get", "k4", 0], ["get", "k4", 168],
]


# ---- the made-up record: two councils, two meetings, one named vote --------------------------------------------------

TODAY = date(2026, 10, 24)


def _meeting(gss: str, mid: int, d: date, kind: str = "council") -> dict[str, Any]:
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "council": gss, "committee_id": 1,
            "committee_title": "Full Council" if kind == "council" else "Cabinet", "kind": kind, "date": d,
            "year": d.year, "status": "", "location": "", "webcast": False, "minutes_published": True, "items": 1,
            "items_with_minutes": 1, "earlier_minutes": "", "minutes_document": "", "attendees": 3, "url": "u"}


def _item(gss: str, mid: int, iid: int, d: date, title: str, text: str) -> dict[str, Any]:
    return {"item_id": f"{gss}:{mid}:{iid}", "meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year,
            "position": 0, "number": f"{iid}.", "title": title, "agenda_text": "", "minutes_text": text,
            "minutes_source": "html", "vote_tables": "", "is_decision": False, "is_restricted": False,
            "is_call_in": False, "declaration_count": 0, "documents": 0, "url": f"https://example/{gss}/{iid}"}


def _member(gss: str, mid: int, d: date, member_id: str, name: str, party: str) -> dict[str, Any]:
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year, "member_id": member_id,
            "member_type": "U", "name": name, "role": "Committee Member", "attendance": "Present, as expected",
            "party_label": party, "party": party, "ward": ""}


def store_record(write_table: Callable[[str, str, list[dict[str, Any]]], None]) -> None:
    """The record the tests of the pipeline run on (tests/test_pipeline.py), with Barnsley's named vote.
    ``write_table(table, gss, rows)`` is the site's own ``store.parquet.write`` with its folder given."""
    d1, d2 = date(2025, 2, 26), date(2025, 3, 5)
    write_table("meetings", BARNSLEY, [_meeting(BARNSLEY, 1, d1)])
    write_table("items", BARNSLEY, [_item(
        BARNSLEY, 1, 10, d1, "Notice of Motion - Weekly Bin Collections",
        "Councillor Kitching moved that weekly bin collections be restored.\nMr J Bloggs asked about recycling "
        "centres.\nUpon being put to the vote the motion was lost.")])
    write_table("attendance", BARNSLEY, [
        _member(BARNSLEY, 1, d1, "1", "Councillor Hannah Kitching", "LD"),
        _member(BARNSLEY, 1, d1, "2", "Councillor Sir Steve Houghton", "LAB"),
        _member(BARNSLEY, 1, d1, "3", "Councillor Robin Franklin", "LAB")])
    write_table("meetings", GUILDFORD, [_meeting(GUILDFORD, 2, d2)])
    write_table("items", GUILDFORD, [_item(
        GUILDFORD, 2, 20, d2, "Waste and Recycling Strategy",
        "Councillor Julia McShane introduced the waste and recycling strategy, including fortnightly bin "
        "collections.\nRESOLVED that the strategy be adopted.")])
    write_table("attendance", GUILDFORD, [
        _member(GUILDFORD, 2, d2, "7", "Councillor Julia McShane", "LD"),
        _member(GUILDFORD, 2, d2, "8", "Councillor Tim Anderson", "LD"),
        _member(GUILDFORD, 2, d2, "9", "Councillor Paul Spooner", "CON")])
    write_table("votes", GUILDFORD, [])
    write_table("votes", BARNSLEY, [
        {"vote_id": VOTE, "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
         "date": d1, "year": 2025, "question": "motion", "outcome": "lost", "member_id": m,
         "name": n, "vote": side, "excerpt": "Upon being put to the vote the motion was lost."}
        for m, n, side in (("1", "Kitching", "for"), ("2", "Houghton", "against"), ("3", "Franklin", "against"))])


SHELL = ('<!doctype html><html><head><title>x</title></head><body><main id="main"><div id="app"></div>'
         "</main></body></html>")


def web_pages(folder: Path) -> Path:
    """The built pages cut down to what the server fills in: a shell for each page it writes text into."""
    folder.mkdir(parents=True, exist_ok=True)
    for name in ("index", "councils", "council", "vote", "about", "corrections", "404"):
        (folder / f"{name}.html").write_text(SHELL, encoding="utf-8")
    return folder


class FakeStream:
    def __init__(self, blocks: list[dict[str, Any]], stop_reason: str = "end_turn") -> None:
        self.blocks, self.stop_reason = blocks, stop_reason

    def __enter__(self) -> FakeStream:
        return self

    def __exit__(self, *a: Any) -> bool:
        return False

    def __iter__(self) -> Iterator[Any]:
        for b in self.blocks:
            yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(type="text_delta", text=b["text"]))

    def get_final_message(self) -> Any:
        content = [SimpleNamespace(type="text", text=b["text"],
                                   citations=[SimpleNamespace(type="search_result_location", **c)
                                              for c in b.get("citations", [])]) for b in self.blocks]
        return SimpleNamespace(content=content, stop_reason=self.stop_reason, model="claude-sonnet-5-5",
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))


class FakeClient:
    """In place of the model's SDK (as tests/test_pipeline.py's): it cites the first passage of the first source,
    then adds a sentence with a loaded word and no citation, an opener about the records and an American spelling.
    ``refuse`` makes it decline."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.parses: list[dict[str, Any]] = []      # each question the model was asked to read, when ``parsed`` is set
        self.parsed: dict[str, Any] | None = None   # what the model reads a question as; None: it fails to
        self.refuse = False
        self.beta = SimpleNamespace(messages=SimpleNamespace(stream=self._stream))
        self.messages = SimpleNamespace(stream=self._stream, parse=self._parse)

    def _parse(self, **kw: Any) -> Any:
        if self.parsed is None:
            raise RuntimeError("offline parse in tests")
        self.parses.append(kw)
        return SimpleNamespace(stop_reason="end_turn", parsed_output=kw["output_format"](**self.parsed),
                               usage=SimpleNamespace(input_tokens=1000, output_tokens=100, cache_read_input_tokens=0,
                                                     cache_creation_input_tokens=0))

    def _stream(self, **kw: Any) -> FakeStream:
        self.calls.append(kw)
        if self.refuse:
            return FakeStream([], stop_reason="refusal")
        first = next(b for b in kw["messages"][0]["content"] if b["type"] == "search_result")
        quote = first["content"][0]["text"]
        return FakeStream([
            {"text": "Across the records retrieved, the minutes record that "},
            {"text": quote[:60], "citations": [{"search_result_index": 0, "cited_text": quote, "source": "x"}]},
            {"text": " The scheme was a fiasco that residents across the borough opposed for many months, and its "
                     "organization was criticized."},
            {"text": " Cllr. Kitching said "},
            {"text": "\"weekly bin collections be restored\"",
             "citations": [{"search_result_index": 0, "cited_text": quote, "source": "x"}]},
            {"text": " and that \"the borough was united behind it\"."},
        ])


def without_scores(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Events as they are compared: each source's card without its ranking figures, which are sums of fractions
    that another computer may round differently in the last place."""
    return [{**e, "sources": [{k: v for k, v in card.items() if k != "ranking"} for card in e["sources"]]}
            if e.get("type") == "sources" else e for e in events]


# ---- what the model is sent ---------------------------------------------------------------------------------------
# Questions through the real pipeline on the made-up record, for the requests themselves: the instructions, the
# sources as documents, the question as the site words it, the model, the effort, the fallback.

PARSED = {"search_text": "bin collections", "date_from": "2024-01-01", "date_to": None, "councils": ["Barnsley"],
          "control": [], "parties": [], "nations": [], "council_types": [], "kinds": [], "group_by": "control",
          "wants_votes": False, "interpretation": "Bin collections in Barnsley, organized since 2024."}
MODEL_ASKS: list[dict[str, Any]] = [
    {"case": "a summary", "json": {"question": "What have councils decided about bin collections?"}},
    {"case": "a comprehensive briefing", "json": {"question": "What have councils decided about recycling?",
                                                  "mode": "comprehensive"}},
    {"case": "a follow-up, with what was asked before", "json": {
        "question": "And what about Barnsley's bin collections?", "history": [
            {"question": "What have councils decided about bin collections?", "answer": "A" * 700},
            {"question": "Second?", "answer": "B"}, {"question": "Third?", "answer": "C"},
            {"question": "Fourth?", "answer": "D"}]}},
    {"case": "the reader's own plan, grouped by region", "json": {
        "question": "Bins by region?", "plan": {"search_text": "bin collections", "group_by": "region",
                                                "filters": {"control": ["LAB", "LD"], "date_from": "2025-01-01"}}}},
    {"case": "a question the model reads first", "parsed": True, "json": {
        "question": "What has Barnsley decided about bin collections since 2024?"}},
    {"case": "sources only, the question read by the model", "parsed": True, "json": {
        "question": "What has Barnsley decided about bin collections since 2024?", "sources_only": True}},
]


def requests_made(fake: FakeClient) -> dict[str, Any]:
    """Every request the stand-in for the model's SDK was given, as it is stored: each briefing asked for and each
    question it was asked to read, argument for argument."""
    def stored(kwargs: dict[str, Any]) -> dict[str, Any]:
        return json.loads(json.dumps({k: (v.__name__ if k == "output_format" else v) for k, v in kwargs.items()},
                                     default=str))

    return {"briefings": [stored(k) for k in fake.calls], "questions_read": [stored(k) for k in fake.parses]}


# ---- an index made by the old code -------------------------------------------------------------------------------
# tests/fixtures/old-index is the search index the old code built from the made-up record (its tables, its
# state.json), kept as it left it. These are the searches made on it, and what each gave.

INDEX_QUERIES: list[dict[str, Any]] = [
    {"words": "bin collections", "where": None},
    {"words": "weekly bin collections restored", "where": f"gss IN ('{BARNSLEY}')"},
    {"words": "waste and recycling strategy", "where": "control IN ('LD')"},
    {"words": "motion \"lost\" (vote)", "where": None},
    {"words": "nothing at all like this zebra", "where": None},
    {"words": "bins", "where": "date >= DATE '2025-03-01'"},
    {"meaning": "weekly bin collections", "where": None},
    {"meaning": "the waste strategy was adopted", "where": f"gss IN ('{GUILDFORD}')"},
    {"meaning": "councillors voted on the motion", "where": "array_has_any(parties, ['LD'])"},
]


def index_answers(words: Callable[[str, str | None, int], list[dict[str, Any]]],
                  meaning: Callable[[Any, str | None, int], list[dict[str, Any]]],
                  embed: Callable[[str], Any]) -> list[dict[str, Any]]:
    """Each search of INDEX_QUERIES: the passages found, in order, with the score or distance of each."""
    out = []
    for query in INDEX_QUERIES:
        if "words" in query:
            hits = words(query["words"], query["where"], 10)
            found = [[h["passage_id"], round(float(h["_score"]), 3)] for h in hits]
        else:
            hits = meaning(embed(query["meaning"]), query["where"], 10)
            found = [[h["passage_id"], round(float(h["_distance"]), 3)] for h in hits]
        out.append({**query, "found": found})
    return out


def search_given(result: Any) -> dict[str, Any]:
    """What the engine's search gave, as it is stored: each record chosen (without its ranking figures) and the
    summary of the evidence."""
    records = [{k: v for k, v in r.items() if k != "ranking"} for r in result.records]
    return json.loads(json.dumps({"records": records, "candidates": result.candidates,
                                  "semantic": result.semantic_available, "evidence": result.evidence}, default=str))


REAL_ASKS: list[dict[str, Any]] = [
    {"case": "a briefing written by the real pipeline", "json": {
        "question": "What have councils decided about bin collections?"}},
    {"case": "the same again, from the cache", "json": {
        "question": "what have councils decided about  bin collections?"}},
    {"case": "no records, with the reader's own plan", "json": {
        "question": "anything", "plan": {"search_text": "bin collections", "filters": {
            "date_from": "2019-01-01", "date_to": "2019-01-02"}}}},
    {"case": "the model declines", "refuse": True, "json": {
        "question": "What has Barnsley decided about weekly bin collections?"}},
    {"case": "sources only, read by the free rules once the cap is reached", "cap": 0.0, "json": {
        "question": "What have councils decided about bin collections?", "sources_only": True,
        "plan": {"search_text": "bin collections", "filters": {}}}},
]
# what the pages and the other endpoints give on the made-up record, with nothing hidden and two statements shown
PAGES_READ: list[str] = [
    "/api/health", "/api/councils", f"/api/councils/{BARNSLEY}", f"/api/councils/{GUILDFORD.lower()}",
    "/api/councils/E99999999", f"/api/votes/{VOTE}", "/api/votes/E07000209:9:9:0", "/sitemap.xml",
    f"/councils/{BARNSLEY}", f"/votes/{VOTE}", "/votes/E07000209:9:9:0", "/councils/E99999999", "/",
    "/councils", "/b/abc123", "/corrections", "/about", "/no-such-page",
    f"/api/statements?page=/votes/{VOTE}", f"/api/statements?council={BARNSLEY.lower()}",
    f"/api/statements?page=https://wherecouncilsstand.com/councils/{BARNSLEY}", "/api/statements",
    "/api/statements?page=/about", "/api/briefings/abc123", "/api/briefings/gone456", "/api/briefings/nosuch",
    "/api/briefings/old789",
]

# ---- a scripted pipeline, in this site's shapes ------------------------------------------------------------------

Q = "What have councils said about closing public toilets since 2020?"
Q2 = "And what did the district councils decide?"
ASKED_BEFORE = [{"question": Q, "answer": "Barnsley's cabinet agreed to keep them open."}]
PARSE_USAGE = {"input_tokens": 1200, "output_tokens": 80, "cache_read_tokens": 0, "cache_write_tokens": 0}
ANSWER_USAGE = {"input_tokens": 9000, "output_tokens": 700, "cache_read_tokens": 3000, "cache_write_tokens": 2000}
DECLINED = "The model declined to answer this question."
NO_KEY_NOTE = "Showing the evidence only (no Anthropic API key set)."
CARDS = [
    {"n": 1, "kind": "minutes", "title": "Barnsley, Cabinet, 12 March 2025", "url": "https://example/1",
     "gss": BARNSLEY, "group": "Councils controlled by Labour", "date": date(2025, 3, 12)},
    {"n": 2, "kind": "minutes", "title": "Guildford, Full Council, 5 March 2025", "url": "https://example/2",
     "gss": GUILDFORD, "group": "Councils controlled by the Liberal Democrats"},
    {"n": 3, "kind": "minutes", "title": "Barnsley, Full Council, 26 February 2025", "url": "https://example/3",
     "gss": BARNSLEY, "group": "Councils controlled by Labour"},
]


def an_answer() -> dict[str, Any]:
    """A checked briefing as the site's verifier reports one: a cited sentence with a quotation, a sentence marked
    for checking that today's rules clear when it is shown again (it only leads in to the citation after it), one
    that stays marked, and a judgemental-word mark for a word on no list."""
    segments = [
        {"text": "Barnsley's cabinet said the toilets were \"well used\".", "sources": [1],
         "cited": [{"source": 1, "cited_text": "the public toilets in the town centre are well used"}],
         "status": "cited", "loaded": [], "misquotes": []},
        {"text": " In the debate that followed:", "sources": [], "cited": [], "status": "unsupported", "loaded": [],
         "misquotes": []},
        {"text": " Guildford agreed to review opening hours.", "sources": [2],
         "cited": [{"source": 2, "cited_text": "RESOLVED that opening hours be reviewed"}], "status": "cited",
         "loaded": [], "misquotes": []},
        {"text": " This was a turning point for every council in the county.", "sources": [], "cited": [],
         "status": "unsupported", "loaded": [{"start": 12, "end": 19, "word": "turning"}], "misquotes": []},
    ]
    markdown = "".join(s["text"] for s in segments)
    return {"segments": segments, "markdown": markdown, "no_records": False, "citations_total": 2,
            "citations_invalid": 0, "grounded_ratio": 0.5, "unsupported_segments": 2, "loaded_words": 1,
            "quotes_total": 1, "quotes_unverified": 0}


def no_records_answer() -> dict[str, Any]:
    return {"segments": [{"text": "No records found. The minutes contain no records matching this question and "
                                  "these filters.", "sources": [], "cited": [], "status": "connective"}],
            "markdown": "No records found.", "no_records": True, "citations_total": 0, "citations_invalid": 0,
            "grounded_ratio": 1.0, "unsupported_segments": 0}


class FakePlan:
    """What the site's ``QueryPlan`` gives its route: the question, whether the model failed to read it, and itself
    as a dictionary. ``parser`` says who read the question, so the bytes sent show it."""

    def __init__(self, question: str, parser: str, parse_error: str | None = None) -> None:
        self.question, self.parser, self.parse_error = question, parser, parse_error
        self.group_by = "control"

    def to_dict(self) -> dict[str, Any]:
        return {"question": self.question, "parser": self.parser, "filters": {"date_from": "2020-01-01"}}


def offline_reader(question: str, *args: Any, **kwargs: Any) -> FakePlan:
    """In place of the site's ``parse_offline``, which reads today's date: the free rules read the question."""
    return FakePlan(question, "offline")


class FakeSource:
    def __init__(self, card: dict[str, Any]) -> None:
        self._card, self.kind = card, "minutes"

    def card(self) -> dict[str, Any]:
        return dict(self._card)


class ScriptedPipeline:
    """In place of the site's ``Pipeline``: ``run`` sends the events of the next behaviour in ``plays`` (or of
    ``"written"``), in the site's own shapes, moving the clock as a real one takes time. ``make_plan`` and ``find``
    are what the site's sources-only search asks of it. (The method wts-core's own tests drive this site with:
    its tests/briefing_sites.py.)"""

    def __init__(self, clock: Clock, model: str, *, has_model: bool = True) -> None:
        self.clock, self.model, self.model_on = clock, model, has_model
        self.today = date(2026, 11, 13)
        self.plays: list[str] = []
        self.calls: list[str] = []  # the behaviours run, and "make_plan" for each question the model read alone
        self.entered, self.gate, self.closed = threading.Event(), threading.Event(), threading.Event()

    def has_model(self) -> bool:
        return self.model_on

    def make_plan(self, req: Any) -> tuple[FakePlan, dict[str, int] | None]:
        self.calls.append("make_plan")
        if not self.model_on:
            return FakePlan(req.question, "offline"), None
        return FakePlan(req.question, "model"), dict(PARSE_USAGE)

    def find(self, plan: Any, req: Any) -> tuple[Any, list[FakeSource]]:
        result = SimpleNamespace(candidates=12, semantic_available=True, evidence={"records": 3}, records=[1, 2, 3])
        return result, [FakeSource(c) for c in CARDS]

    def _plan(self, question: str, **more: Any) -> dict[str, Any]:
        usage = dict(PARSE_USAGE) if self.model_on else None
        return {"type": "plan", "plan": FakePlan(question, "model" if self.model_on else "offline").to_dict(),
                "usage": usage, **more}

    def _sources(self) -> dict[str, Any]:
        return {"type": "sources", "sources": [dict(c) for c in CARDS], "candidates": 12, "semantic": True,
                "evidence": {"records": 3, "groups": {"Councils controlled by Labour": 2}}}

    def run(self, req: Any) -> Iterator[dict[str, Any]]:
        play = self.plays.pop(0) if self.plays else "written"
        self.calls.append(play)
        tick = self.clock.advance
        tick(0.4)
        yield self._plan(req.question, **({"parse_error": "AuthenticationError: bad key"} if play == "unread" else {}))
        tick(0.3)
        yield self._sources()
        if play == "no_records":
            yield {"type": "final", "answer": no_records_answer(), "usage": None}
            return
        if not self.model_on:
            yield {"type": "final", "answer": None, "usage": None, "note": NO_KEY_NOTE}
            return
        if play == "held":  # a briefing still being written while another question arrives
            self.entered.set()
            assert self.gate.wait(20)
        tick(1.5)
        # as the model really sends them: a citation comes before the text of the block it belongs to
        yield {"type": "citation", "search_result_index": 0,
               "cited_text": "the public toilets in the town centre are well used"}
        yield {"type": "text", "text": "Barnsley's cabinet said the toilets "}
        if play == "raises":
            raise RuntimeError("the model's stream broke")
        if play == "left":  # the reader goes while the briefing is being written
            try:
                self.entered.set()
                assert self.gate.wait(20)
                for word in ("were ", "\"well ", "used\"."):
                    tick(0.1)
                    yield {"type": "text", "text": word}
            finally:
                self.closed.set()
            raise AssertionError("the pipeline was not stopped when the reader left")
        yield {"type": "text", "text": "were \"well used\"."}
        yield {"type": "citation", "search_result_index": 1, "cited_text": "RESOLVED that opening hours be reviewed"}
        yield {"type": "text", "text": " Guildford agreed to review opening hours."}
        tick(2.0)
        if play == "declined":  # the call was still paid for, so its token counts go with the event to be recorded
            yield {"type": "error", "message": DECLINED, "usage": dict(ANSWER_USAGE), "model": self.model}
            return
        tick(0.6)
        yield {"type": "final", "answer": an_answer(), "usage": dict(ANSWER_USAGE), "model": self.model,
               "stop_reason": "end_turn"}


class Side:
    """One telling of a scenario: the site's app with a scripted pipeline, whichever code it is running on. The
    recorder and the parity tests each build one (the app, its test client, the pipeline, and how to read what was
    written and to take a response piece by piece)."""

    def __init__(self, app: Any, client: Any, pipeline: ScriptedPipeline, clock: Clock, *,
                 rows: Callable[[], dict[str, list[list[Any]]]], stream: Callable[..., Iterator[bytes]],
                 briefings_today: Callable[[str], int]) -> None:
        self.app, self.client, self.pipeline, self.clock = app, client, pipeline, clock
        self.rows, self.stream, self.briefings_today = rows, stream, briefings_today

    def ask(self, question: str, play: str = "written", **body: Any) -> list[Any]:
        """One question through ``/api/ask``: the status and the exact text of the answer."""
        if play != "written":
            self.pipeline.plays.append(play)
        response = self.client.post("/api/ask", json={"question": question, **body})
        return [response.status_code, response.content.decode("utf-8")]

    def another_client(self) -> Any:
        from fastapi.testclient import TestClient

        return TestClient(self.app)


def _while_one_is_written(side: Side, then: Callable[[], list[Any]]) -> list[Any]:
    """Start a briefing that stays in progress, do ``then`` while it is, and let it finish. What was sent: the held
    briefing's answer first, then whatever ``then`` sent."""
    side.pipeline.plays.append("held")
    held: list[Any] = []
    other = side.another_client()
    thread = threading.Thread(target=lambda: held.append(other.post("/api/ask", json={"question": Q})))
    thread.start()
    assert side.pipeline.entered.wait(20)
    try:
        sent = then()
    finally:
        side.pipeline.gate.set()
        thread.join(30)
    return [[held[0].status_code, held[0].content.decode("utf-8")], *sent]


def _the_reader_leaves(side: Side) -> list[Any]:
    side.pipeline.plays.append("left")
    stream = side.stream(Q)
    received = b""
    for chunk in stream:
        received += chunk
        if chunk.startswith(b"event: text"):
            break
    stream.close()  # the reader has gone: the server closes the response
    side.pipeline.gate.set()
    assert side.pipeline.closed.wait(20)  # the pipeline was stopped, and with it the model
    for thread in threading.enumerate():
        if thread.name == "sse":
            thread.join(20)
    return [[200, received.decode("utf-8")], side.ask(Q)]


# The cases of wts-core's docs/adr/0009-briefing-desk.md, "Parity". Each: its name, the limits it runs under (laid
# over the site's [usage] settings), whether there is a model, and what is asked.
ASK_CASES: list[dict[str, Any]] = [
    {"name": "a fresh question, and the same again from the cache", "usage": {},
     "play": lambda s: [s.ask(Q), s.ask("what have councils said about  closing PUBLIC toilets since 2020?")]},
    {"name": "with no hours to keep an answer, every question is written afresh", "usage": {"answer_cache_hours": 0},
     "play": lambda s: [s.ask(Q), s.ask(Q)]},
    {"name": "a follow-up, and the same follow-up again", "usage": {},
     "play": lambda s: [s.ask(Q), s.ask(Q2, history=ASKED_BEFORE), s.ask(Q2, history=ASKED_BEFORE)]},
    {"name": "a question the model could not read", "usage": {}, "play": lambda s: [s.ask(Q, "unread")]},
    {"name": "sources only", "usage": {}, "play": lambda s: [s.ask(Q, sources_only=True)]},
    {"name": "sources only, once the site's budget is spent", "usage": {"daily_spend_cap_usd": 0.0},
     "play": lambda s: [s.ask(Q, sources_only=True)]},
    {"name": "the visitor's limit reached; a cached answer still loads", "usage": {"per_visitor_daily_questions": 1},
     "play": lambda s: [s.ask(Q), s.ask(Q2), s.ask(Q)]},
    {"name": "the daily cap reached", "usage": {"daily_spend_cap_usd": 0.0}, "play": lambda s: [s.ask(Q)]},
    {"name": "the monthly cap reached", "usage": {"monthly_spend_cap_usd": 0.0}, "play": lambda s: [s.ask(Q)]},
    {"name": "too many requests in a minute", "usage": {"requests_per_minute": 1},
     "play": lambda s: [s.ask(Q), s.ask(Q2)]},
    {"name": "one place too many for the visitor", "usage": {"briefings_at_once_per_visitor": 1},
     "play": lambda s: [*_while_one_is_written(s, lambda: [s.ask(Q2)]), s.ask(Q2)]},
    {"name": "one place too many for the site", "usage": {"briefings_at_once_per_visitor": 5, "briefings_at_once": 1},
     "play": lambda s: [*_while_one_is_written(s, lambda: [s.ask(Q2)]), s.ask(Q2)]},
    {"name": "the second check of the caps counts the others in progress", "usage": {"daily_spend_cap_usd": 0.05},
     "play": lambda s: _while_one_is_written(s, lambda: [s.ask(Q2)])},
    {"name": "the pipeline raising mid-stream", "usage": {"briefings_at_once_per_visitor": 1},
     "play": lambda s: [s.ask(Q, "raises"), s.ask(Q)]},
    {"name": "the model declining", "usage": {}, "play": lambda s: [s.ask(Q, "declined"), s.ask(Q)]},
    {"name": "no records", "usage": {}, "play": lambda s: [s.ask(Q, "no_records"), s.ask(Q)]},
    {"name": "no API key", "usage": {}, "has_model": False,
     "play": lambda s: [s.ask(Q), s.ask(Q), s.ask(Q, sources_only=True)]},
    {"name": "the reader leaving while the briefing is written", "usage": {"briefings_at_once_per_visitor": 1},
     "play": _the_reader_leaves},
]


def play_asks(build: Callable[..., Side]) -> list[dict[str, Any]]:
    """Every case through ``/api/ask``. ``build(usage, has_model)`` gives a new site, with an empty state database,
    its clock at START, the day's visitor secret SALT and briefing ids "briefing001", "briefing002"…"""
    out = []
    for case in ASK_CASES:
        side = build(case["usage"], case.get("has_model", True))
        sent = case["play"](side)
        out.append({"name": case["name"], "usage": case["usage"], "has_model": case.get("has_model", True),
                    "sent": sent, "rows": side.rows(), "calls": side.pipeline.calls,
                    "briefings_today": side.briefings_today(visitor_of(ADDRESS))})
    return out


def visitor_of(address: str, salt: str = SALT) -> str:
    """The day's code for a visitor, as every site makes it: the address itself is never kept."""
    return hashlib.sha256(f"{salt}|{address}".encode()).hexdigest()[:24]


# ---- the checks on briefings: sources, blocks and saved answers ---------------------------------------------------

SOURCES: list[dict[str, Any]] = [
    {"n": 1, "title": "Barnsley Metropolitan Borough Council, full council, 26 February 2025: Notice of Motion - "
                      "Weekly Bin Collections",
     "blocks": ["Councillor Kitching moved that weekly bin collections be restored.",
                "Upon being put to the vote the motion was lost.",
                "The Leader said that the positioning of of that company was a matter for the cabinet."],
     "meta": {"heading": "Notice of Motion - Weekly Bin Collections"}},
    {"n": 2, "title": "Guildford Borough Council, full council, 5 March 2025: Waste and Recycling Strategy",
     "blocks": ["Councillor Julia McShane introduced the waste and recycling strategy, including fortnightly bin "
                "collections.", "RESOLVED that the strategy be adopted.",
                "Members welcomed the programme and noted that 62% of residents favoured the change (a) in rural "
                "wards and", "(b) in the town centre."],
     "meta": {"heading": "Waste and Recycling Strategy"}},
    {"n": 3, "title": "Cornwall Council, cabinet, 12 November 2025: Second homes and council tax",
     "blocks": ["The Cabinet agreed to charge a 100% council tax premium on second homes from April 2026.",
                "Cllr. Jones said it was “a fair contribution” from those who could afford it.",
                "The Revd. Canon Smith presented a petition of 1,204 signatures."],
     "meta": {}},
]
S1 = SOURCES[0]["blocks"]
S2 = SOURCES[1]["blocks"]
S3 = SOURCES[2]["blocks"]


def _c(source: int, text: str) -> dict[str, Any]:
    return {"search_result_index": source - 1, "cited_text": text}


def _cited(text: str, *cites: dict[str, Any]) -> dict[str, Any]:
    return {"text": text, "citations": list(cites)}


QUOTE = "The council agreed to restore weekly bin collections from April."
ONE_SOURCE = [{"n": 1, "title": "Full Council", "blocks": [QUOTE], "meta": {}}]
# Each: the sources the model was given (ONE_SOURCE or SOURCES) and the blocks it wrote. The first few are the
# blocks in the site's own tests (tests/test_verify.py, tests/test_pipeline.py); the rest take each rule in turn.
BRIEFINGS: dict[str, dict[str, Any]] = {
    "a lead-in written in pieces (tests/test_verify.py)": {"sources": "one", "blocks": [
        {"text": "- Members differed on how often bins should be collected, as when the Leader, Cllr. "},
        {"text": "Jones said "}, _cited(f'"{QUOTE}"', _c(1, QUOTE)),
        {"text": " The opposition then voted against every budget since 2019. "}]},
    "a long uncited piece breaks the lead-in (tests/test_verify.py)": {"sources": "one", "blocks": [
        {"text": "Cllr. "},
        {"text": "The council has cut every library budget since 2019 and closed six branches. "},
        _cited(f'"{QUOTE}"', _c(1, QUOTE))]},
    "the fake model's briefing (tests/test_pipeline.py)": {"sources": "all", "blocks": [
        {"text": "The minutes record that "}, _cited(S1[0][:60], {**_c(1, S1[0]), "source": "x"}),
        {"text": " The scheme was a fiasco that residents across the borough opposed for many months."}]},
    "nothing written at all": {"sources": "all", "blocks": []},
    "an empty block and one of spaces": {"sources": "all", "blocks": [{"text": ""}, {"text": "  \n"}, {}]},
    "no records": {"sources": "all", "blocks": [
        {"text": "No records found. The minutes hold nothing on this subject for these councils."}]},
    "no records, not at the start": {"sources": "all", "blocks": [
        {"text": "Summary\n\nNo records found. Nothing was said."}]},
    "a citation that is right, one of another source's words, one of no source": {"sources": "all", "blocks": [
        _cited("Barnsley's motion to restore weekly collections was lost.", _c(1, S1[0]), _c(1, S1[1])),
        _cited(" Guildford adopted its strategy.", _c(1, S2[1])),
        _cited(" Cornwall agreed a premium.", _c(9, S3[0])),
        _cited(" It applies from April 2026.", {"document_index": 2, "cited_text": S3[0]}),
        _cited(" Two sources say so.", _c(2, S2[1]), _c(3, S3[0]), _c(2, S2[0]))]},
    "a citation across two passages, joined without the space": {"sources": "all", "blocks": [
        _cited("Residents favoured the change in rural wards and the town centre.",
               _c(2, "62% of residents favoured the change (a) in rural wards and(b) in the town centre."))]},
    "a citation in curly quotes of a source in straight ones, and the other way": {"sources": "all", "blocks": [
        _cited("Jones called it fair.", _c(3, "it was \"a fair contribution\" from those who could afford it")),
        _cited(" Kitching moved the motion.", _c(1, "Councillor  Kitching moved\nthat weekly bin collections"))]},
    "headings, labels, bullets, dates and joins": {"sources": "all", "blocks": [
        {"text": "## Councils controlled by Labour\n\n**Barnsley Metropolitan Borough Council:**\n- "},
        _cited("The motion to restore weekly collections was lost", _c(1, S1[1])),
        {"text": " (26 February 2025).\n- On 5 March 2025, "},
        _cited("Guildford adopted its strategy", _c(2, S2[1])),
        {"text": "; and "}, _cited("it included fortnightly collections", _c(2, S2[0])),
        {"text": ".\n\n### In summary:\n"}, {"text": "on 12 November 2025."}, {"text": " (written answer, 12 October "
                                                                                 "2026)."},
        {"text": "\n1. First, "}, _cited("the premium was agreed", _c(3, S3[0])), {"text": " in 2026."},
        {"text": " That is 100% of the bill."}, {"text": " It cost £2 million."}]},
    "a claim with no citation, long and short": {"sources": "all", "blocks": [
        {"text": "Councils across England have cut waste services since 2019, and residents have objected."},
        {"text": " Costs rose."}, _cited(" Guildford adopted its strategy.", _c(2, S2[1])),
        {"text": " Most councils agree.\nSpending fell by a fifth in real terms over the period.\n"}]},
    "a sentence before a lead-in is a claim; the lead-in is not": {"sources": "all", "blocks": [
        {"text": "Opposition councillors criticised the budget. Cllr Jones said on 4 May that "},
        _cited("\"it was a fair contribution\"", _c(3, S3[1])),
        {"text": " The vote was close. Mr. Smith, the portfolio holder, said "},
        _cited("the motion was lost", _c(1, S1[1])),
        {"text": ". Was the funding cut by 40% in real terms? Cllr Jones said "},
        _cited("it was fair", _c(3, S3[1])),
        {"text": "\n- Spending on the scheme rose by 40% under the last administration\n- Cllr Jones said "},
        _cited("a fair contribution", _c(3, S3[1]))]},
    "this site's honorifics: Cllr, Rev, Revd and Hon end no sentence": {"sources": "all", "blocks": [
        {"text": "The petition was presented by the Revd. "}, {"text": "Canon Smith, who said "},
        _cited("1,204 people had signed", _c(3, S3[2])),
        {"text": ". The Rev. Jones and the Hon. Alderman Brown then spoke, and Cllr. Kitching said "},
        _cited("weekly bin collections be restored", _c(1, S1[0])),
        {"text": ". Dr. Patel, Prof. Green, Mrs. White, Ms. Black, Mr. Grey, St. John and Sr. and Jr. members said "},
        _cited("the strategy be adopted", _c(2, S2[1])),
        {"text": ". The hon. member for the ward said "}, _cited("the motion was lost", _c(1, S1[1])),
        {"text": ". An Ald. Brown said "}, _cited("the motion was lost", _c(1, S1[1]))]},
    "notes about the evidence, by the strict rule": {"sources": "all", "blocks": [
        {"text": "About the evidence: the records retrieved cover two councils.\n"},
        {"text": "No division records were supplied for Guildford.\n"},
        {"text": "The votes on the second reading were not supplied.\n"},
        {"text": "Gas was supplied to two million homes by the council's company.\n"},
        {"text": "No vote data was supplied for this meeting.\n"},
        {"text": "The records were retrieved from three councils.\n"},
        {"text": "Little was said about rural wards.\n"},
        {"text": "Nothing was found for Cornwall before 2020.\n"},
        {"text": "There are gaps in the minutes of 2021.\n"},
        {"text": "A caveat: the minutes are in draft.\n"},
        {"text": "The cost cannot be attributed to any one council.\n"},
        {"text": "Notes: the evidence base is small.\n"},
        {"text": "Jones said the records were incomplete and the evidence is weak.\n"},
        {"text": "She argued that nothing was found by the auditors.\n"},
        {"text": "The Welsh Government decides these matters for Wales.\n"},
        {"text": "In the records, Barnsley's position is the clearest.\n"},
        {"text": "Other results were not relevant and have been excluded.\n"},
        {"text": "The data are not retrieved from the council's own site.\n"}]},
    "openers about the records are dropped": {"sources": "all", "blocks": [
        {"text": "Across the records retrieved, most councils kept weekly collections. Based on the evidence, "},
        _cited("Barnsley's motion was lost", _c(1, S1[1])),
        {"text": ".\n- In the supplied records: two councils changed. According to the sources provided, costs "
                 "rose.\nFrom these results, nothing follows. Within all the retrieved contributions above, one "
                 "stands out."}]},
    "American spellings in the model's own words, never in a quotation": {"sources": "all", "blocks": [
        {"text": "The council's program to organize recycling centers was criticized, and its labor costs "
                 "analyzed. Members said \"the program was organized in the center\" and the World Health "
                 "Organization was cited. Seized bins were prized. "},
        _cited("Members welcomed the programme", _c(2, S2[2])),
        {"text": " “The color of the bins was not favored”, one said; the color was later changed toward gray, "
                 "and 40 percent of neighbors approved."}]},
    "loaded words in the model's own voice, the family's and this site's own": {"sources": "all", "blocks": [
        {"text": "The Leader admitted the scheme was a shambles and a fiasco, and the opposition slammed the "
                 "chaotic, botched and wasteful roll-out as reckless cronyism. Claims for benefits rose. He "
                 "claimed that it worked; savings were claimed for the scheme. A councillor said \"it was a "
                 "disgraceful shambles\" and “a scandal”. The far-right and hard-left groups were called "
                 "extremists, loony, racist and vindictive; the incompetent, shambolic cabinet U-turned. "},
        _cited("The motion was lost", _c(1, S1[1])),
        {"text": " in chaos, he conceded: a spiteful, bigoted flip-flop."}]},
    "quotations found, cut, altered and made up": {"sources": "all", "blocks": [
        _cited("Kitching moved that \"weekly bin collections be restored\".", _c(1, S1[0])),
        _cited(" The Leader spoke of \"the positioning of that company\".", _c(1, S1[2])),
        _cited(" Members noted that \"62% of residents favoured the change ... in the town centre\".", _c(2, S2[2])),
        _cited(" McShane \"introduce[d] the waste and recycling strategy\".", _c(2, S2[0])),
        _cited(" Jones called it \"a fair and reasonable contribution\".", _c(3, S3[1])),
        {"text": " One member spoke of \"a complete and utter waste\" of money. The item was headed “Second "
                 "homes and council tax”, and another “Waste and Recycling Strategy”; a 'fair contribution' "
                 "is a term, and ‘those who could afford it’ a phrase."},
        _cited(" It was \"lost\".", _c(1, S1[1])),
        {"text": " \"The motion was lost\""}, _cited(" was the result.", _c(1, S1[1])),
        {"text": " A quotation that never closes: \"the motion was"}]},
    "a quotation across two blocks, and an apostrophe that is no quotation": {"sources": "all", "blocks": [
        {"text": "The Leader said the company's \"positioning "}, _cited("of that company", _c(1, S1[2])),
        {"text": " was a matter\" for others. It's the council's view that residents' bins weren't collected."}]},
}


class _Dice:
    """A sequence of numbers that is the same on every computer and every version of Python."""

    def __init__(self, seed: int) -> None:
        self._state = seed

    def below(self, n: int) -> int:
        self._state = (self._state * 6364136223846793005 + 1442695040888963407) % (1 << 64)
        return (self._state >> 33) % n

    def pick(self, items: list[Any]) -> Any:
        return items[self.below(len(items))]


_UNCITED = [
    "Councils across England have cut waste services since 2019. ", "Costs rose. ", "## Councils controlled by Labour\n",
    "**Guildford Borough Council:** ", "- ", "\n- ", " (26 February 2025). ", " on 12 November 2025. ", "; and ",
    " and ", ". ", ".\n\n", "The Leader, Cllr. Jones, said ", "Mr. Smith told the meeting that ", "Cllr Kitching said ",
    "The Revd. Canon Smith said ", "The Hon. Alderman Brown said ", "She said ", "In reply, ",
    "No division records were supplied. ", "The votes were not supplied. ", "Gas was supplied to two million homes. ",
    "Little was said about rural wards. ", "About the evidence: two councils are covered.\n",
    "Across the records retrieved, most councils agreed. ", "Based on the evidence, ", "According to the sources, ",
    "The program was organized by the council's labor group. ", "It was a fiasco. ", "The Leader admitted it. ",
    "He claimed that it worked. ", "The roll-out was chaotic and botched. ", "Was it cut by 40% in real terms? ",
    "The scheme was cut by 40%! ", "Spending rose by £2 million in 2024\n", "One member called it \"a complete "
    "waste of money\". ", "Members spoke of “a fair contribution”. ", "It was \"lost\". ", "Notes: ", "In summary:\n",
    "The opposition disagreed", "Three councils. ", "1. ", "The Welsh Government decides these matters for Wales. ",
    "", " ", "\n",
]
_CITED = [
    ("Kitching moved that weekly bin collections be restored", 1, S1[0]),
    ("\"weekly bin collections be restored\"", 1, S1[0]),
    ("the motion was lost", 1, S1[1]), ("\"the motion was lost\"", 1, S1[1]),
    ("\"the positioning of that company\"", 1, S1[2]),
    ("McShane introduced the strategy", 2, S2[0]), ("the strategy was adopted", 2, S2[1]),
    ("\"RESOLVED that the strategy be adopted\"", 2, S2[1]),
    ("62% of residents favored the change", 2, S2[2]),
    ("the Cabinet agreed a 100% premium", 3, S3[0]), ("it was “a fair contribution”", 3, S3[1]),
    ("\"a fair and reasonable contribution\"", 3, S3[1]),
    ("a petition of 1,204 signatures", 3, S3[2]),
    ("the premium was agreed", 3, "The Cabinet agreed to charge a 50% premium"),  # words the source does not have
    ("the motion was lost", 7, S1[1]),                                                # a source that was not given
    ("Guildford adopted it", 1, S2[1]),                                               # another source's words
]


def generated_briefings(n: int = 150, seed: int = 20261113) -> list[list[dict[str, Any]]]:
    """Briefings put together from the pieces above, the same ones every time: the rules meeting one another in
    orders nobody wrote down."""
    dice = _Dice(seed)
    out = []
    for _ in range(n):
        blocks: list[dict[str, Any]] = []
        for _ in range(2 + dice.below(8)):
            if dice.below(5) < 3:
                blocks.append({"text": "".join(dice.pick(_UNCITED) for _ in range(1 + dice.below(3)))})
            else:
                text, source, cited_text = dice.pick(_CITED)
                cites = [_c(source, cited_text)]
                if dice.below(6) == 0:
                    _, another, more = dice.pick(_CITED)
                    cites.append(_c(another, more))
                blocks.append(_cited(text, *cites))
        out.append(blocks)
    return out


def sources_of(which: str, make: Callable[..., Any]) -> list[Any]:
    """The sources a briefing was given, as the site's own ``Source`` objects (``make`` is that class)."""
    return [make(n=s["n"], kind="minutes", title=s["title"], url=f"https://example/{s['n']}", blocks=list(s["blocks"]),
                 meta=dict(s["meta"])) for s in (ONE_SOURCE if which == "one" else SOURCES)]


def as_older_checks_left_it(answer: dict[str, Any]) -> dict[str, Any]:
    """A checked briefing as checks older than today's might have saved it: every passage with no citation marked
    as a point to check, and a judgemental-word mark on the first seven letters of each. Shown again, today's
    checks clear what they would not mark; nothing else may change."""
    segments = []
    for s in answer["segments"]:
        s = dict(s)
        if s["status"] == "connective":
            s["status"] = "unsupported"
        if s["status"] != "cited" and len(s["text"]) >= 7:
            s["loaded"] = [*s.get("loaded", []), {"start": 0, "end": 7, "word": s["text"][:7]}]
        segments.append(s)
    return {**answer, "segments": segments,
            "unsupported_segments": sum(1 for s in segments if s["status"] == "unsupported"),
            "loaded_words": sum(len(s.get("loaded") or []) for s in segments)}


# saved answers in the site's own tests (tests/test_api.py, tests/test_verify.py), judged again when shown
SAVED_ANSWERS: dict[str, dict[str, Any] | None] = {
    "none": None,
    "no segments": {"markdown": "", "segments": []},
    "tests/test_api.py: marks made by older checks": {
        "markdown": "", "unsupported_segments": 2, "loaded_words": 2, "grounded_ratio": 0.5, "segments": [
            {"text": "March 2025", "sources": [], "status": "unsupported", "loaded": []},
            {"text": "The minutes record that the motion was lost.", "sources": [1], "status": "cited",
             "loaded": [{"start": 4, "end": 11, "word": "minutes"}]},
            {"text": " It was a fiasco that residents across the borough opposed for many months.", "sources": [],
             "status": "unsupported", "loaded": [{"start": 10, "end": 16, "word": "fiasco"}]}]},
    "tests/test_verify.py: a short claim stays": {
        "segments": [{"text": "Opposition councillors criticised the budget.", "status": "unsupported"},
                     {"text": " Cllr Jones said on 4 May that ", "status": "connective"},
                     {"text": "\"it has failed\"", "status": "cited"}],
        "unsupported_segments": 1, "grounded_ratio": 0.3},
    "tests/test_verify.py: a lead-in in pieces is cleared": {
        "segments": [{"text": "- Members differed sharply on the timetable, as when Cllr. ", "status": "unsupported"},
                     {"text": "Jones said ", "status": "connective"},
                     {"text": "\"it will be delivered\"", "status": "cited"}],
        "unsupported_segments": 1, "grounded_ratio": 0.5},
    "tests/test_verify.py: a claim above a lead-in stays (a line that ended)": {
        "segments": [{"text": "- Spending on the scheme rose by 40% under the last administration\n",
                      "status": "unsupported"}, {"text": "- Cllr Jones said ", "status": "connective"},
                     {"text": "\"it has failed\"", "status": "cited"}],
        "unsupported_segments": 1, "grounded_ratio": 0.3},
    "tests/test_verify.py: a claim above a lead-in stays (a question)": {
        "segments": [{"text": "Was the funding cut by 40% in real terms?", "status": "unsupported"},
                     {"text": " Cllr Jones said ", "status": "connective"},
                     {"text": "\"it has failed\"", "status": "cited"}],
        "unsupported_segments": 1, "grounded_ratio": 0.3},
    "the scripted pipeline's briefing": an_answer(),
    "an invalid citation is counted, and never cleared": {
        "segments": [{"text": "The premium was agreed.", "status": "invalid", "sources": []},
                     {"text": " (12 November 2025).", "status": "unsupported"},
                     {"text": " Notes: the records retrieved are few.", "status": "unsupported"},
                     {"text": " The votes were not supplied.", "status": "unsupported"},
                     {"text": " The Revd. Canon Smith said ", "status": "unsupported"},
                     {"text": "\"a petition\"", "status": "cited", "sources": [3]}],
        "unsupported_segments": 4, "grounded_ratio": 0.1, "loaded_words": 0},
}
BRITISH_TEXTS = [
    "Bin collections, in every council.", "The organization of recycling centers, and how councils analyze costs.",
    "Labor-run councils' programs for neighborhoods since 2020.", "", "color",
    "What the World Health Organization said; \"the color of money\" and the Center Parcs proposal.",
    "A program to catalog gray areas: 40 percent traveled toward the theater.",
]

# ---- reports and statements: what is sent ---------------------------------------------------------------------------
# Each step is a request. The clock moves on 61 seconds before each, so the limit of twenty a minute never bites.

WORDS = ("I voted against this motion because the council had already agreed a review of collections, and the "
         "minutes of that meeting set it out.")
FORM = {"page": f"https://wherecouncilsstand.com/votes/{VOTE}", "name": "Steve Houghton",
        "role": "Councillor, Barnsley Metropolitan Borough Council", "text": WORDS,
        "link": "https://barnsley.moderngov.co.uk/ieListDocuments.aspx?MId=1", "email": "cllr@barnsley.gov.uk",
        "acting": True}


def _statement(case: str, **fields: Any) -> dict[str, Any]:
    return {"case": case, "post": "/api/statements", "json": {**FORM, **fields}}


def _without(case: str, field: str) -> dict[str, Any]:
    return {"case": case, "post": "/api/statements", "json": {k: v for k, v in FORM.items() if k != field}}


def _report(case: str, **fields: Any) -> dict[str, Any]:
    return {"case": case, "post": "/api/report", "json": fields}


API_STEPS: list[dict[str, Any]] = [
    _statement("a statement beside a named vote, its page a full address"),
    _statement("beside a council's page, the address without https and the code in small letters",
               page=f"wherecouncilsstand.com/councils/{BARNSLEY.lower()}/"),
    _statement("beside a briefing, a path alone", page="/b/abc123", link=""),
    _statement("the www address, with a query and a fragment",
               page=f"https://www.wherecouncilsstand.com/votes/{VOTE.lower()}?x=1#y"),
    _statement("an address on the host the request came to", page=f"http://testserver/councils/{BARNSLEY}"),
    _statement("line endings and blank lines as they were typed", link="",
               text="Line one <b>bold</b>\r\nline two\r\n\r\n\r\n\r\npara two & more  "),
    _statement("spaces around and inside the name and role", name="  Steve   Houghton ",
               role=" Leader of\tthe  council "),
    _statement("exactly 150 words, and no link", text=" ".join(["word"] * 150), link=""),
    _statement("one word", text="No."),
    _statement("just within every limit", name="N" * 200, role="R" * 200, link="https://example.org/" + "a" * 480,
               email="a" * 288 + "@example.org", text=" ".join(["a" * 20] + ["b" * 13] * 105)),
    _statement("151 words", text=" ".join(["word"] * 151)),
    _statement("no words, only spaces", text="   "),
    _statement("within 150 words but more than 1,500 characters", text=" ".join(["extraordinarily"] * 100)),
    _statement("one long word of 1,550 characters", text="x" * 1550),
    _statement("more than the form can take", text="word " * 400),
    _statement("not an email address", email="not an address"),
    _statement("no email address", email=""),
    _statement("an email address too long", email="a" * 289 + "@example.org"),
    _statement("the box not ticked", acting=False),
    _statement("a page on another site", page="https://example.org/votes/x"),
    _statement("a page a statement cannot sit beside", page="/about"),
    _statement("no page", page=""),
    _statement("an ftp address", page="ftp://wherecouncilsstand.com/votes/x"),
    _statement("a vote that is not on the site", page=f"/votes/{BARNSLEY}:9:9:9"),
    _statement("a council that is not on the site", page="/councils/E99999999"),
    _statement("a briefing that is not on the site", page="/b/nosuchbriefing"),
    _statement("a briefing that has been withdrawn", page="/b/gone456"),
    _statement("a link that is no web address", link="javascript:alert(1)"),
    _statement("a link with a quotation mark", link="https://example.org/a\"onmouseover=\"alert(1)"),
    _statement("a link with angle brackets", link="https://example.org/<script>"),
    _statement("a link with an apostrophe", link="https://example.org/it's"),
    _statement("a link with a space", link="https://example.org/a b"),
    _statement("a link with no host", link="https:///minutes"),
    _statement("a link too long", link="https://example.org/" + "a" * 481),
    _statement("a name of spaces", name="    "),
    _statement("a name of one letter", name=" \n\tX "),
    _statement("a name too long", name="N" * 201),
    _statement("a role of spaces that do not break", role="   "),
    _statement("a role too long", role="R" * 201),
    _without("no name sent", "name"), _without("no role sent", "role"), _without("no page sent", "page"),
    _without("no words sent", "text"), _without("no email address sent", "email"),
    _statement("two faults: no words and a page that is not an item's", text="  ", page="/about"),
    _statement("two faults: a name of spaces and no words", name="  ", text="  "),
    _statement("two faults: a role of spaces and 151 words", role="  ", text=" ".join(["word"] * 151)),
    _statement("two faults: a bad link and a bad email address", link="nope", email="nope"),
    _statement("two faults: a bad email address and a vote that is not on the site", email="nope",
               page=f"/votes/{BARNSLEY}:9:9:9"),
    _statement("two faults: the box not ticked and no words", acting=False, text="  "),
    {"case": "a statement cut short", "post": "/api/statements", "content": "{not json"},
    _report("a report with its kind, page and contact", kind="error", page=f"/votes/{VOTE}",
            message="The vote is shown on the wrong side.", contact="reader@example.org"),
    _report("a request to take a name down", kind="takedown", page="/councils/E08000038",
            message="Please remove my name."),
    _report("characterised unfairly", kind="unfair", message="A loaded word in a briefing.", contact="  c@d.org  "),
    _report("another kind", kind="other", message="Something else entirely"),
    _report("a report with no kind is an error report", message="Wrong party", page=""),
    _report("a kind that is none of them", kind="dispute", message="Something to say"),
    _report("a message too short", kind="error", message="Hey"),
    _report("a message of spaces", kind="error", message="       "),
    _report("a message at its longest", kind="error", message="m" * 5000),
    _report("a message too long", kind="error", message="m" * 5001),
    _report("a page too long", kind="error", message="A long address", page="p" * 501),
    _report("a contact at its longest", kind="error", message="A long contact", contact="c" * 300),
    _report("a contact too long", kind="error", message="A long contact", contact="c" * 301),
    _report("no message"),
    {"case": "a report cut short", "post": "/api/report", "content": "{not json"},
    {"case": "nothing is shown until it is published: beside the vote", "get": f"/api/statements?page=/votes/{VOTE}"},
    {"case": "nothing is shown until it is published: on the council's page",
     "get": f"/api/statements?council={BARNSLEY}"},
]

# ---- what the owner types ---------------------------------------------------------------------------------------
# Sent first, one each minute: five statements and four reports. Then the owner's command lines, under the names the
# site had before wts-core (`publish-statement 1`), one each minute. "<tmp>" is the scenario's own folder.

CHECKED = "Reply from the address on the council's website, 12 November."
OWNER_SENT: list[dict[str, Any]] = [
    _statement("1: beside the vote"),
    _statement("2: beside a briefing", page="/b/abc123", name="Barnsley Council", role="Democratic services",
               text="Our view.", link="", email="dem@barnsley.gov.uk"),
    _statement("3: beside the council's page, to be declined", page=f"/councils/{BARNSLEY}", name="X Y", role="Z W",
               text="Vote for me.", link="", email="x@y.org"),
    _statement("4: beside Guildford's page, to be withdrawn while waiting", page=f"/councils/{GUILDFORD}",
               name="Julia McShane", role="Leader, Guildford Borough Council", text="First para.\n\nSecond.",
               email="leader@guildford.gov.uk"),
    _statement("5: beside the vote, left waiting", name="Hannah Kitching", role="Councillor", link="",
               text="I moved this motion.", email="hk@barnsley.gov.uk"),
    _report("1", kind="error", page=f"/votes/{VOTE}", message="The vote is shown on the wrong side.",
            contact="reader@example.org"),
    _report("2", kind="takedown", page="/councils/E08000038", message="Please remove my name."),
    _report("3", kind="unfair", message="A loaded word in a briefing."),
    _report("4", message="Wrong party", contact="me@example.org"),
]
OWNER_FILES = {"new.txt": "Our newer view, as the council sent it.\n", "long.txt": " ".join(["word"] * 151)}
OWNER_COMMANDS: list[list[str]] = [
    ["list-statements"],
    ["list-reports"],
    ["publish-statement", "1"],
    ["publish-statement", "1", "--checked", "   "],
    ["publish-statement", "1", "--checked", CHECKED],
    ["publish-statement", "1", "--checked", CHECKED],
    ["publish-statement", "9", "--checked", CHECKED],
    ["publish-statement", "2", "--checked", CHECKED, "--council", "barnsley"],
    ["publish-statement", "5", "--checked", CHECKED, "--council", "no such council anywhere"],
    ["update-statement", "1", "--text", " ".join(["word"] * 151)],
    ["update-statement", "1", "--text", "New words.", "--role", "Leader"],
    ["update-statement", "1", "--name", "   "],
    ["update-statement", "1", "--role", "   "],
    ["update-statement", "1", "--name", "N" * 201],
    ["update-statement", "1", "--link", "javascript:alert(1)"],
    ["update-statement", "1", "--link", ""],
    ["update-statement", "1"],
    ["update-statement", "2", "--text-file", "<tmp>/new.txt"],
    ["update-statement", "2", "--text-file", "<tmp>/long.txt"],
    ["update-statement", "5", "--name", "Cllr  Hannah\nKitching"],
    ["update-statement", "9", "--role", "Mayor"],
    ["decline-statement", "3"],
    ["decline-statement", "3", "--reason", "It appeals for votes."],
    ["decline-statement", "3", "--reason", "again"],
    ["decline-statement", "1", "--reason", "it is published"],
    ["decline-statement", "999", "--reason", "x"],
    ["withdraw-statement", "4"],
    ["withdraw-statement", "4"],
    ["withdraw-statement", "1", "--reason", "It names an officer."],
    ["withdraw-statement", "9"],
    ["update-statement", "1", "--role", "Mayor"],
    ["list-statements"],
    ["list-statements", "--all"],
    ["close-report", "1"],
    ["close-report", "1"],
    ["close-report", "999"],
    ["list-reports"],
    ["list-reports", "--all"],
    ["withdraw", "abc123", "--reason", "It named the wrong council."],
    ["withdraw", "nope", "--reason", "x"],
    ["withdraw", "abc123"],
]
OWNER_READS: list[str] = [
    f"/api/statements?page=/votes/{VOTE}", f"/api/statements?council={BARNSLEY}", "/api/statements?page=/b/abc123",
    f"/api/statements?council={GUILDFORD}", "/api/briefings/abc123", f"/councils/{BARNSLEY}", f"/votes/{VOTE}",
]


def send(client: Any, step: dict[str, Any]) -> dict[str, Any]:
    """One request, and its answer as it is stored: the status and the body. The list FastAPI answers a body of
    the wrong shape with is kept as the place and kind of each fault, which do not change with the library's
    version, and not its sentences, which do."""
    if "get" in step:
        r = client.get(step["get"])
    elif "json" in step:
        r = client.post(step["post"], json=step["json"])
    else:
        r = client.post(step["post"], content=step["content"].encode(), headers={"content-type": "application/json"})
    is_json = r.headers.get("content-type", "").startswith("application/json")
    body = r.json() if is_json else None
    if is_json and r.status_code == 422 and isinstance(body.get("detail"), list):
        body = {"detail": [[list(fault["loc"]), fault["type"]] for fault in body["detail"]]}
    return {"case": step.get("case", step.get("get")), "status": r.status_code, "json": body,
            "text": None if is_json else r.text, "type": r.headers.get("content-type")}


def events_of(text: str) -> list[dict[str, Any]]:
    """The events in the text of a streamed answer."""
    return [json.loads(line[6:]) for chunk in text.split("\n\n") for line in chunk.splitlines()
            if line.startswith("data: ")]


def page_read(client: Any, path: str) -> dict[str, Any]:
    """One page or endpoint read, as it is stored. Three of them are mostly the reference data's (every council in
    the country): of those, what is kept is the part that comes from the made-up record."""
    answer = send(client, {"get": path})
    if path == "/api/councils":
        body = answer["json"]
        answer["json"] = {"totals": body["totals"], "rows": len(body["councils"]),
                          "loaded": [r for r in body["councils"] if r["gss"] in (BARNSLEY, GUILDFORD)]}
    elif path in ("/sitemap.xml", "/councils"):
        text = answer["text"]
        found = re.findall(rf"/(?:votes|councils)/(?:{BARNSLEY}|{GUILDFORD})[^<\"]*", text)
        answer["text"] = {"of_the_record": sorted(set(found)), "length_over_10000": len(text) > 10000}
    return answer


def command_run(result: Any, tmp: Path) -> dict[str, Any]:
    """What a command printed, where, and how it ended. A command Typer itself turns away (a missing option) is
    kept as its exit status alone: the page it prints is drawn differently from one terminal to another."""
    error = None
    if result.exception is not None and not isinstance(result.exception, SystemExit):
        error = f"{type(result.exception).__name__}: {result.exception}"
    if result.exit_code == 2:
        return {"exit_code": 2}
    return json.loads(json.dumps({"exit_code": result.exit_code, "stdout": result.stdout, "stderr": result.stderr,
                                  "error": error}).replace(json.dumps(str(tmp))[1:-1], "<tmp>"))


# ---- backups -----------------------------------------------------------------------------------------------------


def database(path: Path, damaged: bool = False) -> Path:
    """A state database with fifty reports in it and the site's own tables. ``damaged``: one whose pages SQLite's
    integrity check finds fault with (an index dropped from the list of tables, so its pages belong to nothing),
    though it still opens and copies."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("create table reports (id integer primary key, message text)")
    con.executemany("insert into reports (message) values (?)", [("a mistake " * 20,)] * 50)
    con.execute("create table usage (cost_usd real)")
    con.execute("create table briefings (id text primary key)")
    if damaged:
        con.execute("create index by_message on reports (message)")
        con.commit()
        con.execute("pragma writable_schema = on")
        con.execute("delete from sqlite_master where name = 'by_message'")
    con.commit()
    con.close()
    return path


def inside(archive: Path) -> dict[str, Any]:
    """What a backup holds: its tables and how many rows each has, the hash of the database inside it, its mode."""
    raw = gzip.decompress(archive.read_bytes())
    with tempfile.TemporaryDirectory() as tmp:
        (Path(tmp) / "db").write_bytes(raw)
        con = sqlite3.connect(Path(tmp) / "db")
        tables = {name: con.execute(f"select count(*) from {name}").fetchone()[0]  # noqa: S608
                  for (name,) in con.execute("select name from sqlite_master where type = 'table' order by name")}
        con.close()
    return {"sha256": hashlib.sha256(raw).hexdigest(), "rows": tables,
            "mode": oct(stat.S_IMODE(archive.stat().st_mode))}


def names(folder: Path) -> list[str]:
    return sorted(p.name for p in folder.iterdir()) if folder.exists() else []


B2_ENV = {"COUNCILS_B2_BUCKET": "wts-backups", "COUNCILS_B2_KEY_ID": "kid", "COUNCILS_B2_APPLICATION_KEY": "secret"}
BACKUPS_MADE = [("2026-11-01", 2), ("2026-11-02", 2), ("2026-11-02", 2), ("2026-11-03", 0), ("2026-11-04", -1),
                ("2026-11-05", 7)]


def backups_scenario(tmp: Path, *, make_backup: Callable[[Path, Path, int, str], Path | None],
                     run: Callable[[list[str]], dict[str, Any]], environment: Callable[..., None],
                     clock: Clock) -> dict[str, Any]:
    """Backups made one after another with different numbers kept, then the commands. ``make_backup(db, to, keep,
    day)`` makes the one named for ``day``; ``run(args)`` runs the site's command line and gives what it printed;
    ``environment(data_dir, **more)`` sets COUNCILS_DATA_DIR and nothing else of ours; ``clock`` is the clock the
    site's code reads."""
    import os

    def command(case: str, args: list[str], left: Path | None = None) -> dict[str, Any]:
        return {"case": case, "args": [a.replace(str(tmp), "<tmp>") for a in args], **run(args),
                **({"left": names(left)} if left else {})}

    environment(tmp / "data")
    out: dict[str, Any] = {"sqlite": sqlite3.sqlite_version, "made": [], "commands": []}
    db, dest = database(tmp / "data" / "state.db"), tmp / "backups"
    for day, keep in BACKUPS_MADE:
        made = make_backup(db, dest, keep, day)
        assert made is not None
        out["made"].append({"day": day, "keep": keep, "name": made.name, "folder": names(dest),
                            "inside": inside(made)})
    out["new_site"] = make_backup(tmp / "nowhere" / "state.db", tmp / "nowhere-backups", 7, "2026-11-06")
    clock.set("2026-11-13T04:10:00+00:00")
    out["commands"].append(command("the newest two kept", ["backup", "--to", str(dest), "--keep", "2"], dest))
    out["commands"].append(command("fourteen kept unless told", ["backup", "--to", str(tmp / "backups-b")],
                                   tmp / "backups-b"))
    out["commands"].append(command("the folder must be given", ["backup"]))
    try:
        make_backup(database(tmp / "bad" / "data" / "state.db", damaged=True), tmp / "bad-backups", 7, "2026-11-06")
    except RuntimeError as exc:
        out["damaged"] = {"error": str(exc), "folder": names(tmp / "bad-backups")}
    environment(tmp / "bad" / "data")
    out["commands"].append(command("a copy that fails its check", ["backup", "--to", str(tmp / "bad-backups")],
                                   tmp / "bad-backups"))
    environment(tmp / "new" / "data")
    out["commands"].append(command("a new site", ["backup", "--to", str(tmp / "new-backups")], tmp / "new-backups"))
    out["commands"].append(command("off-site copies not set up", ["offsite"]))

    # the daily check of the backups: each state of the folder in turn
    environment(tmp / "data")
    folder = tmp / "checked"
    out["commands"].append(command("check: no such folder", ["backup-check", "--in", str(folder)]))
    folder.mkdir()
    out["commands"].append(command("check: no backups yet, and none off site", ["backup-check", "--in", str(folder)]))
    newest = folder / "councils-state-2026-11-12.sqlite.gz"
    (folder / "councils-state-2026-11-11.sqlite.gz").write_bytes(b"older")
    newest.write_bytes(b"newest")
    (folder / "wcs-state-2026-11-13.sqlite.gz").write_bytes(b"another site's")

    def aged(hours: float) -> None:
        at = clock.now().timestamp() - hours * 3600
        os.utime(newest, (at, at))

    aged(49.9)
    out["commands"].append(command("check: a backup just under fifty hours old", ["backup-check", "--in", str(folder)]))
    aged(50.1)
    out["commands"].append(command("check: a backup over fifty hours old", ["backup-check", "--in", str(folder)]))
    environment(tmp / "data", **B2_ENV)
    out["commands"].append(command("check: stale, and no off-site copy made yet", ["backup-check", "--in", str(folder)]))
    aged(1)
    out["commands"].append(command("check: no off-site copy made yet", ["backup-check", "--in", str(folder)]))
    record = folder / "offsite.json"
    for case, status in (
            ("the last off-site copy failed", {"ok": False, "when": "2026-11-13T04:05:00+00:00", "error": "503 busy"}),
            ("a failed copy with no time", {"ok": False, "when": None, "error": "503"}),
            ("a failed copy with a number for its time", {"ok": False, "when": 1731400000, "error": "503"}),
            ("a failed copy with nothing else said", {"ok": False}),
            ("the last off-site copy just under fifty hours old", {"ok": True, "when": "2026-11-11T02:20:00+00:00"}),
            ("the last off-site copy over fifty hours old", {"ok": True, "when": "2026-11-11T02:00:00+00:00"}),
            ("all up to date", {"ok": True, "when": "2026-11-13T04:05:00+00:00", "file": newest.name})):
        record.write_text(json.dumps(status))
        out["commands"].append(command(f"check: {case}", ["backup-check", "--in", str(folder)]))
    record.write_text("{not json")
    out["commands"].append(command("check: a record that cannot be read", ["backup-check", "--in", str(folder)]))
    return out


class FakeB2:
    def __init__(self, bucket: str = "wts-backups", fail_uploads: int = 0, can_delete: bool = True) -> None:
        self.bucket, self.fail_uploads, self.can_delete = bucket, fail_uploads, can_delete
        self.files: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("b2_authorize_account"):
            if request.headers.get("authorization") != httpx.BasicAuth("kid", "secret")._auth_header:
                return httpx.Response(401)
            return httpx.Response(200, json={"accountId": "acc", "apiUrl": "https://api.b2.test",
                                             "authorizationToken": "tok",
                                             "allowed": {"bucketId": "b1", "bucketName": self.bucket}})
        assert request.headers.get("authorization") in ("tok", "up"), "every call carries a token"
        body = json.loads(request.content or b"{}") if path.startswith("/b2api") else {}
        if path.endswith("b2_get_upload_url"):
            return httpx.Response(200, json={"uploadUrl": "https://up.b2.test/upload", "authorizationToken": "up"})
        if path == "/upload":
            if self.fail_uploads:
                self.fail_uploads -= 1
                return httpx.Response(503)
            assert request.headers["x-bz-content-sha1"] == hashlib.sha1(request.content).hexdigest()  # noqa: S324
            self.files[request.headers["x-bz-file-name"]] = request.content
            return httpx.Response(200, json={"fileName": request.headers["x-bz-file-name"]})
        if path.endswith("b2_list_file_names"):
            return httpx.Response(200, json={"files": [{"fileName": n, "fileId": f"id-{n}"} for n in sorted(self.files)
                                                       if n.startswith(body["prefix"])]})
        if path.endswith("b2_delete_file_version"):
            if not self.can_delete:
                return httpx.Response(401, json={"code": "unauthorized"})
            del self.files[body["fileName"]]
            return httpx.Response(200, json={})
        return httpx.Response(404)


def b2_client(b2: FakeB2) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(b2))


# Each case: the simulated bucket, the key, the archives sent in turn and how many are kept
OFFSITE_CASES: list[dict[str, Any]] = [
    {"name": "three nights, one upload retried, the newest two kept", "b2": {"fail_uploads": 1}, "keep": 2,
     "days": ["2026-10-10", "2026-10-11", "2026-10-12"]},
    {"name": "a key without delete rights still stores", "b2": {"can_delete": False}, "keep": 1,
     "days": ["2026-10-11", "2026-10-12"]},
    {"name": "a key Backblaze does not accept", "b2": {}, "keep": 60, "days": ["2026-10-12"],
     "env": {"COUNCILS_B2_APPLICATION_KEY": "wrong"}},
    {"name": "a key for another bucket", "b2": {"bucket": "someone-else"}, "keep": 60, "days": ["2026-10-12"]},
    {"name": "another site's backups in the same bucket are left alone", "b2": {}, "keep": 1,
     "days": ["2026-10-11", "2026-10-12"], "already": ["where-they-stand-2026-10-01.tar.gz"]},
    {"name": "three uploads refused in a row", "b2": {"fail_uploads": 3}, "keep": 60, "days": ["2026-10-12"]},
]


def offsite_scenario(tmp: Path, *, send: Callable[..., dict[str, Any]], check: Callable[..., dict[str, Any]],
                     error: type[Exception]) -> list[dict[str, Any]]:
    """Each case's archives sent in turn to a simulated bucket. ``send(archive, keep=, env=, client=)`` sends one
    and gives the record of it; ``check(env=, client=)`` is what `councils offsite` prints; both raise ``error``."""
    out: list[dict[str, Any]] = [{
        "name": "not set up", "sent": send(tmp / "councils-state-x.sqlite.gz", keep=60, env={}, client=None),
        "check": check(env={}, client=None)}]
    for n, case in enumerate(OFFSITE_CASES):
        folder = tmp / f"offsite-{n}"
        folder.mkdir()
        b2 = FakeB2(**case["b2"])
        b2.files.update(dict.fromkeys(case.get("already", []), b"another site's"))
        env = {**B2_ENV, **case.get("env", {})}
        sent = []
        for day in case["days"]:
            archive = folder / f"councils-state-{day}.sqlite.gz"
            archive.write_bytes(f"backup {day}".encode())
            try:
                status = send(archive, keep=case["keep"], env=env, client=b2_client(b2))
            except error as exc:
                status = {"raised": str(exc)}
            sent.append({k: v for k, v in status.items() if k != "when"})
        recorded = json.loads((folder / "offsite.json").read_text())
        try:
            answer = check(env=env, client=b2_client(b2))
        except error as exc:
            answer = {"raised": str(exc)}
        out.append({**case, "sent": sent, "recorded": {k: v for k, v in recorded.items() if k != "when"},
                    "recorded_when": recorded.get("when"), "in_the_bucket": sorted(b2.files), "check": answer})
    return out


def one_line(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()
