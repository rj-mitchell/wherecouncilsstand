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

from wts_core.checks import balance


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
    return balance.recency_factor(d, p.today, recency=p.recency, floor=p.recency_floor,
                                  min_half_life_years=p.min_half_life_years)


def rank(candidates: list[Candidate], p: RankParams) -> list[Scored]:
    """Every candidate scored, best first. The blend of the two relevance scores and the recency factor are the
    Where They Stand sites' shared ones (wts-core, ``wts_core.checks.balance``); the weights are this site's."""
    if not candidates:
        return []
    relevance = balance.blend([c.bm25 for c in candidates], [c.cosine for c in candidates],
                              word_weight=p.bm25_weight, meaning_floor=p.semantic_floor,
                              meaning_ceiling=p.semantic_ceiling)
    out: list[Scored] = []
    for c, rel in zip(candidates, relevance, strict=True):
        rec = recency_factor(c.date, p)
        out.append(Scored(c, rel, rec, rel * rec))
    out.sort(key=lambda s: (-s.score, -s.relevance, s.candidate.record_id))
    return out
