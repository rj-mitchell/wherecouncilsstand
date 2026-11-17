"""Stop loading a council whose meetings keep timing out.

A council's web service that is down or overloaded times out on every meeting, and each timeout costs the full wait
three times over (``retries`` x ``timeout_seconds``): Epping Forest's took about two minutes a meeting, for hundreds
of meetings (November 2026). After ``timeouts_in_a_row`` meetings in a row time out ([modgov] in
config/settings.toml, 2 by default), the council is stopped and nothing is stored, as when a committee can't be
listed: the next load or update tries again, and meetings already fetched come from the cache. A meeting that loads,
or fails some other way, starts the count again."""

from __future__ import annotations

import re

_TIMEOUT = re.compile(r"timed out|Timeout", re.I)


def is_timeout(error: BaseException) -> bool:
    """The error, or one it was raised from, is a timeout (httpx's own, or a reader's error that names one)."""
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        if type(error).__name__.endswith("Timeout") or _TIMEOUT.search(str(error)):
            return True
        error = error.__cause__ or error.__context__
    return False


class TimeoutStreak:
    def __init__(self, settings, council: str):
        self.limit = int(settings.modgov.get("timeouts_in_a_row", 2))
        self.council = council
        self.ids: list = []

    def ok(self) -> None:
        self.ids = []

    def failed(self, meeting_id, error: BaseException) -> str:
        """Count a failed meeting. Returns the council's error once the limit is reached, otherwise ""."""
        self.ids = self.ids + [meeting_id] if is_timeout(error) else []
        if self.limit and len(self.ids) >= self.limit:
            return (f"stopped after {len(self.ids)} meetings in a row timed out ({', '.join(map(str, self.ids))}): "
                    "the council's web service isn't answering in time; nothing is stored, so the next load or "
                    "update tries again")
        return ""
