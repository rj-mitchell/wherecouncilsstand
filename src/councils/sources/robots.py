"""Whether a site's robots.txt lets this crawler read a page (decision 2: sites are asked, not worked around).

Used by the readers for meetings systems other than Modern.gov, whose sites differ: Civica's hosted CMIS sites forbid
all crawling, some councils' own CMIS and CoINS sites have no robots.txt. A robots.txt that can't be read (no file, or
an error page) allows everything, as the standard says; one that times out is treated as forbidding, to be safe.
"""

from __future__ import annotations

from functools import lru_cache
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx


@lru_cache(maxsize=256)
def _parser(origin: str, user_agent: str) -> RobotFileParser | None:
    rp = RobotFileParser()
    try:
        r = httpx.get(f"{origin}/robots.txt", headers={"User-Agent": user_agent}, timeout=30, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if r.status_code >= 400 or "text/plain" not in r.headers.get("content-type", "text/plain"):
        rp.parse([])          # no robots.txt (or an HTML error page): everything is allowed
    else:
        rp.parse(r.text.splitlines())
    return rp


def allowed(url: str, user_agent: str) -> bool:
    u = urlparse(url)
    rp = _parser(f"{u.scheme}://{u.netloc}", user_agent)
    return rp is not None and rp.can_fetch(user_agent, url)
