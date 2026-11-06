"""The briefing test set (``eval/questions.toml``, roadmap X8) and how the site is scored against it (adapted from
Where Countries Stand's).

    councils evaluate                     # the built-in rules read each question (free)
    councils evaluate --with-model        # the model reads each question (a fraction of a penny each)

Two scores per question, both without writing a briefing:

1. **Reading the question:** each filter chosen (councils, nations, kinds of council and meeting, the party in
   control, councillors' parties, dates, whether votes are wanted) compared with the filters a careful reader would
   choose. Dates are compared by year.
2. **The evidence:** for questions where "No records found" is right, whether nothing was found; for questions that
   name councils in ``include``, whether a source from each was found.

Results are printed and saved under ``eval/runs/`` (docs/EVALUATION.md).
"""

from __future__ import annotations

import json
import tomllib
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from councils.config import REPO_ROOT, Settings
from councils.rag.pipeline import AskRequest, Pipeline
from councils.rag.query_parse import QueryPlan, parse_offline

QUESTIONS = REPO_ROOT / "eval" / "questions.toml"
LISTS = ("councils", "nations", "council_types", "kinds", "control", "parties")
FIELDS = (*LISTS, "date_from", "date_to", "wants_votes")


@dataclass
class Result:
    id: str
    category: str
    question: str
    fields: dict[str, bool]
    got: dict[str, Any]
    records: int
    evidence_ok: bool | None
    problems: list[str] = field(default_factory=list)

    @property
    def plan_ok(self) -> bool:
        return all(self.fields.values())


def load_questions(path: Path = QUESTIONS) -> tuple[date, list[dict[str, Any]]]:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    return date.fromisoformat(data["today"]), data["q"]


def _year(value: str | None) -> int | None:
    return int(str(value)[:4]) if value else None


def compare(plan: QueryPlan, expect: dict[str, Any], today: date, default_years: int,
            start: date) -> tuple[dict[str, bool], dict[str, Any]]:
    """Each filter right or wrong, and what was chosen."""
    f = plan.filters.as_dict()
    got: dict[str, Any] = {k: sorted(f.get(k) or []) for k in LISTS}
    got |= {"date_from": _year(f.get("date_from")), "date_to": _year(f.get("date_to")),
            "wants_votes": bool(plan.wants_votes)}
    want_from = expect.get("date_from")
    want: dict[str, Any] = {k: sorted(expect.get(k, [])) for k in LISTS}
    want |= {"date_from": max(today.year - default_years, start.year) if want_from == "default" else _year(want_from),
             "date_to": _year(expect.get("date_to")), "wants_votes": bool(expect.get("wants_votes", False))}
    ok = {k: got[k] == want[k] for k in FIELDS}
    for k in FIELDS:  # `<field>_any`: acceptable alternatives
        if f"{k}_any" in expect:
            ok[k] = any(got[k] == (sorted(v) if isinstance(v, list) else v) for v in expect[f"{k}_any"])
    return ok, got


def run(settings: Settings, with_model: bool = False, ids: set[str] | None = None,
        pipeline: Pipeline | None = None, path: Path = QUESTIONS) -> list[Result]:
    today, questions = load_questions(path)
    p = pipeline or Pipeline(settings, today=today)
    default_years = int(settings.archive.get("default_years", 4))
    out: list[Result] = []
    for q in questions:
        if ids and q["id"] not in ids:
            continue
        req = AskRequest(question=q["question"])
        if with_model and p.has_model():
            plan, _ = p.make_plan(req)
        else:
            plan = parse_offline(q["question"], today, default_years, settings.start_date)
        fields, got = compare(plan, q.get("expect", {}), today, default_years, settings.start_date)
        result, _ = p.find(plan, req)
        problems = [f"{k}: chose {got[k]!r}" for k, ok in fields.items() if not ok]
        evidence_ok: bool | None = None
        if q.get("no_records"):
            evidence_ok = not result.records
            if not evidence_ok:
                problems.append(f"expected no records, found {len(result.records)}")
        elif q.get("include"):
            found = {r.get("gss") for r in result.records}
            missing = [c for c in q["include"] if c not in found]
            evidence_ok = not missing
            if missing:
                problems.append("no source from " + ", ".join(missing))
        out.append(Result(q["id"], q.get("category", ""), q["question"], fields, got, len(result.records),
                          evidence_ok, problems))
    return out


def summary(results: list[Result]) -> dict[str, Any]:
    by_cat: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by_cat[r.category].append(r)
    checked = [r for r in results if r.evidence_ok is not None]
    return {
        "questions": len(results),
        "plans_right": sum(r.plan_ok for r in results),
        "fields_right": sum(sum(r.fields.values()) for r in results),
        "fields": len(results) * len(FIELDS),
        "evidence_checked": len(checked),
        "evidence_right": sum(bool(r.evidence_ok) for r in checked),
        "by_category": {c: {"questions": len(rs), "plans_right": sum(r.plan_ok for r in rs)}
                        for c, rs in by_cat.items()},
    }


def save(results: list[Result], with_model: bool, folder: Path = REPO_ROOT / "eval" / "runs") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}{'-model' if with_model else ''}.json"
    path.write_text(json.dumps({"summary": summary(results), "results": [asdict(r) for r in results]}, indent=1,
                               default=str), encoding="utf-8")
    return path
