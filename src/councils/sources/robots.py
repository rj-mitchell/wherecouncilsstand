"""Whether a site's robots.txt lets this crawler read a page (decision 2: sites are asked, not worked around).

Used by every reader (decision 21): Modern.gov, CMIS and CoINS. Sites differ: Civica's hosted CMIS sites and many
councils' own Modern.gov sites forbid all crawling ("Disallow: /"), some sites have no robots.txt. A robots.txt that
isn't there (no file, or an error page) allows everything, as the standard says. One that can't be fetched at all (the
connection fails or times out) is "unknown": the CMIS and CoINS readers treat it as forbidding, to be safe, and the
Modern.gov reader as a server that is down (the council keeps what is stored and is tried again the next day).

Paths are compared as written and also ignoring case, as these (IIS) sites treat them: a rule for
``/DMS/Document.ashx`` covers ``/dms/document.ashx`` too. A page either comparison forbids is forbidden.
"""

from __future__ import annotations

import re
from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from councils.sources import tls


@lru_cache(maxsize=256)
def _parser(origin: str, user_agent: str) -> RobotFileParser | None:
    rp = RobotFileParser()
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
        rp.parse([])          # no robots.txt (or an HTML error page): everything is allowed
    else:
        rp.parse(r.text.splitlines())
    return rp


def robot_name(user_agent: str) -> str:
    """The name a robots.txt names this crawler by: "WhereCouncilsStand" in "Mozilla/5.0 (compatible;
    WhereCouncilsStand/0.1; +…)". robotparser matches a rule against the text before the first "/", which for the
    whole user agent is "Mozilla", so a council's "User-agent: WhereCouncilsStand" rule would otherwise be missed."""
    m = re.search(r"compatible;\s*([\w.-]+)/", user_agent)
    return m.group(1) if m else user_agent


def allowed(url: str, user_agent: str) -> bool:
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    return rp is not None and rp.can_fetch(robot_name(user_agent), url)


def check(url: str, user_agent: str) -> str:
    """"allowed", "forbidden", or "unknown" when the site's robots.txt couldn't be fetched."""
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    if rp is None:
        return "unknown"
    if not rp.can_fetch(robot_name(user_agent), url):
        return "forbidden"
    entry = (next((e for e in rp.entries if "*" not in e.useragents and e.applies_to(robot_name(user_agent))), None)
             or next((e for e in rp.entries if "*" in e.useragents), None) or rp.default_entry)
    if entry is None:
        return "allowed"
    path = (u.path or "/").lower()
    for line in entry.rulelines:      # the first rule that applies decides, as in urllib.robotparser
        rule = line.path.lower()
        if rule == "*" or path.startswith(rule):
            return "allowed" if line.allowance else "forbidden"
    return "allowed"


def crawl_delay(url: str, user_agent: str) -> float:
    """The Crawl-delay the site's robots.txt asks of this crawler, in seconds (0 if none)."""
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    try:
        return float(rp.crawl_delay(robot_name(user_agent)) or 0) if rp else 0.0
    except (TypeError, ValueError):
        return 0.0
