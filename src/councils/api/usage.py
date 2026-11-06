"""Spending, limits and visitors (as Where MPs Stand). Every model-written briefing costs money and the site is
public, so there are limits per visitor and overall. Over the overall cap, briefings stop for the day and the sources
are still shown, which costs nothing."""

from __future__ import annotations

import hashlib
import ipaddress
import secrets
import threading
import time
from collections import defaultdict, deque
from typing import Any

from councils.api.state import StateDB, today, utcnow


def prices_for(prices: dict[str, Any], model: str | None) -> dict[str, Any]:
    """The [usage] prices, with a model's own prices (``[usage.models."<model>"]``) on top."""
    for name, own in (prices.get("models") or {}).items():
        if model and (model == name or model.startswith(name)):
            return {**prices, **own}
    return prices


def cost_usd(usage: dict[str, int] | None, prices: dict[str, Any], model: str | None = None) -> float:
    if not usage:
        return 0.0
    p = prices_for(prices, model)
    price_in = float(p.get("price_input_per_mtok", 2.0))
    reads = usage.get("cache_read_tokens", 0) or usage.get("cache_read_input_tokens", 0) or 0
    if "cache_write_tokens" in usage:
        # the site's own counts (rag/answer.usage_dict): input_tokens includes the cache writes, priced higher below
        writes = usage.get("cache_write_tokens", 0) or 0
        uncached = usage.get("input_tokens", 0) - writes
    else:
        # the SDK's own names: its input_tokens already leaves out cache writes (and cache reads)
        writes = usage.get("cache_creation_input_tokens", 0) or 0
        uncached = usage.get("input_tokens", 0)
    return round(uncached / 1e6 * price_in
                 + writes / 1e6 * price_in * float(p.get("cache_write_multiplier", 1.25))
                 + usage.get("output_tokens", 0) / 1e6 * float(p.get("price_output_per_mtok", 10.0))
                 + reads / 1e6 * float(p.get("price_cache_read_per_mtok", 0.2)), 6)


def network_of(address: str | None) -> str:
    """The unit limits count by (as Where MPs Stand): an IPv4 address, or an IPv6 /64. One home or phone connection
    is given a whole /64, so counting single IPv6 addresses would let one person appear as countless visitors."""
    if not address:
        return "-"
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return address
    if ip.version == 4:
        return str(ip)
    if ip.ipv4_mapped:
        return str(ip.ipv4_mapped)
    return str(ip) if ip.is_loopback else str(ipaddress.ip_network(f"{ip}/64", strict=False))


def visitor_key(state: StateDB, address: str | None) -> str:
    """A code for a visitor's IP address (an IPv6 address's /64), for daily limits; the address itself is not kept.
    The secret mixed in changes every day (UTC) and old ones are deleted, so codes can't be linked across days or
    turned back into an address."""
    name = f"visitor_salt:{today()}"
    salt = state.get(name)
    if salt is None:
        with state.connect() as con:
            con.execute("INSERT OR IGNORE INTO kv (key, value) VALUES (?, ?)", (name, secrets.token_hex(16)))
            con.execute("DELETE FROM kv WHERE key LIKE 'visitor_salt:%' AND key != ?", (name,))
        salt = state.get(name)
    return hashlib.sha256(f"{salt}|{network_of(address)}".encode()).hexdigest()[:24]


def record_usage(state: StateDB, visitor: str | None, kind: str, model: str | None, usage: dict[str, int] | None,
                 prices: dict[str, Any]) -> float:
    if not usage:
        return 0.0
    cost = cost_usd(usage, prices, model)
    with state.connect() as con:
        con.execute("INSERT INTO usage VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (utcnow(), today(), visitor, kind, model, usage.get("input_tokens", 0),
                     usage.get("output_tokens", 0),
                     usage.get("cache_read_tokens", 0) or usage.get("cache_read_input_tokens", 0) or 0,
                     usage.get("cache_write_tokens", 0) or usage.get("cache_creation_input_tokens", 0) or 0, cost))
    return cost


def spent(state: StateDB, since_day: str) -> float:
    with state.connect() as con:
        row = con.execute("SELECT COALESCE(SUM(cost_usd), 0) AS c FROM usage WHERE day >= ?", (since_day,)).fetchone()
    return float(row["c"])


def count_question(state: StateDB, visitor: str) -> int:
    """Counts a new (not cached) briefing for a visitor today; returns how many they have had."""
    with state.connect() as con:
        con.execute("INSERT INTO questions (day, visitor, n) VALUES (?, ?, 1) "
                    "ON CONFLICT(day, visitor) DO UPDATE SET n = n + 1", (today(), visitor))
        con.execute("DELETE FROM questions WHERE day < ?", (today(),))
        return int(con.execute("SELECT n FROM questions WHERE day = ? AND visitor = ?",
                               (today(), visitor)).fetchone()["n"])


def questions_today(state: StateDB, visitor: str) -> int:
    with state.connect() as con:
        row = con.execute("SELECT n FROM questions WHERE day = ? AND visitor = ?", (today(), visitor)).fetchone()
    return int(row["n"]) if row else 0


def blocked(state: StateDB, visitor: str, cfg: dict[str, Any], pending_usd: float = 0.0) -> str | None:
    """Why a new briefing can't be written now, or None. ``pending_usd`` is the estimated cost of briefings being
    written at this moment, whose cost isn't recorded yet (InFlight)."""
    if questions_today(state, visitor) >= int(cfg.get("per_visitor_daily_questions", 30)):
        return "You have asked a lot of questions today, so new briefings are paused until tomorrow."
    return site_paused(state, cfg, pending_usd)


def site_paused(state: StateDB, cfg: dict[str, Any], pending_usd: float = 0.0) -> str | None:
    """Why new briefings are paused for everyone (a spending cap reached), or None: for the status page."""
    if spent(state, today()) + pending_usd >= float(cfg.get("daily_spend_cap_usd", 3.0)):
        return "The site has reached today's limit on new briefings, which keeps its costs down."
    if spent(state, today()[:8] + "01") + pending_usd >= float(cfg.get("monthly_spend_cap_usd", 50.0)):
        return "The site has reached this month's limit on new briefings, which keeps its costs down."
    return None


class InFlight:
    """Briefings being written right now (as Where MPs Stand). Their cost is only known when they finish, so without
    this, many questions at once would all pass the spending caps before any was counted: each is reserved at an
    estimated cost while it runs, and each visitor (and the site as a whole) may have only a few at once."""

    def __init__(self, per_key: int = 2, total: int = 8, estimate_usd: float = 0.15):
        self.per_key, self.total, self.estimate_usd = per_key, total, estimate_usd
        self.running: dict[str, int] = defaultdict(int)
        self.lock = threading.Lock()

    def start(self, key: str) -> str | None:
        """Reserve a place, or say why not."""
        with self.lock:
            if self.running[key] >= self.per_key:
                return "A briefing is already being written for you; please wait for it to finish."
            if sum(self.running.values()) >= self.total:
                return "Many briefings are being written at the moment; please try again in a minute."
            self.running[key] += 1
            return None

    def finish(self, key: str) -> None:
        with self.lock:
            self.running[key] -= 1
            if self.running[key] <= 0:
                del self.running[key]

    def pending_usd(self, besides: int = 0) -> float:
        """Estimated cost of the briefings in progress, not counting ``besides`` of them (the caller's own)."""
        with self.lock:
            return max(sum(self.running.values()) - besides, 0) * self.estimate_usd


class RateLimiter:
    """At most ``per_minute`` requests a minute for each key, in memory."""

    def __init__(self, per_minute: int):
        self.per_minute = per_minute
        self.hits: dict[str, deque] = defaultdict(deque)
        self.lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self.lock:
            q = self.hits[key]
            while q and now - q[0] > 60:
                q.popleft()
            if len(q) >= self.per_minute:
                return False
            q.append(now)
            if len(self.hits) > 10_000:   # forget idle visitors
                for k in [k for k, v in self.hits.items() if not v or now - v[-1] > 60]:
                    del self.hits[k]
            return True
