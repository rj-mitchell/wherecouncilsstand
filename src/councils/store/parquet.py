"""Zstd-compressed Parquet storage: one file per table and council.

Each table lives at ``parquet/<table>/<gss>.parquet`` and is replaced whole when a council is loaded again, which
keeps loading idempotent. The raw responses are cached separately (sources/modgov.py), so reloading is cheap.
"""

from __future__ import annotations

import os
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

MEETING_SCHEMA = pa.schema([
    ("meeting_id", pa.string()),        # "<gss>:<Modern.gov meeting id>"
    ("gss", pa.string()),
    ("council", pa.string()),
    ("committee_id", pa.int64()),
    ("committee_title", pa.string()),
    ("kind", pa.string()),              # "council", "cabinet", "policy" (committees.py)
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("status", pa.string()),
    ("location", pa.string()),
    ("webcast", pa.bool_()),
    ("minutes_published", pa.bool_()),
    ("items", pa.int32()),
    ("items_with_minutes", pa.int32()),
    ("minutes_pdf_url", pa.string()),   # a document titled as minutes, where there is one
    ("attendees", pa.int32()),
    ("url", pa.string()),
])

ITEM_SCHEMA = pa.schema([
    ("item_id", pa.string()),           # "<meeting_id>:<agenda item id>"
    ("meeting_id", pa.string()),
    ("gss", pa.string()),
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("position", pa.int32()),
    ("number", pa.string()),            # as the minutes number it: "187."
    ("title", pa.string()),
    ("agenda_text", pa.string()),
    ("minutes_text", pa.string()),
    ("is_decision", pa.bool_()),
    ("is_restricted", pa.bool_()),
    ("is_call_in", pa.bool_()),
    ("declaration_count", pa.int32()),
    ("documents", pa.int32()),
    ("url", pa.string()),
])

ATTENDANCE_SCHEMA = pa.schema([
    ("meeting_id", pa.string()),
    ("gss", pa.string()),
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("member_id", pa.string()),         # Modern.gov's id for the person on that council's site
    ("member_type", pa.string()),
    ("name", pa.string()),              # as recorded: "Councillor Dave Leech"
    ("role", pa.string()),              # "Mayor", "Committee Member", "Chair"
    ("attendance", pa.string()),        # "Present, as expected", "Apologies", "Absent"
    ("party_label", pa.string()),       # the council's own label on the date: "LAB", "Labour", "REFUK"
    ("party", pa.string()),             # standard code (parse/parties.py); "" if not recognised
    ("ward", pa.string()),
])

VOTE_SCHEMA = pa.schema([
    ("vote_id", pa.string()),           # "<item_id>:<n>"
    ("item_id", pa.string()),
    ("meeting_id", pa.string()),
    ("gss", pa.string()),
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("question", pa.string()),          # what was voted on, as the minutes put it, where they say
    ("outcome", pa.string()),           # "carried", "lost", or "" if the minutes don't say
    ("member_id", pa.string()),         # matched to the meeting's attendance; "" if not matched
    ("name", pa.string()),              # as written in the minutes
    ("vote", pa.string()),              # "for", "against", "abstain"
    ("excerpt", pa.string()),           # the passage of the minutes the vote was read from
])

DECLARATION_SCHEMA = pa.schema([
    ("item_id", pa.string()),
    ("meeting_id", pa.string()),
    ("gss", pa.string()),
    ("date", pa.date32()),
    ("year", pa.int32()),
    ("member_id", pa.string()),
    ("name", pa.string()),
    ("interest", pa.string()),          # "disclosable pecuniary", "pecuniary", "non-pecuniary", "other registrable",
                                        # "personal", "prejudicial", "" (as the minutes call it)
    ("excerpt", pa.string()),
])

SCHEMAS = {"meetings": MEETING_SCHEMA, "items": ITEM_SCHEMA, "attendance": ATTENDANCE_SCHEMA,
           "votes": VOTE_SCHEMA, "declarations": DECLARATION_SCHEMA}


def path(root: Path, table: str, gss: str) -> Path:
    return Path(root) / table / f"{gss}.parquet"


def write(root: Path, table: str, gss: str, rows: Iterable[dict[str, Any]]) -> Path:
    """Replace one council's rows in one table."""
    p = path(root, table, gss)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".parquet.tmp")
    pq.write_table(pa.Table.from_pylist(list(rows), schema=SCHEMAS[table]), tmp, compression="zstd")
    os.replace(tmp, p)
    return p


def read(root: Path, table: str, gss: str) -> list[dict[str, Any]]:
    p = path(root, table, gss)
    return pq.read_table(p).to_pylist() if p.exists() else []


def attach(con: duckdb.DuckDBPyConnection, root: Path) -> list[str]:
    """A view per table over every council's file. Returns the views created."""
    made = []
    for table in SCHEMAS:
        files = sorted(str(p) for p in (Path(root) / table).glob("*.parquet"))
        if files:
            con.execute(f"CREATE OR REPLACE VIEW {table} AS SELECT * FROM read_parquet({files!r}, union_by_name=true)")
            made.append(table)
    return made
