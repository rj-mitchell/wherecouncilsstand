"""Whether a site's robots.txt lets this crawler read a page (decision 2: sites are asked, not worked around).

Used by every reader (decision 21): Modern.gov, CMIS and CoINS. Sites differ: Civica's hosted CMIS sites and many
councils' own Modern.gov sites forbid all crawling ("Disallow: /"), some sites have no robots.txt. A robots.txt that
isn't there (no file, or an error page) allows everything, as the standard says. One that can't be fetched at all (the
connection fails or times out) is "unknown": the CMIS and CoINS readers treat it as forbidding, to be safe, and the
Modern.gov reader as a server that is down (the council keeps what is stored and is tried again the next day).

Rules are read as RFC 9309 says, not as Python's ``urllib.robotparser`` (which differs between versions): every
group naming this crawler is combined, or, if none does, every group for all crawlers ("User-agent: *"), so a file
that repeats "User-agent: *" with "Disallow: /" in its second group (Bedford's and Cornwall's, November 2026) forbids
everything; the longest matching rule decides, an Allow winning a tie; "*" and "$" in a rule are honoured. Paths are
compared as written and also ignoring case, as these (IIS) sites treat them: a rule for ``/DMS/Document.ashx`` covers
``/dms/document.ashx`` too. A page either comparison forbids is forbidden.
"""

from __future__ import annotations

import contextlib
import re
from dataclasses import dataclass, field
from functools import lru_cache
from urllib.parse import unquote, urlparse

import httpx

from councils.sources import tls


@dataclass
class Group:
    agents: list[str] = field(default_factory=list)
    rules: list[tuple[bool, str]] = field(default_factory=list)   # (allow, path)
    delay: float = 0.0


@dataclass
class Robots:
    """A site's robots.txt, as groups of rules."""

    groups: list[Group] = field(default_factory=list)

    @classmethod
    def parse(cls, text: str) -> Robots:
        groups: list[Group] = []
        current: Group | None = None
        last_was_agent = False
        for raw in text.splitlines():
            line = raw.split("#", 1)[0].strip().replace("\xa0", "")
            if ":" not in line:
                continue
            key, value = (x.strip() for x in line.split(":", 1))
            key = key.lower()
            if key == "user-agent":
                if current is None or not last_was_agent:
                    current = Group()
                    groups.append(current)
                current.agents.append(value.lower())
                last_was_agent = True
                continue
            last_was_agent = False
            if current is None:
                continue
            if key in ("allow", "disallow"):
                if value:        # an empty Disallow allows everything: no rule
                    current.rules.append((key == "allow", value))
            elif key == "crawl-delay":
                with contextlib.suppress(ValueError):
                    current.delay = max(current.delay, float(value))
        return cls(groups)

    def _groups(self, name: str) -> list[Group]:
        mine = [g for g in self.groups if any(a != "*" and a in name.lower() for a in g.agents)]
        return mine or [g for g in self.groups if "*" in g.agents]

    def allows(self, name: str, path: str) -> bool:
        rules = [r for g in self._groups(name) for r in g.rules]
        return _decide(rules, path) and _decide([(a, p.lower()) for a, p in rules], path.lower())

    def crawl_delay(self, name: str) -> float:
        return max((g.delay for g in self._groups(name)), default=0.0)


def _matches(rule: str, path: str) -> bool:
    pattern = re.escape(unquote(rule)).replace(r"\*", ".*")
    if pattern.endswith(r"\$"):
        pattern = pattern[:-2] + "$"
    return re.match(pattern, unquote(path)) is not None


def _decide(rules: list[tuple[bool, str]], path: str) -> bool:
    """The longest rule that matches decides; an Allow wins a tie; no rule allows."""
    hits = [(len(p), allow) for allow, p in rules if _matches(p, path)]
    return max(hits)[1] if hits else True


@lru_cache(maxsize=256)
def _parser(origin: str, user_agent: str) -> Robots | None:
    """The site's robots.txt; None if it couldn't be fetched."""
    url, headers = f"{origin}/robots.txt", {"User-Agent": user_agent}
    try:
        r = httpx.get(url, headers=headers, timeout=30, follow_redirects=True)
    except httpx.HTTPError as e:
        # a server that leaves out an intermediate certificate (Plymouth, Newham ...): completed as the readers do
        # (sources/tls.py), still verified
        ctx = tls.completed_context(urlparse(origin).hostname or "") if tls.is_incomplete_chain(e) else None
        if ctx is None:
            return None
        try:
            with httpx.Client(verify=ctx, headers=headers, timeout=30, follow_redirects=True) as http:
                r = http.get(url)
        except httpx.HTTPError:
            return None
    if r.status_code >= 400 or "text/plain" not in r.headers.get("content-type", "text/plain"):
        return Robots()       # no robots.txt (or an HTML error page): everything is allowed
    return Robots.parse(r.text)


def robot_name(user_agent: str) -> str:
    """The name a robots.txt names this crawler by: "WhereCouncilsStand" in "Mozilla/5.0 (compatible;
    WhereCouncilsStand/0.1; +…)"."""
    m = re.search(r"compatible;\s*([\w.-]+)/", user_agent)
    return m.group(1) if m else user_agent


@lru_cache(maxsize=1)
def obeyed() -> bool:
    """Whether robots.txt's rules are obeyed: ``[robots] obey`` in config/settings.toml. Off by the owner's decision of
    6 November 2026 (decision 21): robots.txt isn't treated as a barrier to councils' public records. Crawl-delay is
    still honoured where the file can be read."""
    from councils.config import load_settings

    return bool(load_settings().section("robots").get("obey", True))


def check(url: str, user_agent: str) -> str:
    """"allowed", "forbidden", or "unknown" when the site's robots.txt couldn't be fetched. Always "allowed" when
    robots.txt isn't obeyed (``obeyed``)."""
    if not obeyed():
        return "allowed"
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    if rp is None:
        return "unknown"
    path = (u.path or "/") + (f"?{u.query}" if u.query else "")
    return "allowed" if rp.allows(robot_name(user_agent), path) else "forbidden"


def allowed(url: str, user_agent: str) -> bool:
    return check(url, user_agent) == "allowed"


def crawl_delay(url: str, user_agent: str) -> float:
    """The Crawl-delay the site's robots.txt asks of this crawler, in seconds (0 if none)."""
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    return rp.crawl_delay(robot_name(user_agent)) if rp else 0.0
