"""Build data_static/councils.csv: every principal council in England and Wales, and its Modern.gov site if it has one.

Sources (fetched fresh each run):
  * England: MHCLG's local-authority register on planning.data.gov.uk (OGL), current entries only, with type, GSS code
    and region. Combined authorities are left out.
  * Wales: mySociety MapIt's unitary authorities (GSS codes, ONS names).
  * Modern.gov sites: Local Democracy UK's council list (CC BY 4.0), then a probe of the usual host names
    (democracy., moderngov., modgov., committees., ...) on each remaining council's own domain.

Each site is checked with one GetCommittees request. "blocked" means the site refused automated requests from where
this ran, and "unreachable" that the connection failed; either may work from elsewhere or later.

    uv run python scripts/build_councils.py
"""

from __future__ import annotations

import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from urllib.parse import urlparse

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from councils.config import STATIC_DIR, load_settings  # noqa: E402
from councils.sources.modgov import probe  # noqa: E402

REGISTER = "https://files.planning.data.gov.uk/dataset/local-authority.csv"
MAPIT_UTA = "https://mapit.mysociety.org/areas/UTA"
LOCAL_DEMOCRACY = "https://www.local-democracy.uk/api/councils"

TYPES = {"CTY": "county", "NMD": "district", "UA": "unitary", "MD": "metropolitan", "LBO": "london_borough",
         "CC": "city_of_london", "SRA": "isles_of_scilly"}
HOST_PREFIXES = ["democracy", "moderngov", "modgov", "committees", "democratic", "meetings", "councillors",
                 "decisionmaking", "democracy.cityof", "cmttpublic", "mgov", "moderngovwebpublic", "modgov.lb",
                 "committeemeetings", "councilmeetings", "democraticservices", "minutes", "cabinet"]
FIELDS = ["gss", "reference", "name", "nation", "type", "region", "website", "modgov_url", "modgov_status",
          "modgov_source"]


def norm(name: str) -> str:
    """A key for matching council names across sources."""
    n = name.lower().replace("&", "and").replace("-", " ").replace("'", "").replace(".", "")
    n = re.sub(r"\b(borough council of|london borough of|royal borough of|borough of|city of|county of|metropolitan borough council|"
               r"metropolitan district council|metropolitan borough|city and district council|county borough council|"
               r"borough council|district council|county council|city council|council|the|cyngor|mbc)\b", " ", n)
    n = re.sub(r"\s+", " ", n).strip()
    return re.sub(r" district$", "", n)


ALIASES = {  # Local Democracy UK name key -> register name key, where they differ
    "kingston upon thames": "kingston upon thames",
    "rhondda cynon taf": "rhondda cynon taf",
    "newport": "newport",
    "isle of anglesey": "isle of anglesey",
    "bcp": "bournemouth christchurch and poole",
    "herefordshire": "herefordshire",
    "city of london corporation": "london",
    "london corporation": "london",
    "windsor and maidenhead": "windsor and maidenhead",
    "york": "york",
}


def england(http: httpx.Client) -> list[dict]:
    rows = list(csv.DictReader(http.get(REGISTER).text.splitlines()))
    out = []
    for r in rows:
        if r.get("end-date") or r.get("local-authority-type") not in TYPES:
            continue
        out.append({"gss": r["statistical-geography"], "reference": r["reference"], "name": r["name"],
                    "nation": "england", "type": TYPES[r["local-authority-type"]], "region": (r.get("region") or "").split(":")[-1],  # "statistical-geography:E12000006" in a few
                    "website": r.get("website", "")})
    return out


def wales(http: httpx.Client) -> list[dict]:
    areas = http.get(MAPIT_UTA).json().values()
    return [{"gss": a["codes"]["gss"], "reference": a["codes"]["gss"], "name": a["name"], "nation": "wales",
             "type": "unitary", "region": "wales", "website": ""}
            for a in areas if a.get("country") == "W"]


def candidate_hosts(website: str, name: str) -> list[str]:
    host = urlparse(website if "://" in website else f"https://{website}").hostname or ""
    domain = host.removeprefix("www.")
    out = [f"https://{p}.{domain}" for p in HOST_PREFIXES] if domain else []
    slug = re.sub(r"[^a-z]", "", norm(name))
    if slug:
        out.append(f"https://{slug}.moderngov.co.uk")
    return out


def main() -> None:
    s = load_settings()
    ua = {"User-Agent": s.modgov.get("user_agent", "WhereCouncilsStand")}
    with httpx.Client(headers=ua, timeout=60, follow_redirects=True) as http:
        councils = england(http) + wales(http)
        known = http.get(LOCAL_DEMOCRACY).json()["councils"]

    by_key = {norm(c["name"]): c for c in councils}
    for k in known:
        names = [k["name"]]
        if " and " in k["name"] and k["name"].endswith("Councils"):  # one site for two councils
            a, b = k["name"].removesuffix(" Councils").split(" and ", 1)
            suffix = " District" if "District" in b else ""
            names = [a + suffix, b]
        for name in names:
            key = norm(name)
            key = ALIASES.get(key, key)
            c = by_key.get(key)
            if c is None:
                print(f"unmatched in Local Democracy UK: {name}", file=sys.stderr)
                continue
            c["modgov_url"], c["modgov_source"] = k["baseUrl"].rstrip("/"), "local-democracy-uk"

    def check(c: dict) -> dict:
        if c.get("modgov_url"):
            status, _ = probe(s, c["gss"], c["modgov_url"])
            c["modgov_status"] = status
            return c
        for url in candidate_hosts(c.get("website", ""), c["name"]):
            status, _ = probe(s, c["gss"], url)
            if status in ("ok", "blocked"):  # an unreachable guess is just a host that doesn't exist
                c.update(modgov_url=url, modgov_status=status, modgov_source="probed")
                return c
        c.update(modgov_url="", modgov_status="none", modgov_source="")
        return c

    with ThreadPoolExecutor(12) as ex:
        councils = list(ex.map(check, councils))

    councils.sort(key=lambda c: (c["nation"], c["name"]))
    path = STATIC_DIR / "councils.csv"
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(councils)
    counts: dict[tuple[str, str], int] = {}
    for c in councils:
        counts[(c["nation"], c["modgov_status"])] = counts.get((c["nation"], c["modgov_status"]), 0) + 1
    print(path, len(councils), dict(sorted(counts.items())))


if __name__ == "__main__":
    main()
