"""Composite soft ranking: relevance x recency (adapted from Where Countries Stand).

Nothing here excludes a record. Recency only re-weights relevance, so a much stronger textual match from 2019 still
outranks a weak 2026 one. Hard exclusions happen only through filters. Minutes have no speaker roles to weight, so
there is no authority factor.

relevance  = w * bm25 / max(bm25) + (1 - w) * calibrated(cosine)
             calibrated(c) = clamp((c - floor) / (ceiling - floor), 0, 1), using the embedding model's similarity range
recency    = floor + (1 - floor) * 0.5 ** (age_years / half_life)
             slider s in [0, 1]: s = 0 -> recency = 1 for every record; otherwise half_life = min_half_life_years / s
score      = relevance * recency
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any


@dataclass
class RankParams:
    recency: float = 0.4
    bm25_weight: float = 0.5
    recency_floor: float = 0.35
    min_half_life_years: float = 3.0
    semantic_floor: float = 0.5
    semantic_ceiling: float = 0.85
    today: date = field(default_factory=date.today)

    @classmethod
    def from_settings(cls, ranking: dict[str, Any], **overrides: Any) -> RankParams:
        keys = {f for f in cls.__dataclass_fields__ if f != "today"}
        values = {k: ranking[k] for k in keys if k in ranking}
        if "default_recency" in ranking:
            values["recency"] = ranking["default_recency"]
        values.update({k: v for k, v in overrides.items() if v is not None})
        p = cls(**values)
        p.recency = min(max(float(p.recency), 0.0), 1.0)
        return p


@dataclass
class Candidate:
    record_id: str
    date: date
    bm25: float | None = None
    cosine: float | None = None
    best_passage_id: str | None = None
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Scored:
    candidate: Candidate
    relevance: float
    recency: float
    score: float

    def breakdown(self) -> dict[str, Any]:
        return {
            "score": round(self.score, 4),
            "relevance": round(self.relevance, 4),
            "keyword": None if self.candidate.bm25 is None else round(self.candidate.bm25, 4),
            "semantic": None if self.candidate.cosine is None else round(self.candidate.cosine, 4),
            "recency": round(self.recency, 4),
        }


def recency_factor(d: date, p: RankParams) -> float:
    if p.recency <= 0:
        return 1.0
    half_life = p.min_half_life_years / p.recency
    age_years = max((p.today - d).days, 0) / 365.25
    return p.recency_floor + (1 - p.recency_floor) * 0.5 ** (age_years / half_life)


def rank(candidates: list[Candidate], p: RankParams) -> list[Scored]:
    if not candidates:
        return []
    bm_max = max((c.bm25 for c in candidates if c.bm25), default=0.0)
    has_sem = any(c.cosine is not None for c in candidates)
    w = p.bm25_weight if (bm_max and has_sem) else (1.0 if bm_max else 0.0)
    span = max(p.semantic_ceiling - p.semantic_floor, 1e-6)
    out: list[Scored] = []
    for c in candidates:
        kw = (c.bm25 or 0.0) / bm_max if bm_max else 0.0
        sem = 0.0 if c.cosine is None else min(max((c.cosine - p.semantic_floor) / span, 0.0), 1.0)
        rel = w * kw + (1 - w) * sem
        rec = recency_factor(c.date, p)
        out.append(Scored(c, rel, rec, rel * rec))
    out.sort(key=lambda s: (-s.score, -s.relevance, s.candidate.record_id))
    return out
