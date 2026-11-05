"""Write the letters asking councils for permission to read their meetings sites (docs/DECISIONS.md, 2: sites that
forbid or refuse the crawler are asked, not worked around).

    uv run python scripts/outreach.py

writes one letter per council in outreach/<batch>/, ready for Where They Stand's deploy/mail.sh to send from the
charity's Gmail account (docs/HOSTING.md there, "Email from the server"):

    bash /opt/hansardgpt/deploy/mail.sh send /opt/wherecouncilsstand/outreach/2026-11/*.txt

A letter starts with its To: and Subject: lines. Councils are added to LETTERS below with the address each publishes
for its democratic services team (or its general address, asking for it to be passed on, where it publishes none).
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BATCH = "2026-11"
SITE = "https://wherecouncilsstand.com"
SIGNATURE = "Where They Stand\nwheretheystanduk@gmail.com\n" + SITE
USER_AGENT = "Mozilla/5.0 (compatible; WhereCouncilsStand/0.1; +https://github.com/rj-mitchell/wherecouncilsstand)"

# gss: (address, greeting, passed on?) -- passed on: a general address, asked to forward the letter
LETTERS: dict[str, tuple[str, str, bool]] = {
    "E10000012": ("democratic.services@essex.gov.uk", "Democratic Services team", False),
    "E08000030": ("Democraticservices@walsall.gov.uk", "Democratic Services team", False),
    "S12000039": ("committee.admin@west-dunbarton.gov.uk", "Committee Services team", False),
    "E07000131": ("customer.services@harborough.gov.uk", "Democratic Services team", True),
    # Civica-hosted CMIS sites (*.cmis.uk.com, *.cmis-ni.org): addresses found 5 November 2026
    "E08000025": ("democratic.services@birmingham.gov.uk", "Democratic Services team", False),
    "E07000067": ("governance@braintree.gov.uk", "Governance and Members team", False),
    "E10000003": ("democraticservices365@cambridgeshire.gov.uk", "Democratic Services team", False),
    "E07000069": ("Democraticservices@castlepoint.gov.uk", "Democratic Services team", False),
    "E07000071": ("democratic.services@colchester.gov.uk", "Democratic Services team", False),
    "E08000027": ("dudleycouncilplus@dudley.gov.uk", "Democratic Services team", True),
    "E07000244": ("democraticservices@eastsuffolk.gov.uk", "Democratic Services team", False),
    "E07000119": ("democracy@fylde.gov.uk", "Democratic Services team", False),
    "E07000145": ("enquiries@great-yarmouth.gov.uk", "Democratic Services team", True),
    "N09000009": ("committees@midulstercouncil.org", "Democratic Services team", False),
    "S12000019": ("democratic.services@midlothian.gov.uk", "Democratic Services team", False),
    "E10000020": ("councillorsupport@norfolk.gov.uk", "Democratic Services team", False),
    "S12000021": ("committeeservices@north-ayrshire.gov.uk", "Committee Services team", False),
    "S12000050": ("committee@northlan.gov.uk", "Committee Services team", False),
    "S12000048": ("committee@pkc.gov.uk", "Committee Services team", False),
    "S12000038": ("democratic-services@renfrewshire.gov.uk", "Democratic Services team", False),
    # the page shows "democratic.services@", but its link goes to this address
    "E07000039": ("democraticservices@southderbyshire.gov.uk", "Democratic Services team", False),
    "S12000029": ("committees@southlanarkshire.gov.uk", "Committee Services team", False),
    "E07000196": ("info@sstaffs.gov.uk", "Democratic Services team", True),
}

SCOTLAND_NI = ("scotland", "northern_ireland")


def council_rows() -> dict[str, dict]:
    with open(ROOT / "data_static" / "councils.csv", newline="") as f:
        return {r["gss"]: r for r in csv.DictReader(f)}


def short_name(name: str) -> str:
    """"Essex County Council" -> "Essex"; "London Borough of Camden" -> "Camden"."""
    s = re.sub(r"^(?:The |London Borough of |Royal Borough of |City of )", "", name)
    s = re.sub(r"\s+(?:Metropolitan Borough|County Borough|Borough|District|County|City|Town)?\s*Council$", "", s)
    return s.strip() or name


def letter(row: dict, address: str, greeting: str, passed_on: bool) -> str:
    name, short, url = row["name"], short_name(row["name"]), row["modgov_url"]
    hosted = bool(re.search(r"\.cmis(?:-ni)?\.(?:uk\.com|org)\b", url))
    main = "full council and cabinet" if row["nation"] not in SCOTLAND_NI else "full council and its main policy committee"
    parts = []
    if passed_on:
        parts.append(f"Dear colleague,\n\nI couldn't find a direct address for {greeting.replace(' team', '')}, "
                     "so please could you pass this on to them? Thank you.\n")
    parts.append(f"Dear {greeting},\n")
    parts.append(
        f"I'm writing from Where Councils Stand ({SITE}), an independent public website that helps people find out "
        "what their council has discussed, decided and voted on. It reads the minutes councils already publish of "
        f"the meetings of {main}, from May 2018 onwards, and every point it makes links back to the council's own record. "
        "It is a project of Where They Stand, which is applying to register as a charity in England and Wales.\n")
    if hosted:
        parts.append(
            f"Your committee site, {url}, is hosted for you by Civica, and its robots.txt file asks automated tools "
            f"not to read it (as on every committee site Civica hosts that we have looked at). We have respected that and left "
            f"{name} out, rather than work around it. We would like to include {short}, so I'm writing to ask "
            "whether you would be willing to do one of the following:\n\n"
            "1. ask Civica to let our crawler in, by adding these two lines at the top of the site's robots.txt "
            "(everyone else would still be kept out):\n\n"
            "   User-agent: WhereCouncilsStand\n   Allow: /\n\n"
            "2. or reply to confirm you are content for us to read the public meeting pages and published minutes, "
            "and we will ask Civica ourselves.\n")
    else:
        parts.append(
            f"Your committee site, {url}, has a robots.txt file asking automated tools not to read it. We have "
            f"respected that and left {name} out, rather than work around it. We would like to include {short}, so "
            "I'm writing to ask whether you would be willing to do one of the following:\n\n"
            "1. let our crawler in, by adding these two lines at the top of the site's robots.txt (everyone else "
            "would still be kept out):\n\n"
            "   User-agent: WhereCouncilsStand\n   Allow: /\n\n"
            "2. or reply to confirm you are content for us to read the public meeting pages and published minutes.\n")
    parts.append(
        "How it would read your site:\n\n"
        f"- Only public pages: the committee and meeting pages, attendance, and the published minutes of {main}.\n"
        "- At most one request a second, following any Crawl-delay you set. Every page is kept once fetched, so "
        "nothing is read twice.\n"
        "- The first load is roughly 1,000 pages over about half an hour. After that, a daily check for new "
        "meetings, re-reading only meetings from the last four months, because minutes can be corrected when they "
        "are approved.\n"
        f"- It identifies itself as: {USER_AGENT}\n"
        "- Names of people who aren't councillors are removed before anything is shown.\n")
    parts.append(
        f"If you would rather we didn't, we will keep {short} out, and the site will say that the council's site "
        "doesn't allow it. I'm happy to answer any questions, or to change how it reads the site to suit you.\n")
    parts.append(f"Kind regards,\n\n{SIGNATURE}\n")
    subject = f"Permission to read {name}'s published minutes (Where Councils Stand)"
    if passed_on:
        subject = f"For Democratic Services: {subject[0].lower()}{subject[1:]}"
    return f"To: {address}\nSubject: {subject}\n\n" + "\n".join(parts)


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", short_name(name).lower()).strip("-")


def main() -> None:
    rows = council_rows()
    out = ROOT / "outreach" / BATCH
    out.mkdir(parents=True, exist_ok=True)
    for gss, (address, greeting, passed_on) in LETTERS.items():
        row = rows[gss]
        (out / f"{slug(row['name'])}.txt").write_text(letter(row, address, greeting, passed_on))
    print(f"{len(LETTERS)} letters in {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
