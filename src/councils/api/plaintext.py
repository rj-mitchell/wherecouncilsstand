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

from wts_core.dates import long_date
from wts_core.replies import safe_link

from councils import sisters
from councils.api import titles

SITE = "Where Councils Stand"
LATEST = 25          # named votes set out in full on a council's page, as its app does (council.tsx); the rest by year
KIND_LABEL = {"council": "Full council", "cabinet": "Cabinet", "policy": "Policy committee", "board": "Board",
              "mayor": "Mayor’s decisions", "scrutiny": "Overview and scrutiny"}
AUTHORITY = "strategic_authority"
SIDES = ("for", "against", "abstain")
# a Scottish division is between a motion and an amendment: each side is for something
MOTION_OR_AMENDMENT = "motion or amendment"

_APP = '<div id="app"></div>'
_NEEDS_JS = re.compile(r"\s*<noscript><p>This page needs JavaScript\..*?</noscript>", re.S)
_HEAD_TAGS = re.compile(
    r'\s*<(?:title>[^<]*</title|meta name="(?:description|robots|twitter:card)"[^>]*|link rel="canonical"[^>]*|'
    r'meta property="og:(?:title|description|url|type|site_name|locale)"[^>]*)>', re.I)


def month_year(iso: str | None) -> str:
    return date.fromisoformat(iso[:10]).strftime("%B %Y") if iso else ""


def council_path(gss: str) -> str:
    return f"/councils/{quote(gss)}"


def vote_path(vote_id: str) -> str:
    return f"/votes/{quote(vote_id, safe=':')}"


# The page shell

def with_text(page: str, fragment: str | None) -> str:
    """The page with ``fragment`` in its app root (replaced by the app when it starts), and without its "needs
    JavaScript" note, which is no longer true."""
    if not fragment or _APP not in page:
        return page
    return _NEEDS_JS.sub("", page.replace(_APP, f'<div id="app">{fragment}</div>', 1), count=1)


def page_with_meta(page: str, *, title: str, description: str, url: str, noindex: bool = False,
                   data: dict[str, Any] | list[dict[str, Any]] | None = None) -> str:
    """The page with its own title, description (cut at a word to ``DESCRIPTION_MAX`` characters), canonical
    address and link-preview text, and ``data`` (schema.org structured data, for search engines, one script for
    each) if given. The link-preview image stays the family kit's card, from the page's head."""
    description = titles.shorten(description, titles.DESCRIPTION_MAX)
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
    for one in ([data] if isinstance(data, dict) else data or []):  # "</" escaped: the data cannot end the script
        tags.append('<script type="application/ld+json">' + json.dumps(one).replace("</", "<\\/") + "</script>")
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


# A council

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


def _fits(*candidates: str) -> str:
    """The first of ``candidates`` short enough for a page's description, or the last cut to fit."""
    for text in candidates:
        if len(text) <= titles.DESCRIPTION_MAX:
            return text
    return titles.shorten(candidates[-1], titles.DESCRIPTION_MAX)


def authority_description(c: dict[str, Any]) -> str:
    what = f"{c['name']} ({c.get('kind_name') or 'strategic authority'}, {_region(c) or 'England'})"
    if not c.get("loaded"):
        return _fits(f"{what}: not covered yet. " + " ".join(c.get("reasons") or []), f"{c['name']}: not covered yet.")
    votes = _plural(c.get("named_votes") or 0, "named vote")
    when = f"{month_year(c.get('from'))} to {month_year(c.get('to'))}"
    meetings = _plural(c.get("meetings") or 0, "board and scrutiny meeting")
    return _fits(f"{what}: {votes}, with each member’s role and party, and {meetings} from {when}. {_mayor_now(c)}.",
                 f"{c['name']}: {votes}, with each member’s role and party, and {meetings} from {when}. "
                 f"{_mayor_now(c)}.",
                 f"{c['name']}: {votes} and {meetings} from {when}. {_mayor_now(c)}.")


def council_description(c: dict[str, Any]) -> str:
    if _is_authority(c):
        return authority_description(c)
    if not c.get("loaded"):
        return _fits(f"{c['name']} ({c.get('type_name') or 'council'}, {c.get('region_name') or c.get('nation') or 'UK'}): "
                     "not covered yet. " + " ".join(c.get("reasons") or []), f"{c['name']}: not covered yet.")
    control = (c.get("control") or {}).get("name")
    votes = _plural(c.get("named_votes") or 0, "named vote")
    when = f"{month_year(c.get('from'))} to {month_year(c.get('to'))}"
    meetings = _plural(c.get("meetings") or 0, "full council and cabinet meeting")
    in_control = f" In overall control: {control}." if control else ""
    return _fits(f"{c['name']}: {votes}, with each councillor’s party on the date, and {meetings} from {when}."
                 + in_control,
                 f"{c['name']}: {votes}, with each councillor’s party, and {meetings} from {when}." + in_control,
                 f"{c['name']}: {votes} and {_plural(c.get('meetings') or 0, 'meeting')} from {when}." + in_control)


def council_data(c: dict[str, Any], url: str, base: str) -> list[dict[str, Any]]:
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
    return [{"@context": "https://schema.org", "@type": "WebPage", "name": c["name"], "url": url,
             "description": council_description(c), "inLanguage": "en-GB",
             "isPartOf": {"@type": "WebSite", "name": SITE, "url": base + "/"}, "about": org},
            breadcrumbs(base, [("Councils", "/councils"), (c["name"], council_path(c["gss"]))])]


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
    return ("<h2>Mayors</h2><ul>" + items + "</ul><p>Each with the party they were elected for. A mayor’s party is "
            "shown in place of a party in control: a strategic authority isn’t run by a party.</p>")


def authority_text(c: dict[str, Any]) -> str:
    parts = ['<p class="meta"><a href="/councils">All councils</a></p>',
             f"<h1>{e(c['name'])}</h1>", f'<p class="meta">Strategic authority, {e(_region(c))}</p>',
             f"<p>{e(c.get('kind_name') or '')}"
             + (f"; {e(c['category_name'][0].lower() + c['category_name'][1:])}" if c.get("category_name") else "")
             + (f". Created {e(c['created'])}" if c.get("created") else "") + ".</p>",
             _constituents(c)]
    if not c.get("loaded"):
        parts.append(f"<p>This strategic authority isn’t covered yet. {e(' '.join(c.get('reasons') or []))}</p>")
        return "".join(parts) + _mayors(c) + mps_text(c)
    parts.append(f"<p>Board, and overview and scrutiny committee meetings from {e(month_year(c.get('from')))} to "
                 f"{e(month_year(c.get('to')))}, read from the authority’s {_link(c.get('site'), 'own record')}.</p>")
    control = c.get("control") or {}
    mayor = (f"{control['mayor']} ({control['name'].removeprefix('Mayor: ')})"
             + (f", since {long_date(control['since'])}" if control.get("since") else "")
             if control.get("mayor") else "No mayor, so no single party")
    parts.append(_facts([
        ("Mayor", mayor),
        ("Meetings", f"{c.get('meetings') or 0:,}: {c.get('board_meetings') or 0:,} board, "
                     f"{c.get('scrutiny_meetings') or 0:,} overview and scrutiny"
                     + (f", {c['mayor_meetings']:,} of the mayor’s decisions" if c.get("mayor_meetings") else "")),
        ("Named votes", f"{c.get('named_votes') or 0:,} recorded in the minutes")]))
    parts.append(_mayors(c))
    members = c.get("members")
    if members:
        parts.append(f"<h2>Members</h2><p>Listed at the {e(members['committee'])} meeting of "
                     f"{e(long_date(members['date']))}, with each member’s role, and their party on the date from "
                     "their home council’s record where the site has it. Appointed members who aren’t councillors "
                     "aren’t named.</p><ul>")
        for m in members["members"]:
            who = m["name"] or "Name not shown (not a councillor)"
            bits = [m["role_name"]] + ([m["home"]["name"]] if m.get("home") else []) + \
                   ([f"{m['party']} ({_source(m['party_source'])})"] if m.get("party") else [])
            parts.append(f"<li>{e(who)}: {e(', '.join(bits))}</li>")
        parts.append("</ul>")
    parts.append(mps_text(c))
    parts.append(_votes_and_meetings(c, "this authority’s minutes"))
    return "".join(parts)


def _facts(rows: list[tuple[str, str]]) -> str:
    """A council's or an authority's figures, as the page shows them once its script runs (council.tsx)."""
    return '<dl class="facts">' + "".join(f"<dt>{e(t)}</dt><dd>{e(v)}</dd>" for t, v in rows) + "</dl>"


def _source(source: str | None) -> str:
    return {"home council": "home council’s record", "authority": "the authority’s record",
            "as elected": "as elected"}.get(source or "", "recorded")


def council_text(c: dict[str, Any]) -> str:
    if _is_authority(c):
        return authority_text(c)
    parts = ['<p class="meta"><a href="/councils">All councils</a></p>', f"<h1>{e(c['name'])}</h1>",
             f'<p class="meta">{e(c.get("type_name") or "")}, {e(c.get("region_name") or "")}</p>', _part_of(c)]
    if not c.get("loaded"):
        parts.append(f"<p>This council isn’t covered yet. {e(' '.join(c.get('reasons') or []))} Councils are covered "
                     "when their minutes are published through a system the site can read (Modern.gov, CMIS or CoINS) "
                     "and their site can be read.</p>")
        return "".join(parts) + _landlords(c) + mps_text(c)
    parts.append(f"<p>Full council and cabinet meetings from {e(month_year(c.get('from')))} to "
                 f"{e(month_year(c.get('to')))}, read from the council’s {_link(c.get('site'), 'own record')}.</p>")
    control = c.get("control") or {}
    parts.append(_facts([
        ("In overall control", (control.get("name") or "Not recorded")
         + (f", as listed on {long_date(control['as_of'])}" if control.get("as_of") else "")),
        ("Meetings", f"{c.get('meetings') or 0:,}: {c.get('council_meetings') or 0:,} full council, "
                     f"{c.get('cabinet_meetings') or 0:,} cabinet"
                     + (f", {c['policy_meetings']:,} policy committee" if c.get("policy_meetings") else "")),
        ("Named votes", f"{c.get('named_votes') or 0:,} recorded in the minutes")]))
    parts.append(_landlords(c))
    seats = c.get("seats")
    if seats:
        parts.append(f"<h2>Members by party</h2><p>The {seats['total']:,} councillors listed at the full council "
                     f"meeting of {e(long_date(seats['date']))}, with their party as the council recorded it.</p><ul>"
                     + "".join(f"<li>{e(p['name'])}: {p['members']:,}</li>" for p in seats["parties"]) + "</ul>")
    if c.get("control_timeline"):
        parts.append("<h2>Party in overall control</h2><ul>" + "".join(
            f"<li>From {e(month_year(t['from']))}: {e(t['name'])}</li>" for t in c["control_timeline"]) + "</ul>")
    parts.append(mps_text(c))
    parts.append(_votes_and_meetings(c, "this council’s minutes"))
    return "".join(parts)


def _short_tally(v: dict[str, Any]) -> str:
    """"carried, for 30, against 12": a vote's result in a list of links."""
    return f"{v['outcome'] + ', ' if titles.outcome(v) else ''}{_tally(v.get('counts') or {}, v.get('question'))}".lower()


def by_year(votes: list[dict[str, Any]]) -> list[tuple[str, list[dict[str, Any]]]]:
    """Named votes grouped by the year of their meeting, newest first (as they come)."""
    years: dict[str, list[dict[str, Any]]] = {}
    for v in votes:
        years.setdefault((v.get("date") or "")[:4] or "Undated", []).append(v)
    return list(years.items())


def _vote_links(votes: list[dict[str, Any]]) -> str:
    return '<ul class="vote-links">' + "".join(
        f"<li>{_link(vote_path(v['vote_id']), v.get('heading') or v.get('item') or 'Named vote')}: "
        f"{e(KIND_LABEL.get(v.get('kind', ''), v.get('committee') or ''))}, {e(long_date(v.get('date')))}; "
        f"{e(_short_tally(v))}.</li>" for v in votes) + "</ul>"


def budget_votes(votes: list[dict[str, Any]]) -> str:
    """The named votes on items about the budget, council tax or a precept, year by year: where readers searching
    for a council's budget or council tax should land."""
    budget = [v for v in votes if v.get("budget")]
    if not budget:
        return ""
    return ("<h2>Budget and council tax votes, year by year</h2><p>Named votes on agenda items about the budget, "
            "council tax or a precept.</p>"
            + "".join(f"<h3>{e(year)}</h3>{_vote_links(vs)}" for year, vs in by_year(budget)))


def all_votes(votes: list[dict[str, Any]]) -> str:
    """Every named vote, a list for each year (closed but for the latest), so that each can be reached by a link."""
    if not votes:
        return ""
    return ("<h2>Every named vote, by year</h2>" + "".join(
        f'<details class="vote-year"{" open" if i == 0 else ""}><summary>{e(year)}: '
        f"{_plural(len(vs), 'named vote')}</summary>{_vote_links(vs)}</details>"
        for i, (year, vs) in enumerate(by_year(votes))))


def _votes_and_meetings(c: dict[str, Any], whose: str) -> str:
    parts = []
    votes = c.get("votes") or []
    parts.append(budget_votes(votes))
    parts.append(f"<h2>Named votes ({len(votes):,})</h2>")
    if not votes:
        parts.append(f"<p>No named votes were found in {whose}.</p>")
    else:
        if len(votes) > LATEST:
            parts.append(f"<p>The latest {LATEST}, then every named vote by year.</p>")
        parts.append("<ol>")
        for v in votes[:LATEST]:
            what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "")
            parts.append(f"<li>{_link(vote_path(v['vote_id']), v.get('heading') or v.get('item') or 'Named vote')}: "
                         f"{e(what)}, {e(long_date(v.get('date')))}, a named vote{e(vote_on(v.get('question')))}"
                         f"{', ' + e(v['outcome']) if v.get('outcome') else ''}. "
                         f"{e(_tally(v.get('counts') or {}, v.get('question')))}.</li>")
        parts.append("</ol>")
        parts.append(all_votes(votes))
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


def mps_text(c: dict[str, Any]) -> str:
    """The MPs whose seats overlap the council (decision 31), each linked to their page on Where MPs Stand, under
    that site's name and its spine from the family kit, so the reader knows they are going to another site. As the
    app draws it (council.tsx, Seats)."""
    m = c.get("mps") or {}
    seats = m.get("seats") or []
    if not seats:
        return ""
    whose = "authority" if _is_authority(c) else "council"
    items = []
    for s in seats:
        mp = s.get("mp")
        if mp:
            items.append(f"<li>{_link(mp['url'], mp['name'])}, {e(mp['party'] + ', ' if mp.get('party') else '')}"
                         f"MP for {e(s['name'])}</li>")
        else:
            items.append(f"<li>{e(s['name'])}: no MP listed on {e(sisters.MPS_NAME)}</li>")
    return (f'<section class="seats" aria-labelledby="mps-heading"><h2 id="mps-heading">MPs whose seats overlap this '
            f'{whose}</h2><div class="sister"><span class="spine" aria-hidden="true">{sisters.spine("mps")}</span><div><p class="sister-name">On '
            f'{e(sisters.MPS_NAME)}</p><p class="small">{seats_note(len(seats), whose)}</p>'
            f'<ul class="seat-list">{"".join(items)}</ul></div></div></section>')


def seats_note(n: int, whose: str) -> str:
    """What the list of MPs is, and where it comes from (council.tsx says the same)."""
    seat = "constituency" if n == 1 else f"{n:,} Westminster constituencies"
    return (f"The {'Westminster ' if n == 1 else ''}{seat} with at least part of a ward in this {whose}’s area, "
            "from the ONS lookup of wards to constituencies (July 2024 boundaries), each with the MP "
            f"{e(sisters.MPS_NAME)} lists for it.")


# A named vote

def vote_title(v: dict[str, Any]) -> str:
    """A vote's page title (api/titles.py; the app sets the same one): "Amendment 7, lost 10–19: General Fund
    Budget… – Rushmoor, 26 Feb 2026"."""
    return v.get("title") or f"{v.get('item') or 'Named vote'}, {v['council']}"


def vote_description(v: dict[str, Any]) -> str:
    if v.get("description"):
        return v["description"]
    what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "A meeting")
    return titles.shorten(f"{v['council']}, {what.lower() if what in KIND_LABEL.values() else what}, "
                          f"{long_date(v.get('date'))}: a named vote{vote_on(v.get('question'))}"
                          f"{', ' + v['outcome'] if v.get('outcome') else ''}. "
                          f"{_tally(v.get('counts') or {}, v.get('question'))}, with each councillor’s party on the "
                          "date.", titles.DESCRIPTION_MAX)


def breadcrumbs(base: str, trail: list[tuple[str, str]]) -> dict[str, Any]:
    """schema.org: where a page sits (Councils › a council › a named vote)."""
    return {"@context": "https://schema.org", "@type": "BreadcrumbList",
            "itemListElement": [{"@type": "ListItem", "position": n, "name": name, "item": base + path}
                                for n, (name, path) in enumerate(trail, 1)]}


def vote_data(v: dict[str, Any], url: str, base: str) -> list[dict[str, Any]]:
    meeting = f"{KIND_LABEL.get(v.get('kind', ''), v.get('committee') or 'Meeting')}, {long_date(v.get('date'))}"
    page = {"@context": "https://schema.org", "@type": "WebPage", "name": vote_title(v), "url": url,
            "description": vote_description(v), "inLanguage": "en-GB",
            "isPartOf": {"@type": "WebSite", "name": SITE, "url": base + "/"},
            "about": [{"@type": "GovernmentOrganization", "name": v["council"],
                       "url": base + council_path(v["gss"])},
                      {"@type": "Event", "name": f"{v['council']}: {meeting}", "startDate": v.get("date"),
                       **({"url": v["url"]} if v.get("url") else {})}]}
    return [page, breadcrumbs(base, [("Councils", "/councils"), (v["council"], council_path(v["gss"])),
                                     (v.get("heading") or v.get("item") or "Named vote", vote_path(v["vote_id"]))])]


CORRECTIONS_LOG = '<div id="corrections-log">'
NOTHING_CORRECTED = "Nothing has been corrected or withdrawn so far."


def corrections_text(entries: list[dict[str, Any]]) -> str:
    """The corrections log (the impartiality policy, 7.1), newest first: for each entry its date, what it was (a
    briefing withdrawn, or a correction) and the public note. No link: which page was put right is for the note
    to say, and a saved briefing is listed nowhere."""
    if not entries:
        return f"<p>{e(NOTHING_CORRECTED)}</p>"
    items = []
    for c in entries:
        note = f"<p>{e(c['note'])}</p>" if c.get("note") else ""
        items.append(f'<li><h3>{e(c["heading"])}</h3><p class="corrections-when"><time datetime="{e(c["date"])}">'
                     f'{e(long_date(c["date"]))}</time></p>{note}</li>')
    return f'<ol class="corrections-log">{"".join(items)}</ol>'


def with_corrections(page: str, entries: list[dict[str, Any]]) -> str:
    """The corrections page with its log in place (web/corrections.html keeps a line there that says the log
    could not be shown, for when it can't)."""
    start = page.find(CORRECTIONS_LOG)
    end = page.find("</div>", start)
    if start < 0 or end < 0:
        return page
    return page[:start] + CORRECTIONS_LOG + corrections_text(entries) + page[end:]


def hidden_text(heading: str, instead: str) -> str:
    """What stands in place of a page that is hidden while a concern about it is decided (the impartiality policy,
    7.3): the kind of page it is, and the note. Nothing of the record."""
    return (f'<p class="meta"><a href="/councils">Councils</a></p><h1>{e(heading)}</h1>'
            f'<p class="notice">{e(instead)}</p>')


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
        # data-nosnippet: a search engine may show the page, but never quotes a statement as the site's own words
        parts.append(f'<article class="statement" data-nosnippet><h{level}>Statement from {e(r["name"])}, {e(long_date(r["shown_on"]))}'
                     f"</h{level}><p>{e(r['role'])}</p>{about if gathered else ''}{words}{link}"
                     f"<p><em>In their own words. Not checked or endorsed by {SITE}.</em></p></article>")
    return "".join(parts)


def vote_text(v: dict[str, Any]) -> str:
    what = KIND_LABEL.get(v.get("kind", ""), v.get("committee") or "")
    parts = [f'<p class="meta">{_link(council_path(v["gss"]), v["council"])}</p>',
             f"<h1>{e(v.get('heading') or v.get('item') or 'Named vote')}</h1>",
             f"<p>{e(what)}, {e(long_date(v.get('date')))}: a named vote{e(vote_on(v.get('question')))}"
             f"{', ' + e(v['outcome']) if v.get('outcome') else ''}.</p>",
             f"<p>{e(_tally(v.get('counts') or {}, v.get('question')))}.</p>",
             (f"<p>The authority’s mayor on the date: {e((v.get('control') or 'not recorded').removeprefix('Mayor: '))}"
              " (a strategic authority isn’t run by a party). Each member’s party is the one their home council "
              "recorded for them at the time, where the site has it.</p>" if v.get("is_authority") else
              f"<p>Party in overall control of the council on the date: {e(v.get('control') or 'not recorded')}. "
              "Each councillor’s party is the one the council recorded for them at the time.</p>")]
    if v.get("partial"):
        parts.append("<p>Only one side of this vote could be read from the minutes. The others may be recorded in a "
                     "form that couldn’t be read, or not at all.</p>")
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
    parts.append(f"<p>{_link(v.get('url'), "The item in the council’s own minutes")}. Names are matched to the "
                 "councillors listed at the meeting. The names of people who aren’t councillors are removed.</p>")
    parts.append(nearby_text(v))
    return "".join(parts)


def nearby_text(v: dict[str, Any]) -> str:
    """Links from a vote's page to the council's other named votes near it: on the same item, at the same meeting,
    and the one before and after it (as the app shows them, vote.tsx)."""
    parts = []
    if v.get("siblings"):
        parts.append("<h2>Other named votes on this item</h2>" + _vote_links(v["siblings"]))
    if v.get("same_meeting"):
        parts.append("<h2>Other named votes at this meeting</h2>" + _vote_links(v["same_meeting"]))
    steps = [(f"Earlier named vote at {v['council']}", v.get("earlier")),
             (f"Later named vote at {v['council']}", v.get("later"))]
    if any(x for _, x in steps):
        parts.append('<nav class="vote-steps" aria-label="Named votes before and after this one"><ul>' + "".join(
            f"<li>{e(what)}: {_link(vote_path(x['vote_id']), x.get('heading') or 'Named vote')}, "
            f"{e(long_date(x.get('date')))}</li>" for what, x in steps if x) + "</ul></nav>")
    return "".join(parts)


# The list of councils, and the home page

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
        parts.append(f"<h2>Strategic authorities</h2><p>{len(covered):,} of England’s {len(authorities):,} strategic "
                     "authorities (combined authorities, combined county authorities and the Greater London "
                     "Authority) are covered: their boards and overview and scrutiny committees. Each is shown with "
                     "its mayor’s party, which isn’t control of the authority or its councils.</p><ul>")
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


LATEST_VOTES_ROOT = '<div id="latest-votes"></div>'


def latest_result(v: dict[str, Any]) -> str:
    """A vote's result and counts as the record has them: "Lost. For 10, Against 19, Abstained 2."; where only one
    side could be read, that side alone, said so."""
    said = titles.outcome(v)
    counts, question = v.get("counts") or {}, v.get("question")
    lead = f"{said.capitalize()}. " if said else ""
    if v.get("partial"):
        read = ", ".join(f"{side_label(s, question)} {counts[s]}" for s in SIDES if counts.get(s))
        return f"{lead}Only one side could be read from the minutes: {read}."
    return f"{lead}{_tally(counts, question)}."


def latest_votes_text(votes: list[dict[str, Any]]) -> str:
    """The home page's latest named votes (decision 32): each vote's heading (as its own page has it) linking to
    its page, its council, its date in full, and its result and counts."""
    if not votes:
        return ""
    items = "".join(
        f'<li><a href="{e(vote_path(v["vote_id"]))}">{e(v.get("heading") or v.get("item") or "Named vote")}</a>'
        f'<p class="meta">{e(v["council"])}, <time datetime="{e(v.get("date") or "")}">{e(long_date(v.get("date")))}'
        f'</time></p><p class="latest-result">{e(latest_result(v))}</p></li>' for v in votes)
    return ('<section class="latest-votes" aria-labelledby="latest-votes-heading">'
            '<h2 id="latest-votes-heading">Latest named votes</h2>'
            f"<p>The {_plural(len(votes), 'newest named vote')} in the record, from every council and strategic "
            "authority the site reads, newest first. Each links to the vote’s own page, with how each councillor "
            f'voted and their party on the date.</p><ol class="latest-list">{items}</ol>'
            '<p><a href="/councils">Every council’s named votes, from the list of councils</a></p></section>')


def with_latest_votes(page: str, votes: list[dict[str, Any]]) -> str:
    """The home page with its latest named votes in place, outside the app's root, so the app leaves them as they
    are (web/index.html keeps an empty place for them)."""
    if LATEST_VOTES_ROOT not in page:
        return page
    return page.replace(LATEST_VOTES_ROOT, f'<div id="latest-votes">{latest_votes_text(votes)}</div>', 1)


def briefing_title(at: str | None) -> str:
    """A saved briefing's title, made by the site: never the reader's question, which can say anything at all and
    would otherwise stand as the site's own headline in a browser tab, a search result or a link's preview."""
    return f"Briefing from council minutes, {long_date(at[:10])}" if at else "Briefing from council minutes"


BRIEFING_DESCRIPTION = ("A briefing written by AI from councils’ own minutes, in answer to a question asked by a reader. "
                        "Every point cites the minutes it comes from.")


def home_text(totals: dict[str, Any], examples: list[str]) -> str:
    return ("<h1>Council decisions, from the minutes</h1>"
            "<p>Ask about anything councils across the UK have discussed, decided or voted on at full council and "
            "cabinet. Briefings are written by AI from the official record only, and every citation is checked. "
            '<a href="/methodology#ai-briefings">How the briefings are checked</a></p>'
            f"<p>The record holds {totals.get('meetings', 0):,} meetings and {totals.get('named_votes', 0):,} named "
            f"votes from {totals.get('loaded', 0):,} of the {totals.get('councils', 0):,} councils in the UK"
            + (f" and {totals['authorities_loaded']:,} of England’s {totals['authorities']:,} strategic authorities"
               if totals.get("authorities_loaded") else "")
            + ", since May 2018. Asking a question needs JavaScript; every council’s page, with its named votes, can "
            "be read without it, from the <a href=\"/councils\">list of councils</a>.</p>"
            "<h2>Questions to try</h2><ul>" + "".join(f"<li>{e(q)}</li>" for q in examples) + "</ul>"
            '<p><a href="/methodology">Methodology</a></p>')
