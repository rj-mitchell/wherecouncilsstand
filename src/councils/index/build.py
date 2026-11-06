"""Build the search index from the Parquet store (adapted from Where Countries Stand).

Each agenda item's minutes are split into passages of about 250 words. Before that, the names of people who aren't
councillors are removed (parse/redact.py), so neither the site nor the model ever sees them. Each passage carries
its filter columns: the council's nation, type and region, the kind of meeting, the date, the party in control of the
council on the date, the councillors it names and their parties on the date, and whether the item has a named vote.
The keyword index is built straight away; embedding (meaning search) is a separate, resumable step, newest first.
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np

from councils import store
from councils.config import Settings
from councils.embed.base import Embedder
from councils.index.lance import SearchIndex
from councils.parse import redact
from councils.parse.votes import Matcher, Member, split_names
from councils.reference import people
from councils.registry import councils

log = logging.getLogger(__name__)

_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_NAMED = re.compile(r"\b(?:Councillors?|Cllrs?\.?|Cynghorydd|Cynghorwyr)\s+((?:[A-Z][\w'’.-]*\s?){1,4}"
                    r"(?:(?:,\s*|\s+and\s+|\s*&\s*)(?:[A-Z][\w'’.-]*\s?){1,4})*)")
KIND_LABEL = {"council": "Full Council", "cabinet": "Cabinet", "policy": "Policy committee"}


def chunk_text(text: str, max_words: int = 250) -> list[str]:
    """Split on paragraph (line) boundaries into passages of at most ~max_words words."""
    chunks: list[str] = []
    current: list[str] = []
    count = 0

    def flush():
        nonlocal current, count
        if current:
            chunks.append("\n".join(current))
        current, count = [], 0

    for para in [p for p in text.split("\n") if p.strip()]:
        words = len(para.split())
        if words > max_words:
            flush()
            buf: list[str] = []
            n = 0
            for sent in _SENTENCE.split(para):
                w = len(sent.split())
                if n + w > max_words and buf:
                    chunks.append(" ".join(buf))
                    buf, n = [], 0
                buf.append(sent)
                n += w
            if buf:
                chunks.append(" ".join(buf))
            continue
        if count + words > max_words:
            flush()
        current.append(para)
        count += words
    flush()
    return chunks or [text]


def fmt_date(d) -> str:
    return f"{d.day} {d.strftime('%B %Y')}"


def named_members(text: str, matcher: Matcher) -> list[str]:
    """Member ids of the councillors a passage names ("Councillor Kitching", "Councillors Carr and Smith")."""
    out: list[str] = []
    for m in _NAMED.finditer(text):
        for name in split_names(m.group(1)):
            mid = matcher.match(name)
            if mid and mid not in out:
                out.append(mid)
    return out


def passage_rows(gss: str, settings: Settings, max_words: int = 250) -> list[dict[str, Any]]:
    root = settings.parquet_dir
    council = councils()[gss]
    items = store.parquet.read(root, "items", gss)
    meetings = {m["meeting_id"]: m for m in store.parquet.read(root, "meetings", gss)}
    attendance = store.parquet.read(root, "attendance", gss)
    who = people.build(attendance, list(meetings.values())).get(gss) or people.Council(gss)
    surnames = redact.councillor_surnames({a["name"] for a in attendance})
    voted = {v["item_id"] for v in store.parquet.read(root, "votes", gss)}
    matchers: dict[int, Matcher] = {}
    out = []
    for it in items:
        text = it.get("minutes_text") or ""
        m = meetings.get(it["meeting_id"])
        if not text.strip() or m is None:
            continue
        text, _ = redact.redact(text, surnames)
        if it["year"] not in matchers:   # councillors around that year, for matching names
            matchers[it["year"]] = Matcher([Member(mid, name, "") for mid, name in
                                            people.recent(who, it["date"], 400)])
        matcher = matchers[it["year"]]
        heading = (f"{council.name}, {m['committee_title']}, {fmt_date(it['date'])}"
                   + (f" — {it['number']} {it['title']}" if it.get("number") else f" — {it['title']}"))
        control = who.control_on(it["date"])
        for i, chunk in enumerate(chunk_text(text, max_words)):
            members = named_members(chunk, matcher)
            parties = sorted({p for p in (who.party_on(mid, it["date"]) for mid in members) if p})
            out.append({
                "passage_id": f"{it['item_id']}#{i}",
                "record_id": it["item_id"],
                "source_key": f"{gss}:{it['year']}",
                "gss": gss,
                "nation": council.nation,
                "council_type": council.type,
                "region": council.region,
                "kind": m["kind"],
                "date": it["date"],
                "year": it["year"],
                "control": control,
                "parties": parties,
                "members": [f"{gss}:{mid}" for mid in members],
                "named_vote": it["item_id"] in voted,
                "chunk": i,
                "council_name": council.name,
                "committee": m["committee_title"],
                "item_title": it["title"],
                "item_number": it.get("number") or "",
                "heading": heading,
                "text": chunk,
                # the item's title and the council's name are searchable too ("what has Barnsley said about HS2")
                "search_text": f"{it['title']}\n{council.name}\n{chunk}",
                "url": it["url"],
            })
    return out


class State:
    """Which council-years are indexed and embedded (data/index/state.json)."""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, dict[str, Any]] = json.loads(self.path.read_text()) if self.path.exists() else {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1, sort_keys=True))
        tmp.replace(self.path)

    def indexed(self, key: str, passages: int) -> None:
        self.data[key] = {"passages": passages, "embedded": False, "indexed_at": time.time()}
        self.save()

    def embedded(self, key: str) -> None:
        self.data.setdefault(key, {})["embedded"] = True
        self.save()

    def unembedded(self) -> list[str]:
        """Council-years still to embed, newest first."""
        keys = [k for k, v in self.data.items() if not v.get("embedded") and v.get("passages")]
        return sorted(keys, key=lambda k: (-int(k.split(":")[1]), k))


class Indexer:
    def __init__(self, settings: Settings, index: SearchIndex | None = None):
        self.settings = settings
        self.index = index or SearchIndex(settings.index_dir, int(settings.embedding.get("dim", 384)))
        self.state = State(settings.index_dir / "state.json")

    def index_council(self, gss: str) -> int:
        """Replace a council's passages. A council-year whose passages are all unchanged keeps its embeddings, with its
        tags (party in control, parties named) brought up to date; any other is embedded again."""
        rows = passage_rows(gss, self.settings, int(self.settings.embedding.get("passage_words", 250)))
        by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for r in rows:
            by_key[r["source_key"]].append(r)
        old = [k for k in self.state.data if k.startswith(f"{gss}:")]
        embedded = [k for k in old if self.state.data[k].get("embedded") and k in by_key]
        kept: dict[str, list] = {}
        if embedded:
            stored: dict[str, dict[str, str]] = defaultdict(dict)    # key -> passage_id -> text
            for r in self.index.rows_for_keys(embedded):
                stored[r["source_key"]][r["passage_id"]] = r["search_text"]
            vectors = self.index.vectors_for_keys(embedded)
            for k in embedded:
                new = by_key[k]
                if len(new) == len(stored[k]) and all(stored[k].get(r["passage_id"]) == r["search_text"]
                                                      and r["passage_id"] in vectors for r in new):
                    kept[k] = [vectors[r["passage_id"]] for r in new]
        self.index.replace_keys(sorted(set(old) | set(by_key)), rows)
        for k in old:
            self.state.data.pop(k, None)
        for k, v in by_key.items():
            self.state.indexed(k, len(v))
            if k in kept:
                self.index.add_vectors([], v, np.asarray(kept[k], dtype=np.float32))
                self.state.data[k]["embedded"] = True
        self.state.save()
        return len(rows)

    def index_all(self, gss_codes: list[str] | None = None) -> int:
        codes = gss_codes or sorted(p.stem for p in (self.settings.parquet_dir / "items").glob("*.parquet"))
        known = councils()
        for gss in [g for g in codes if g not in known]:
            # stored under a code no longer in councils.csv (Barnsley's and Sheffield's old codes: run
            # scripts/recode_councils.py); skipped rather than stopping the whole index
            log.warning("%s is stored but isn't in councils.csv: skipped (see scripts/recode_councils.py)", gss)
        codes = [g for g in codes if g in known]
        total = 0
        for gss in codes:
            n = self.index_council(gss)
            log.info("indexed %s: %d passages", gss, n)
            total += n
        self.index.build_indices()
        self.index.optimize()     # building leaves the previous indices behind
        return total


def update_index(settings: Settings, changed: list[str], embedder: Embedder,
                 max_seconds: float | None = None) -> dict[str, Any]:
    """The search index after the daily update: the councils whose stored meetings changed are indexed again, new
    passages are embedded for up to ``max_seconds``, and the new rows are merged into the indices (built from scratch
    only the first time, or once meaning search has grown by a fifth: SearchIndex.refresh). Nothing is written when
    nothing changed."""
    indexer = Indexer(settings)
    idx = indexer.index
    for gss in changed:              # one writer at a time; unchanged passages keep their vectors
        indexer.index_council(gss)
    done = []
    if changed or idx.unmerged():    # unmerged: rows an earlier, stopped update added
        done.append(idx.refresh())
    embedded = embed_pending(settings, idx, indexer.state, embedder, max_seconds=max_seconds)
    if embedded:
        done.append(idx.refresh())
    return {"passages_embedded": embedded, "still_to_embed": len(indexer.state.unembedded()),
            "index": "built" if "built" in done else "merged" if done else "unchanged"}


def embed_pending(settings: Settings, index: SearchIndex, state: State, embedder: Embedder, *,
                  max_seconds: float | None = None, batch: int = 2000) -> int:
    """Embed the passages of indexed-but-unembedded council-years, newest first. Returns passages embedded."""
    started = time.time()
    total = 0
    for key in state.unembedded():
        rows = index.rows_for_keys([key])
        if not rows:
            state.embedded(key)
            continue
        for i in range(0, len(rows), batch):
            part = rows[i:i + batch]
            texts = [f"{r['heading']}: {r['search_text'].split(chr(10), 2)[-1]}" for r in part]
            vecs = embedder.embed_documents(texts)
            index.add_vectors([key] if i == 0 else [], part, vecs)
            total += len(part)
            log.info("embedded %d passages (%s, %.1f/s)", total, key, total / max(time.time() - started, 1e-6))
        state.embedded(key)
        if max_seconds is not None and time.time() - started > max_seconds:
            break
    return total
