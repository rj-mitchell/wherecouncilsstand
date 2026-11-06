"""Readable text and page details in the HTML the server sends (as Where MPs Stand's plaintext.py), for anything that
reads pages without running their scripts: search engines, AI assistants, readers with scripts off. The text goes
where the app later draws the page, so people with scripts on see no difference. Plain HTML only, every value
escaped."""

from __future__ import annotations

import json
import re
from datetime import date
from html import escape as e
from typing import Any
from urllib.parse import quote

SITE = "Where Councils Stand"
MAX_ITEMS = 60
KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee"}
SIDES = ("for", "against", "abstain")
# a Scottish division is between a motion and an amendment: each side is for something
MOTION_OR_AMENDMENT = "motion or amendment"

_APP = '<div id="app"></div>'
_NEEDS_JS = re.compile(r"\s*<noscript><p>This page needs JavaScript\..*?</noscript>", re.S)
_HEAD_TAGS = re.compile(
    r'\s*<(?:title>[^<]*</title|meta name="(?:description|robots|twitter:card)"[^>]*|link rel="canonical"[^>]*|'
    r'meta property="og:(?:title|description|url|type|site_name|locale)"[^>]*)>', re.I)


def long_date(iso: str | date | None) -> str:
    if not iso:
        return ""
    d = iso if isinstance(iso, date) else date.fromisoformat(str(iso)[:10])
    return f"{d.day} {d.strftime('%B %Y')}"


def month_year(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%B %Y") if iso else ""


def council_path(gss: str) -> str:
    return f"/councils/{quote(gss)}"


def vote_path(vote_id: str) -> str:
    return f"/votes/{quote(vote_id, safe=':')}"


# ---- the page shell ------------------------------------------------------------------------------------------------

def with_text(page: str, fragment: str | None) -> str:
    """The page with ``fragment`` in its app root (replaced by the app when it starts), and without its "needs
    JavaScript" note, which is no longer true."""
    if not fragment or _APP not in page:
        return page
    return _NEEDS_JS.sub("", page.replace(_APP, f'<div id="app">{fragment}</div>', 1), count=1)


def page_with_meta(page: str, *, title: str, description: str, url: str, noindex: bool = False,
                   data: dict[str, Any] | None = None) -> str:
    """The page with its own title, description, canonical address and link-preview text, and ``data`` (schema.org
    structured data, for search engines) if given. The link-preview image stays the family kit's card, from the
    page's head."""
    tags = [f"<title>{e(title)}</title>",
            f'<meta name="description" content="{e(description)}" />',
            f'<link rel="canonical" href="{e(url)}" />',
            f'<meta property="og:site_name" content="{SITE}" />',
            '<meta property="og:type" content="website" />',
            '<meta property="og:locale" content="en_GB" />',
            f'<meta property="og:title" content="{e(title)}" />',
            f'<meta property="og:description" content="{e(description)}" />',
            f'<meta property="og:url" content="{e(url)}" />',
            '<meta name="twitter:card" content="summary_large_image" />']
    if noindex:
        tags.append('<meta name="robots" content="noindex" />')
    if data:  # "</" is escaped so the data cannot end the script element
        tags.append('<script type="application/ld+json">' + json.dumps(data).replace("</", "<\\/") + "</script>")
    head = "\n    " + "\n    ".join(tags) + "\n  </head>"
    return re.sub(r"\s*</head>", lambda _: head, _HEAD_TAGS.sub("", page), count=1)


def _link(href: str | None, text: str) -> str:
    return f'<a href="{e(href)}">{e(text)}</a>' if href else e(text)


def _plural(n: int, one: str, many: str | None = None) -> str:
    return f"{n:,} {one if n == 1 else (many or one + 's')}"


def side_label(side: str, question: str | None) -> str:
    if question == MOTION_OR_AMENDMENT:
        return {"for": "For the motion", "against": "For the amendment", "abstain": "Abstained"}[side]
    return {"for": "For", "against": "Against", "abstain": "Abstained"}[side]


def vote_on(question: str | None) -> str:
    if not question:
        return ""
    return " between a motion and an amendment" if question == MOTION_OR_AMENDMENT else f" on the {question}"


def _tally(counts: dict[str, int], question: str | None) -> str:
    return ", ".join(f"{side_label(s, question)} {counts.get(s, 0)}" for s in SIDES)


# ---- a council -----------------------------------------------------------------------------------------------------

def council_description(c: dict[str, Any]) -> str:
    if not c.get("loaded"):
        return (f"{c['name']} ({c.get('type_name') or 'council'}, {c.get('region_name') or c.get('nation') or 'UK'}): "
                "not covered yet. " + " ".join(c.get("reasons") or []))
    control = (c.get("control") or {}).get("name")
    return (f"{c['name']}: full council and cabinet meetings from {month_year(c.get('from'))} to "
            f"{month_year(c.get('to'))}, from the council's own minutes. "
            + (f"In overall control: {control}. " if control else "")
            + f"{_plural(c.get('meetings') or 0, 'meeting')} and {_plural(c.get('named_votes') or 0, 'named vote')}, "
            "with each councillor's party on the date.")


def council_data(c: dict[str, Any], url: str, base: str) -> dict[str, Any]:
    """schema.org: the page, about the council."""
    org: dict[str, Any] = {"@type": "GovernmentOrganization", "name": c["name"],
                           "identifier": {"@type": "PropertyValue", "propertyID": "GSS code", "value": c["gss"]},
                           "areaServed": c.get("region_name") or c.get("nation")}
    return {"@context": "https://schema.org", "@type": "WebPage", "name": c["name"], "url": url,
            "description": council_description(c), "inLanguage": "en-GB",
            "isPartOf": {"@type": "WebSite", "name": SITE, "url": base + "/"}, "about": org}


def council_text(c: dict[str, Any]) -> str:
    parts = [f'<p class="meta"><a href="/councils">Councils</a> · {e(c.get("type_name") or "")} · '
             f'{e(c.get("region_name") or "")}</p>', f"<h1>{e(c['name'])}</h1>"]
    if not c.get("loaded"):
        parts.append(f"<p>This council isn't covered yet. {e(' '.join(c.get('reasons') or []))} Councils are covered "
                     "when their minutes are published through a system the site can read (Modern.gov, CMIS or CoINS) "
                     "and their site can be read.</p>")
        return parts[0] + parts[1] + parts[2] + _landlords(c)
    parts.append(f"<p>Full council and cabinet meetings from {e(month_year(c.get('from')))} to "
                 f"{e(month_year(c.get('to')))}, read from the council's {_link(c.get('site'), 'own record')}.</p>")
    control = c.get("control") or {}
    facts = [f"In overall control: {control['name']}"
             + (f", as listed on {long_date(control['as_of'])}" if control.get("as_of") else "") if control else
             "Party in overall control: not recorded",
             f"{_plural(c.get('meetings') or 0, 'meeting')}: {c.get('council_meetings') or 0:,} full council, "
             f"{c.get('cabinet_meetings') or 0:,} cabinet"
             + (f", {c['policy_meetings']:,} policy committee" if c.get("policy_meetings") else ""),
             f"{_plural(c.get('named_votes') or 0, 'named vote')} recorded in the minutes"]
    parts.append("<ul>" + "".join(f"<li>{e(f)}</li>" for f in facts) + "</ul>")
    parts.append(_landlords(c))
    seats = c.get("seats")
    if seats:
        parts.append(f"<h2>Members by party</h2><p>The {seats['total']:,} councillors listed at the full council "
                     f"meeting of {e(long_date(seats['date']))}, with their party as the council recorded it.</p><ul>"
                     + "".join(f"<li>{e(p['name'])}: {p['members']:,}</li>" for p in seats["parties"]) + "</ul>")
    if c.get("control_timeline"):
        parts.append("<h2>Party in overall control</h2><ul>" + "".join(
            f"<li>From {e(month_year(t['from']))}: {e(t['name'])}</li>" for t in c["control_timeline"]) + "</ul>")
    votes = c.get("votes") or []
    parts.append(f"<h2>Named votes ({len(votes):,})</h2>")
    if not votes:
        parts.append("<p>No named votes were found in this council's minutes.</p>")
    else:
        parts.append("<ol>")
        for v in votes[:MAX_ITEMS]:
            what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "")
            parts.append(f"<li>{_link(vote_path(v['vote_id']), v.get('item') or 'Named vote')}: {e(what)}, "
                         f"{e(long_date(v.get('date')))}, a named vote{e(vote_on(v.get('question')))}"
                         f"{', ' + e(v['outcome']) if v.get('outcome') else ''}. "
                         f"{e(_tally(v.get('counts') or {}, v.get('question')))}.</li>")
        parts.append("</ol>")
        if len(votes) > MAX_ITEMS:
            parts.append(f"<p>The {len(votes) - MAX_ITEMS:,} earlier named votes are listed on this page when it "
                         "runs in a browser.</p>")
    if c.get("recent"):
        parts.append("<h2>Latest meetings</h2><ul>" + "".join(
            f"<li>{e(long_date(m['date']))}: {_link(m.get('url'), m.get('committee') or 'Meeting')}"
            f"{'' if m.get('items_with_minutes') else ' (minutes not published yet)'}</li>" for m in c["recent"])
            + "</ul>")
    return "".join(parts)


def _landlords(c: dict[str, Any]) -> str:
    ll = c.get("landlords") or {}
    links = []
    if ll.get("council"):
        links.append(_link(ll["council"]["url"], f"{ll['council']['name']} as a landlord"))
    if ll.get("area"):
        a = ll["area"]
        links.append(_link(a["url"], f"The social landlord with homes in {a['name']}" if a.get("landlords") == 1
                           else f"The {a.get('landlords', 0):,} social landlords with homes in {a['name']}"))
    if not links:
        return ""
    return "<h2>On Where Landlords Stand</h2><ul>" + "".join(f"<li>{x}</li>" for x in links) + "</ul>"


# ---- a named vote --------------------------------------------------------------------------------------------------

def vote_title(v: dict[str, Any]) -> str:
    return f"{v.get('item') or 'Named vote'}, {v['council']}"


def vote_description(v: dict[str, Any]) -> str:
    what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "A meeting")
    return (f"{v['council']}, {what.lower() if what in KIND_LABEL.values() else what}, {long_date(v.get('date'))}: "
            f"a named vote{vote_on(v.get('question'))}{', ' + v['outcome'] if v.get('outcome') else ''}. "
            f"{_tally(v.get('counts') or {}, v.get('question'))}, with each councillor's party on the date.")


def vote_data(v: dict[str, Any], url: str, base: str) -> dict[str, Any]:
    meeting = f"{KIND_LABEL.get(v.get('kind', ''), v.get('committee') or 'Meeting')}, {long_date(v.get('date'))}"
    return {"@context": "https://schema.org", "@type": "WebPage", "name": vote_title(v), "url": url,
            "description": vote_description(v), "inLanguage": "en-GB",
            "isPartOf": {"@type": "WebSite", "name": SITE, "url": base + "/"},
            "about": [{"@type": "GovernmentOrganization", "name": v["council"],
                       "url": base + council_path(v["gss"])},
                      {"@type": "Event", "name": f"{v['council']}: {meeting}", "startDate": v.get("date"),
                       **({"url": v["url"]} if v.get("url") else {})}]}


def vote_text(v: dict[str, Any]) -> str:
    what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "")
    parts = [f'<p class="meta"><a href="/councils">Councils</a> · {_link(council_path(v["gss"]), v["council"])}</p>',
             f"<h1>{e(v.get('item') or 'Named vote')}</h1>",
             f"<p>{e(what)}, {e(long_date(v.get('date')))}: a named vote{e(vote_on(v.get('question')))}"
             f"{', ' + e(v['outcome']) if v.get('outcome') else ''}.</p>",
             f"<p>{e(_tally(v.get('counts') or {}, v.get('question')))}.</p>",
             f"<p>Party in overall control of the council on the date: {e(v.get('control') or 'not recorded')}. Each "
             "councillor's party is the one the council recorded for them at the time.</p>"]
    if v.get("partial"):
        parts.append("<p>Only one side of this vote could be read from the minutes. The others may be recorded in a "
                     "form that couldn't be read, or not at all.</p>")
    for side in SIDES:
        members = [m for m in v.get("members") or [] if m.get("side") == side]
        if not members:
            continue
        parts.append(f"<h2>{e(side_label(side, v.get('question')))} ({len(members)})</h2><ul>" + "".join(
            f"<li>{e(m['name'])} ({e(m['party']) if m.get('party') else 'not matched to a member'})</li>"
            for m in members) + "</ul>")
    parts.append("<h2>From the minutes</h2>")
    if v.get("from_table"):
        parts.append("<p>The minutes set this vote out as a table, with a row or column for each councillor.</p>")
    elif v.get("excerpt"):
        parts.append(f"<blockquote><p>{e(v['excerpt'])}</p></blockquote>")
    parts.append(f"<p>{_link(v.get('url'), "The item in the council's own minutes")}. Names are matched to the "
                 "councillors listed at the meeting. The names of people who aren't councillors are removed.</p>")
    return "".join(parts)


# ---- the list of councils, and the home page -----------------------------------------------------------------------

COVERAGE = {"full": "Full", "partial": "Partial", "not_yet": "Not yet"}


def councils_text(directory: dict[str, Any]) -> str:
    rows = directory.get("councils") or []
    loaded = [r for r in rows if r.get("loaded")]
    parts = ["<h1>Councils</h1>",
             f"<p>{len(loaded):,} of the {len(rows):,} principal councils in the UK are covered: those whose minutes "
             "are published through a system we can read (Modern.gov, CMIS or CoINS). Coverage starts in May "
             "2018.</p>", "<h2>Covered</h2><ul>"]
    for r in loaded:
        control = (r.get("control") or {}).get("name")
        parts.append(f"<li>{_link(council_path(r['gss']), r['name'])}: {e(r.get('type_name') or '')}, "
                     f"{e(r.get('region_name') or '')}. Coverage: {COVERAGE.get(r.get('coverage', ''), '')}. "
                     f"{e(month_year(r.get('from')))} to {e(month_year(r.get('to')))}"
                     f"{'; in overall control: ' + e(control) if control else ''}.</li>")
    parts.append("</ul><h2>Not covered yet</h2><ul>")
    for r in rows:
        if not r.get("loaded"):
            parts.append(f"<li>{_link(council_path(r['gss']), r['name'])}: {e(' '.join(r.get('reasons') or []))}"
                         "</li>")
    parts.append("</ul>")
    return "".join(parts)


def home_text(totals: dict[str, Any], examples: list[str]) -> str:
    return ("<h1>What has your council decided?</h1>"
            "<p>Ask about anything councils across the UK have discussed, decided or voted on at full council and "
            "cabinet. Every point in the briefing cites the council's own minutes.</p>"
            f"<p>The record holds {totals.get('meetings', 0):,} meetings and {totals.get('named_votes', 0):,} named "
            f"votes from {totals.get('loaded', 0):,} of the {totals.get('councils', 0):,} councils in the UK, "
            "since May 2018. Asking a question needs JavaScript; every council's page, with its named votes, can "
            "be read without it, from the <a href=\"/councils\">list of councils</a>.</p>"
            "<h2>For example</h2><ul>" + "".join(f"<li>{e(q)}</li>" for q in examples) + "</ul>"
            '<p><a href="/methodology">How it works</a></p>')
