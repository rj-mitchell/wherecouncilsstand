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

from councils.api.statements import safe_link

SITE = "Where Councils Stand"
MAX_ITEMS = 60
KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee", "board": "Board",
              "mayor": "Mayor's decisions", "scrutiny": "Overview and scrutiny"}
AUTHORITY = "strategic_authority"
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

def _is_authority(c: dict[str, Any]) -> bool:
    return c.get("type") == AUTHORITY


def _region(c: dict[str, Any]) -> str:
    regions = [r["name"] for r in c.get("regions") or []]
    return " and ".join(regions) if len(regions) > 1 else (c.get("region_name") or "")


def _mayor_now(c: dict[str, Any]) -> str:
    control = c.get("control") or {}
    if control.get("mayor"):
        return f"Mayor: {control['mayor']} ({control['name'].removeprefix('Mayor: ')})"
    return "No mayor: no single party"


def authority_description(c: dict[str, Any]) -> str:
    what = f"{c['name']} ({c.get('kind_name') or 'strategic authority'}, {_region(c) or 'England'})"
    if not c.get("loaded"):
        return f"{what}: not covered yet. " + " ".join(c.get("reasons") or [])
    return (f"{what}: board, and overview and scrutiny meetings from {month_year(c.get('from'))} to "
            f"{month_year(c.get('to'))}, from the authority's own minutes. {_mayor_now(c)}. "
            f"{_plural(c.get('meetings') or 0, 'meeting')} and {_plural(c.get('named_votes') or 0, 'named vote')}, "
            "with each member's role and party on the date.")


def council_description(c: dict[str, Any]) -> str:
    if _is_authority(c):
        return authority_description(c)
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
    key = "GSS code" if not c["gss"].startswith("SA-") else "Provisional key (no ONS code yet)"
    org: dict[str, Any] = {"@type": "GovernmentOrganization", "name": c["name"],
                           "identifier": {"@type": "PropertyValue", "propertyID": key, "value": c["gss"]},
                           "areaServed": _region(c) or c.get("nation")}
    if _is_authority(c):
        org["additionalType"] = c.get("kind_name") or "Strategic authority"
        org["member"] = [{"@type": "GovernmentOrganization", "name": m["name"], "url": base + council_path(m["gss"])}
                         for m in c.get("constituents") or []]
    elif c.get("authorities"):
        org["memberOf"] = [{"@type": "GovernmentOrganization", "name": a["name"], "url": base + council_path(a["gss"])}
                           for a in c["authorities"]]
    return {"@context": "https://schema.org", "@type": "WebPage", "name": c["name"], "url": url,
            "description": council_description(c), "inLanguage": "en-GB",
            "isPartOf": {"@type": "WebSite", "name": SITE, "url": base + "/"}, "about": org}


def _part_of(c: dict[str, Any]) -> str:
    """A council's strategic authorities: "Part of: West Yorkshire Combined Authority"."""
    links = [_link(council_path(a["gss"]), a["name"]) + ("" if a.get("role") == "constituent"
                                                         else f" ({e(a['role_name'].lower())})")
             for a in c.get("authorities") or []]
    return f"<p>Part of: {', '.join(links)}.</p>" if links else ""


def _constituents(c: dict[str, Any]) -> str:
    rows = c.get("constituents") or []
    if not rows:
        return ""
    by_role: dict[str, list[str]] = {}
    for m in rows:
        dates = (f" (from {long_date(m['from'])})" if m.get("from") else "") + \
                (f" (until {long_date(m['to'])})" if m.get("to") else "")
        by_role.setdefault(m["role_name"], []).append(_link(council_path(m["gss"]), m["name"]) + e(dates))
    return "".join(f"<p>{e(role)}s: {', '.join(names)}.</p>" for role, names in by_role.items())


def _mayors(c: dict[str, Any]) -> str:
    rows = c.get("mayors") or []
    if not rows:
        return "<h2>Mayor</h2><p>It has no mayor, so no single party controls it: its members are appointed by its " \
               "councils.</p>"
    items = "".join(f"<li>{e(m['name'])} ({e(m['party_name'])}): from {e(long_date(m['from']))}"
                    f"{' to ' + e(long_date(m['to'])) if m.get('to') else ''}</li>" for m in rows)
    return ("<h2>Mayors</h2><ul>" + items + "</ul><p>Each with the party they were elected for. A mayor's party is "
            "shown in place of a party in control: a strategic authority isn't run by a party.</p>")


def authority_text(c: dict[str, Any]) -> str:
    parts = [f'<p class="meta"><a href="/councils">Councils</a> · Strategic authority · {e(_region(c))}</p>',
             f"<h1>{e(c['name'])}</h1>",
             f"<p>{e(c.get('kind_name') or '')}"
             + (f"; {e(c['category_name'][0].lower() + c['category_name'][1:])}" if c.get("category_name") else "")
             + (f". Created {e(c['created'])}" if c.get("created") else "") + ".</p>",
             _constituents(c)]
    if not c.get("loaded"):
        parts.append(f"<p>This strategic authority isn't covered yet. {e(' '.join(c.get('reasons') or []))}</p>")
        return "".join(parts) + _mayors(c)
    parts.append(f"<p>Board, and overview and scrutiny committee meetings from {e(month_year(c.get('from')))} to "
                 f"{e(month_year(c.get('to')))}, read from the authority's {_link(c.get('site'), 'own record')}.</p>")
    facts = [_mayor_now(c),
             f"{_plural(c.get('meetings') or 0, 'meeting')}: {c.get('board_meetings') or 0:,} board, "
             f"{c.get('scrutiny_meetings') or 0:,} overview and scrutiny"
             + (f", {c['mayor_meetings']:,} of the mayor's decisions" if c.get("mayor_meetings") else ""),
             f"{_plural(c.get('named_votes') or 0, 'named vote')} recorded in the minutes"]
    parts.append("<ul>" + "".join(f"<li>{e(f)}</li>" for f in facts) + "</ul>")
    parts.append(_mayors(c))
    members = c.get("members")
    if members:
        parts.append(f"<h2>Members</h2><p>Listed at the {e(members['committee'])} meeting of "
                     f"{e(long_date(members['date']))}, with each member's role, and their party on the date from "
                     "their home council's record where the site has it. Appointed members who aren't councillors "
                     "aren't named.</p><ul>")
        for m in members["members"]:
            who = m["name"] or "Name not shown (not a councillor)"
            bits = [m["role_name"]] + ([m["home"]["name"]] if m.get("home") else []) + \
                   ([f"{m['party']} ({_source(m['party_source'])})"] if m.get("party") else [])
            parts.append(f"<li>{e(who)}: {e(', '.join(bits))}</li>")
        parts.append("</ul>")
    parts.append(_votes_and_meetings(c, "this authority's minutes"))
    return "".join(parts)


def _source(source: str | None) -> str:
    return {"home council": "home council's record", "authority": "the authority's record",
            "as elected": "as elected"}.get(source or "", "recorded")


def council_text(c: dict[str, Any]) -> str:
    if _is_authority(c):
        return authority_text(c)
    parts = [f'<p class="meta"><a href="/councils">Councils</a> · {e(c.get("type_name") or "")} · '
             f'{e(c.get("region_name") or "")}</p>', f"<h1>{e(c['name'])}</h1>", _part_of(c)]
    if not c.get("loaded"):
        parts.append(f"<p>This council isn't covered yet. {e(' '.join(c.get('reasons') or []))} Councils are covered "
                     "when their minutes are published through a system the site can read (Modern.gov, CMIS or CoINS) "
                     "and their site can be read.</p>")
        return "".join(parts) + _landlords(c)
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
    parts.append(_votes_and_meetings(c, "this council's minutes"))
    return "".join(parts)


def _votes_and_meetings(c: dict[str, Any], whose: str) -> str:
    parts = []
    votes = c.get("votes") or []
    parts.append(f"<h2>Named votes ({len(votes):,})</h2>")
    if not votes:
        parts.append(f"<p>No named votes were found in {whose}.</p>")
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


def statements_text(rows: list[dict[str, Any]], here: str) -> str:
    """Statements under the right of reply (decision 22), after the record: each headed "Statement from [name], [date]"
    and followed by the words that say it is the author's own, not the site's. On a council's page they are gathered
    under their own heading, each saying which item it is about when that isn't the page itself."""
    if not rows:
        return ""
    gathered = len({r["page"] for r in rows}) > 1 or rows[0]["page"] != here
    level = 3 if here.startswith("/councils/") else 2
    parts = ["<h2>Statements in their own words</h2>"] if level == 3 else []
    for r in rows:
        about = "" if r["page"] == here else f"<p>About: {_link(r['page'], r.get('about') or r['page'])}</p>"
        words = "".join(f"<p>{e(p.strip())}</p>" for p in re.split(r"\n\s*\n", r["text"]) if p.strip())
        link = f"<p>{_link(r['link'], 'The record they point to')}</p>" if safe_link(r.get("link")) else ""
        parts.append(f'<article class="statement"><h{level}>Statement from {e(r["name"])}, {e(long_date(r["shown_on"]))}'
                     f"</h{level}><p>{e(r['role'])}</p>{about if gathered else ''}{words}{link}"
                     f"<p><em>In their own words. Not checked or endorsed by {SITE}.</em></p></article>")
    return "".join(parts)


def vote_text(v: dict[str, Any]) -> str:
    what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "")
    parts = [f'<p class="meta"><a href="/councils">Councils</a> · {_link(council_path(v["gss"]), v["council"])}</p>',
             f"<h1>{e(v.get('item') or 'Named vote')}</h1>",
             f"<p>{e(what)}, {e(long_date(v.get('date')))}: a named vote{e(vote_on(v.get('question')))}"
             f"{', ' + e(v['outcome']) if v.get('outcome') else ''}.</p>",
             f"<p>{e(_tally(v.get('counts') or {}, v.get('question')))}.</p>",
             (f"<p>The authority's mayor on the date: {e((v.get('control') or 'not recorded').removeprefix('Mayor: '))}"
              " (a strategic authority isn't run by a party). Each member's party is the one their home council "
              "recorded for them at the time, where the site has it.</p>" if v.get("is_authority") else
              f"<p>Party in overall control of the council on the date: {e(v.get('control') or 'not recorded')}. "
              "Each councillor's party is the one the council recorded for them at the time.</p>")]
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
    everything = directory.get("councils") or []
    rows = [r for r in everything if r.get("type") != AUTHORITY]
    authorities = [r for r in everything if r.get("type") == AUTHORITY]
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
    if authorities:
        covered = [r for r in authorities if r.get("loaded")]
        parts.append(f"<h2>Strategic authorities</h2><p>{len(covered):,} of England's {len(authorities):,} strategic "
                     "authorities (combined authorities, combined county authorities and the Greater London "
                     "Authority) are covered: their boards and overview and scrutiny committees. Each is shown with "
                     "its mayor's party, which isn't control of the authority or its councils.</p><ul>")
        for r in authorities:
            if r.get("loaded"):
                parts.append(f"<li>{_link(council_path(r['gss']), r['name'])}: {e(r.get('kind_name') or '')}, "
                             f"{e(_region(r))}. {e(_mayor_now(r))}. {e(month_year(r.get('from')))} to "
                             f"{e(month_year(r.get('to')))}.</li>")
            else:
                parts.append(f"<li>{_link(council_path(r['gss']), r['name'])}: not covered yet. "
                             f"{e(' '.join(r.get('reasons') or []))}</li>")
        parts.append("</ul>")
    return "".join(parts)


def home_text(totals: dict[str, Any], examples: list[str]) -> str:
    return ("<h1>What has your council decided?</h1>"
            "<p>Ask about anything councils across the UK have discussed, decided or voted on at full council and "
            "cabinet. Every point in the briefing cites the council's own minutes.</p>"
            f"<p>The record holds {totals.get('meetings', 0):,} meetings and {totals.get('named_votes', 0):,} named "
            f"votes from {totals.get('loaded', 0):,} of the {totals.get('councils', 0):,} councils in the UK"
            + (f" and {totals['authorities_loaded']:,} of England's {totals['authorities']:,} strategic authorities"
               if totals.get("authorities_loaded") else "")
            + ", since May 2018. Asking a question needs JavaScript; every council's page, with its named votes, can "
            "be read without it, from the <a href=\"/councils\">list of councils</a>.</p>"
            "<h2>For example</h2><ul>" + "".join(f"<li>{e(q)}</li>" for q in examples) + "</ul>"
            '<p><a href="/methodology">How it works</a></p>')
