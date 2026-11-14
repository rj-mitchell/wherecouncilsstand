"""Deterministic retrieval: filters -> BM25 + vector candidates -> composite rank -> balanced records (adapted from
Where Countries Stand).

Given the same index, query text, filters and slider values, results are identical every time. The only
non-deterministic step, turning a plain-English question into filters, happens before this (``rag.query_parse``)
and its output is shown to the reader as editable filters.
"""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import Any

from wts_core.ports import Embedder

from councils.config import Settings
from councils.index.lance import (
    IndexOutOfDate,
    date_lit,
    get_embedder,
    open_index,
    sql_list,
    sql_str,
)
from councils.rank.composite import Candidate, RankParams, Scored, rank
from councils.rank.evidence import GROUP_BY, evidence_summary, select_evidence
from councils.registry import withheld_codes

log = logging.getLogger(__name__)

CARRY = ("gss", "nation", "council_type", "region", "kind", "control", "year", "named_vote")


@dataclass
class Filters:
    date_from: date | None = None
    date_to: date | None = None
    councils: list[str] = field(default_factory=list)      # GSS codes
    nations: list[str] = field(default_factory=list)       # england, wales
    regions: list[str] = field(default_factory=list)
    council_types: list[str] = field(default_factory=list)  # ... or "strategic_authority"
    kinds: list[str] = field(default_factory=list)         # council, cabinet, policy; board, mayor, scrutiny
    control: list[str] = field(default_factory=list)       # party codes in overall control, or "NOC"; for strategic
                                                           # authorities "MAYOR:<party>" or "SA:NONE" (decision 19)
    parties: list[str] = field(default_factory=list)       # parties of councillors named in the passage
    named_votes_only: bool = False

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("date_from", "date_to"):
            d[k] = d[k].isoformat() if d[k] else None
        return d


@dataclass
class SearchResult:
    scored: list[Scored]
    records: list[dict[str, Any]]
    no_records: bool
    candidates: int
    semantic_available: bool
    where: str | None
    evidence: dict[str, Any] = field(default_factory=dict)


def build_where(f: Filters) -> str:
    clauses = []
    if f.date_from:
        clauses.append(f"date >= {date_lit(f.date_from)}")
    if f.date_to:
        clauses.append(f"date <= {date_lit(f.date_to)}")
    for col, values in (("gss", f.councils), ("nation", f.nations), ("region", f.regions),
                        ("council_type", f.council_types), ("kind", f.kinds), ("control", f.control)):
        if values:
            clauses.append(f"{col} IN ({', '.join(sql_str(v) for v in values)})")
    if f.parties:
        clauses.append(f"array_has_any(parties, {sql_list(f.parties)})")
    if f.named_votes_only:
        clauses.append("named_vote = true")
    return " AND ".join(clauses)


class Engine:
    def __init__(self, settings: Settings, embedder: Embedder | None = None, today: date | None = None):
        self.settings = settings
        self.index = open_index(settings)      # as it stands: search by words needs no embedding model
        self._embedder = embedder
        self.today = today
        self._has_vectors = False
        self._meaning: bool | None = None      # whether the index was built with this embedder; None: not yet asked

    def has_vectors(self) -> bool:
        if not self._has_vectors:
            self._has_vectors = self.index.stats()["vectors"] > 0
        return self._has_vectors

    @property
    def embedder(self) -> Embedder | None:
        if self._embedder is None:
            try:
                self._embedder = get_embedder(self.settings)
            except Exception as exc:  # semantic search degrades to keyword-only
                log.warning("embedder unavailable (%s); using keyword search only", exc)
                return None
        return self._embedder

    def searches_by_meaning(self) -> bool:
        """Whether search by meaning can be used: there are vectors, there is an embedder, and the vectors were
        made with it. An index built with another embedding model is never searched with this one's vectors: the
        search carries on by words alone, until everything has been embedded again (``councils embed --again``)."""
        if not self.has_vectors() or self.embedder is None:
            return False
        if self._meaning is None:
            try:
                self.index = open_index(self.settings, self.embedder)
                self._meaning = True
            except IndexOutOfDate as exc:
                log.error("search by meaning is off: %s. Search by words carries on; run `councils embed --again`",
                          exc)
                self._meaning = False
        return self._meaning

    def search(self, query: str, filters: Filters | None = None, recency: float | None = None, limit: int = 12,
               diversify: bool = True, group_by: str = "control") -> SearchResult:
        f = filters or Filters()
        r = self.settings.ranking
        where = build_where(f)
        held = withheld_codes()
        if held:   # passages of a council withheld since it was indexed (decision 21), until the update removes them
            where = " AND ".join(w for w in (where, f"gss NOT IN ({', '.join(sql_str(g) for g in held)})") if w)

        def keyword() -> list[dict[str, Any]]:
            return self.index.search_words(query, where, int(r.get("candidates_bm25", 300)))

        with ThreadPoolExecutor(max_workers=1) as pool:
            by_keyword = pool.submit(keyword)
            vec_hits: list[dict[str, Any]] = []
            semantic = self.searches_by_meaning()
            if semantic:
                vec = self.embedder.embed_query(query)
                vec_hits = self.index.search_meaning(vec, where, int(r.get("candidates_vector", 300)),
                                                     nprobes=r.get("vector_nprobes"),
                                                     refine_factor=r.get("vector_refine_factor"))
            bm = by_keyword.result()

        cands: dict[str, Candidate] = {}

        def cand_for(hit: dict[str, Any]) -> Candidate:
            c = cands.get(hit["record_id"])
            if c is None:
                c = Candidate(record_id=hit["record_id"], date=hit["date"],
                              data={k: hit.get(k) for k in CARRY} | {"passages": {}})
                cands[hit["record_id"]] = c
            return c

        for h in bm:
            c = cand_for(h)
            c.data["passages"][h["passage_id"]] = h
            if c.bm25 is None or h["_score"] > c.bm25:
                c.bm25 = float(h["_score"])
                c.best_passage_id = h["passage_id"]
        for h in vec_hits:
            c = cand_for(h)
            sim = 1.0 - float(h["_distance"])
            if c.cosine is None or sim > c.cosine:
                c.cosine = sim
                if c.bm25 is None:
                    c.best_passage_id = h["passage_id"]

        floor, ceiling = getattr(self.embedder, "similarity_range", (0.5, 0.85)) if semantic else (0.5, 0.85)
        params = RankParams.from_settings(
            r, recency=recency, semantic_floor=r.get("semantic_floor", floor),
            semantic_ceiling=r.get("semantic_ceiling", ceiling), **({"today": self.today} if self.today else {}))
        scored = rank(list(cands.values()), params)
        if diversify and scored:
            top = select_evidence(scored[:max(limit * 8, 150)], limit,
                                  group_by=group_by if group_by in GROUP_BY else "control",
                                  max_per_council=int(r.get("max_per_council", 2)),
                                  max_per_meeting=int(r.get("max_per_meeting", 1)),
                                  min_relevance_ratio=float(r.get("min_relevance_ratio", 0.25)))
        else:
            top = scored[:limit]
        records = self.records_for(top) if top else []
        return SearchResult(top, records, not scored, len(cands), semantic, where,
                            evidence_summary(records, group_by))

    def records_for(self, scored: list[Scored]) -> list[dict[str, Any]]:
        """One record per chosen agenda item: its best passage, with the item's details."""
        missing = [s.candidate.best_passage_id for s in scored
                   if s.candidate.best_passage_id and s.candidate.best_passage_id not in s.candidate.data["passages"]]
        extra = self.index.passages_for(missing)
        out = []
        for s in scored:
            pid = s.candidate.best_passage_id or ""
            p = s.candidate.data["passages"].get(pid) or extra.get(pid)
            if not p:
                continue
            out.append({
                "record_id": s.candidate.record_id,
                "passage_id": pid,
                **{k: p.get(k) for k in ("gss", "nation", "council_type", "region", "kind", "control", "council_name",
                                         "committee", "item_title", "item_number", "heading", "url", "named_vote")},
                "parties": list(p.get("parties") or []),
                "members": list(p.get("members") or []),
                "date": p["date"].isoformat(),
                "year": p["date"].year,
                "text": p["text"],
                "ranking": s.breakdown(),
            })
        return out
