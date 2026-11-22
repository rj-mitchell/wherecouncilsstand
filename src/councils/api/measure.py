"""Measurement for Google Ad Grants (docs/DECISIONS.md, 36; the charity's family/MEASUREMENT.md): built, and off.

The switch is ``[ads] measurement`` and ``tag`` in config/settings.toml (``COUNCILS_ADS_MEASUREMENT`` and
``COUNCILS_ADS_TAG`` in deploy/.env on the server). Off, as it ships, nothing here is used: the pages are sent as
they are built, and carry nothing of measurement but the family kit's inert ``data-wts-conversion`` marks. On, with a
valid tag, every page the server sends:

- loads the family kit's ``measure.js`` in its head, which shows the family's consent banner and loads the Google tag
  only if the reader accepts, and then sends only this site's conversions (``MEASURES``);
- has "Measurement choices" on a line of its own after the footer's notice, which opens the banner again (it is a
  control, not a page, so it is not one of the footer's six links);
- and /privacy is the measurement version of the notice, ``web/privacy-measurement.html``, never at an address of
  its own. The site refuses to start with it while it is still a draft (``NNNNNNN`` for the charity number, or
  "(draft" in its date).

This app sends no content security policy of its own: on the shared server the front door sets every site's, and
must allow the Google tag's hosts before the switch is turned on (docs/DEPLOY.md, "Measurement").
"""

from __future__ import annotations

import re
from html import escape
from pathlib import Path

from councils.config import Settings

# The conversions this site has, for measure.js (its banner names only these). This site offers no downloads, so it
# has no "download" (the charity's family/MEASUREMENT.md lists it for the briefing sites that have them).
MEASURES = "briefing_read source_opened donate_click report_sent"
PRIVACY = "/privacy"
# the measurement version of the privacy notice, as built (web/privacy-measurement.html)
NOTICE = "privacy-measurement"
CHOICES = "Measurement choices"
_TAG = re.compile(r"(?:AW|G|GT)-[A-Za-z0-9]+")
_UNFINISHED = re.compile(r"NNNNNNN|\(draft\b")
_LICENCE = re.compile(r'(<p class="licence">.*?</p>)', re.S)


def tag(settings: Settings) -> str:
    """The Google tag's ID when ``[ads] measurement`` is on with a valid tag, else "" (off)."""
    ads = settings.section("ads")
    value = str(ads.get("tag") or "").strip()
    return value if ads.get("measurement") and _TAG.fullmatch(value) else ""


def unfinished(notice: str) -> bool:
    """Whether the measurement notice is still a draft: the charity number or its date not yet filled in."""
    return bool(_UNFINISHED.search(notice))


def check_notice(dist: Path) -> None:
    """Refuse to measure without a finished measurement notice to serve at /privacy."""
    path = dist / f"{NOTICE}.html"
    if not path.is_file():
        raise RuntimeError(f"[ads] measurement is on, but there is no {path}: build the pages (web/, npm run build)")
    if unfinished(path.read_text(encoding="utf-8")):
        raise RuntimeError("[ads] measurement is on, but web/privacy-measurement.html isn't finished: put in the "
                           "charity number for NNNNNNN and the date it was last updated, then build the pages again")


def script(google_tag: str) -> str:
    """The family kit's consent banner and Google tag loader, for a page's head."""
    return (f'<script src="/family/measure.js" data-tag="{escape(google_tag)}" data-privacy="{PRIVACY}" '
            f'data-measures="{MEASURES}" defer></script>')


def choices() -> str:
    """"Measurement choices", which opens the banner again; without the script, a link to the notice's section."""
    return f'<p class="measure-choices"><a href="{PRIVACY}#measurement" data-wts-measure-open>{CHOICES}</a></p>'


def page(html: str, google_tag: str) -> str:
    """A page as the server sends it while measuring: the script in its head, and "Measurement choices" after the
    footer's notice."""
    if "</head>" in html and "/family/measure.js" not in html:
        html = html.replace("</head>", script(google_tag) + "\n  </head>", 1)
    footer = html.rfind('<footer class="site-footer">')
    if footer >= 0 and "data-wts-measure-open" not in html:
        html = html[:footer] + _LICENCE.sub(lambda m: m[1] + "\n      " + choices(), html[footer:], count=1)
    return html
