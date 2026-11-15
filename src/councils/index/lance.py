"""Search index: LanceDB tables for BM25 keyword search and vector search, through the Where They Stand sites'
shared index (wts-core, ``wts_core.adapters.lancedb``). This file is what is this site's own: its columns, the
columns indexed for filtering, and which embedder its settings name.

Two tables share the same filter columns:

* ``passages``  every searchable passage of minutes, with a BM25 full-text index on ``search_text``. Built straight
  after loading, so keyword search is available immediately.
* ``vectors``   one embedding per passage. Filled by the (slower, resumable) embedding job; hybrid search uses
  whatever is embedded so far.

Rows are keyed by ``source_key`` (one council and year, such as ``E08000038:2024``), so reloading a council's year
replaces its rows. Each passage carries its council's nation, type and region, the kind of meeting, the party in
control of the council on the date, and the parties of the councillors the passage names, so a question about any of
these is a filter on the passages themselves. Passage text has had the names of people who aren't councillors
removed (parse/redact.py).

The index records what it was built with (the embedder, its dimension) beside its tables, in ``wts_index.json``,
and refuses vectors from any other: vectors from two models are never mixed. If the embedding model is changed,
search by meaning stops (search by words carries on) until ``councils embed --again`` has embedded everything
afresh.
"""

from __future__ import annotations

from typing import Any

import pyarrow as pa
from wts_core.adapters.fastembed import FastEmbedEmbedder
from wts_core.adapters.hashing import HashingEmbedder
from wts_core.adapters.lancedb import (
    IndexSchema,
    LanceIndex,
    ScalarColumns,
    date_lit,
    sanitise_query,
    sql_list,
    sql_str,
    stored_meta,
)
from wts_core.ports import Embedder, IndexMeta, IndexOutOfDate

__all__ = ["FILTER_FIELDS", "SCHEMA", "IndexOutOfDate", "LanceIndex", "date_lit", "get_embedder", "open_index",
           "sanitise_query", "sql_list", "sql_str"]

FILTER_FIELDS = [
    ("passage_id", pa.string()),
    ("record_id", pa.string()),          # the agenda item: "<gss>:<meeting id>:<item id>"
    ("source_key", pa.string()),         # council and year: "E08000038:2024"
    ("gss", pa.string()),
    ("nation", pa.string()),             # england, wales
    ("council_type", pa.string()),       # district, unitary, metropolitan, london_borough, county, ...
    ("region", pa.string()),
    ("kind", pa.string()),               # council, cabinet, policy
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("control", pa.string()),            # party in overall control on the date, or "NOC" (reference/people.py)
    ("parties", pa.list_(pa.string())),  # parties, on the date, of the councillors the passage names
    ("members", pa.list_(pa.string())),  # the councillors it names: "<gss>:<member id>"
    ("named_vote", pa.bool_()),          # the agenda item has a named vote
]
# the further columns of the passages table
PASSAGE_FIELDS = [
    ("chunk", pa.int32()),
    ("council_name", pa.string()),
    ("committee", pa.string()),
    ("item_title", pa.string()),
    ("item_number", pa.string()),
    ("heading", pa.string()),
    ("text", pa.string()),
    ("search_text", pa.string()),
    ("url", pa.string()),
]
# Raise the version when the columns change: an index built with another is out of date, and is built again.
SCHEMA = IndexSchema(filter_fields=FILTER_FIELDS, passage_fields=PASSAGE_FIELDS, version=1)
# Indexes that let filtered searches skip the rows that do not match
SCALAR_COLUMNS = ScalarColumns(btree=("passage_id", "source_key", "record_id", "gss", "date"),
                               bitmap=("nation", "council_type", "region", "kind", "control", "named_vote", "year"))


def get_embedder(settings: Any) -> Embedder:
    """The embedder the settings name: "fastembed" (a small open-source model run locally; its weights are fetched
    once from Hugging Face into ``data/models`` and their hash is part of what the index records, so the model in
    use is pinned; no council data goes to Hugging Face) or "hashing" (deterministic and offline: word overlap
    only, for tests and the made-up record)."""
    cfg = settings.embedding
    backend = cfg.get("backend", "fastembed")
    if backend == "hashing":
        return HashingEmbedder(int(cfg.get("dim", 256)))
    if backend == "fastembed":
        return FastEmbedEmbedder(cfg["model"], settings.data_dir / "models",
                                 threads=cfg.get("threads"), batch_size=int(cfg.get("batch_size", 64)))
    raise ValueError(f"unknown embedding backend {backend!r}")


def open_index(settings: Any, embedder: Embedder | IndexMeta | None = None) -> LanceIndex:
    """The site's search index. With an embedder, the index must have been built with it (``IndexOutOfDate``
    otherwise), and vectors can be added. With none it is opened as it stands, for search by words, counts and
    writing passages: such an index adds no vectors."""
    return LanceIndex(settings.index_dir, embedder, schema=SCHEMA, scalar_columns=SCALAR_COLUMNS)


def open_as_built(settings: Any) -> LanceIndex:
    """The index opened with what it says it was built with, where it says: vectors it already holds can then be
    put back beside passages that are written again, without loading the embedding model."""
    return open_index(settings, stored_meta(settings.index_dir))
