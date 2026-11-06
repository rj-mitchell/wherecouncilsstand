"""Load and parse many councils side by side. Each council is a different server, so several run at once; requests to
any one council stay one at a time (sources/modgov.py)."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed

from councils import extract, ingest, store
from councils.config import Settings
from councils.registry import Council


def loaded(settings: Settings, council: Council) -> bool:
    return store.parquet.path(settings.parquet_dir, "meetings", council.gss).exists()


def many(settings: Settings, councils: Iterable[Council], workers: int = 10, resume: bool = False) -> Iterator[dict]:
    """Load then parse each council, yielding one summary per council as it finishes. With ``resume``, councils
    already in the store are only parsed again."""

    def one(c: Council) -> dict:
        line = {"gss": c.gss, "name": c.name}
        if not (resume and loaded(settings, c)):
            try:
                res = ingest.load(settings, c)
            except Exception as e:  # one council's failure mustn't stop the rest
                return line | {"error": f"{type(e).__name__}: {e}"}
            line |= {"meetings": res.meetings, "failed": len(res.failed),
                     "committees": sorted({f"{t} ({k})" for t, k in res.committees.values()}), "error": res.error}
        if loaded(settings, c):
            line |= extract.run(settings, c.gss)
        return line

    with ThreadPoolExecutor(workers) as ex:
        futures = [ex.submit(one, c) for c in councils]
        for f in as_completed(futures):
            yield f.result()


def _digest(settings: Settings, gss: str) -> str:
    """A fingerprint of what the index is built from: a council's stored meetings, items and attendance."""
    import hashlib

    h = hashlib.sha256()
    for table in ("meetings", "items", "attendance"):
        p = store.parquet.path(settings.parquet_dir, table, gss)
        h.update(p.read_bytes() if p.exists() else b"")
    return h.hexdigest()


def update(settings: Settings, councils: Iterable[Council], workers: int = 20) -> Iterator[dict]:
    """Bring loaded councils up to date: list each committee's meetings again, fetch new meetings and recent ones
    whose minutes may have changed (everything else comes from the cache), and parse votes again. Yields one summary
    per council, with ``changed`` set when what the search index is built from changed. A council whose server
    fails keeps what is stored (ingest.load with ``update``)."""

    def one(c: Council) -> dict:
        before = _digest(settings, c.gss)
        meetings_before = len(store.parquet.read(settings.parquet_dir, "meetings", c.gss))
        line = {"gss": c.gss, "name": c.name}
        try:
            res = ingest.load(settings, c, update=True)
        except Exception as e:  # one council's failure mustn't stop the rest
            return line | {"error": f"{type(e).__name__}: {e}", "changed": False}
        if res.error:
            return line | {"error": res.error, "changed": False}
        changed = _digest(settings, c.gss) != before
        line |= {"meetings": res.meetings, "new_meetings": res.meetings - meetings_before, "changed": changed}
        if changed:
            line |= extract.run(settings, c.gss)
        return line

    with ThreadPoolExecutor(workers) as ex:
        # a council whose site forbids reading isn't asked at all, and isn't a failure (decision 21)
        futures = [ex.submit(one, c) for c in councils if loaded(settings, c) and not c.withheld]
        for f in as_completed(futures):
            yield f.result()
