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
