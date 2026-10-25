"""Learn what each council's own party codes mean ("L", "WLP", "IND2", "CCH" ...) and write data_static/parties.csv.

For every label in the stored attendance that the rules in parse/parties.py don't recognise, the members recorded
with it are looked up by name in Open Council Data's annual lists of every UK councillor and their party (CSV
downloads, public domain). The party most of them have there gives the label's meaning, which is then mapped to a
code by the same rules. Labels whose members can't be found, or don't agree, are left for a person to decide.

    uv run python scripts/party_labels.py            # after `councils ingest`
"""

from __future__ import annotations

import csv
import io
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import duckdb
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from councils import store  # noqa: E402
from councils.config import STATIC_DIR, load_settings  # noqa: E402
from councils.parse.parties import NAMES, normalise  # noqa: E402
from councils.registry import councils  # noqa: E402

OCD = "https://opencouncildata.co.uk/csv2.php?y={year}"
YEARS = tuple(range(2018, 2027))
# Open Council Data's party names. "Independent / Other" covers both independents and named local groups, so the
# council's own label decides which (see code_for).
OCD_PARTIES = {"Labour Party": "LAB", "Conservative and Unionist": "CON", "Liberal Democrats": "LD",
               "Green Party (E&W)": "GRN", "Reform UK": "REF", "Plaid Cymru": "PC", "UK Independence Party": "UKIP",
               "Liberal Party": "LIB", "The Liberal Party": "LIB", "Your Party": "YP", "Workers Party of Britain": "WPB",
               "Social Democratic Party": "SDP"}
SINGLE_INDEPENDENT = re.compile(r"^(?:i|in|ind|ind ind|na|non[- ]?aligned|other|unaligned|nongp|non-grouped)$", re.I)


def code_for(party: str, label: str) -> str:
    if party in OCD_PARTIES:
        return OCD_PARTIES[party]
    if party == "Independent / Other":
        return "IND" if SINGLE_INDEPENDENT.match(label.strip()) else "LOCAL"
    return normalise(party) or "LOCAL"


def person_key(name: str) -> str:
    n = re.sub(r"\b(?:councillor|cllr|cynghorydd|mr|mrs|ms|miss|dr|mbe|obe|cbe|bem|jp|dl|msc|bsc)\b\.?", " ",
               name.lower())
    words = re.sub(r"[^a-z' -]", " ", n).split()
    return f"{words[0][0]} {words[-1]}" if len(words) >= 2 else (words[0] if words else "")


def council_key(name: str) -> str:
    n = name.lower().replace("&", "and")
    n = re.sub(r"\b(?:london borough of|royal borough of|borough council of|city of|metropolitan borough|county borough|"
               r"borough|district|county|city|council|the)\b", " ", n)
    return re.sub(r"[^a-z]", "", n)


def main() -> None:
    s = load_settings()
    con = duckdb.connect()
    store.parquet.attach(con, s.parquet_dir)
    rows = con.execute("select gss, party_label, name, max(year) from attendance where party = '' "
                       "and party_label <> '' group by all").fetchall()
    # the years each council used each label, to see when a council already has a label for a party
    spans = defaultdict(list)
    for gss, label, first, last in con.execute("select gss, party_label, min(year), max(year) from attendance "
                                               "group by all").fetchall():
        spans[gss].append((label, first, last))
    # (council, label) -> {member: the last year the member was recorded with that label}
    by_label: dict[tuple[str, str], dict[str, int]] = defaultdict(dict)
    for gss, label, name, year in rows:
        if normalise(label, gss):
            continue          # the rules (or an earlier decision) already recognise it
        key = person_key(name)
        by_label[(gss, label)][key] = max(year, by_label[(gss, label)].get(key, 0))

    # (council key, person key) -> {year: party name}
    parties: dict[tuple[str, str], dict[int, str]] = defaultdict(dict)
    with httpx.Client(timeout=120, follow_redirects=True) as http:
        for year in YEARS:
            r = http.get(OCD.format(year=year))
            if r.status_code != 200:
                continue
            for row in csv.DictReader(io.StringIO(r.text)):
                parties[(council_key(row["Council"]), person_key(row["Councillor Name"]))][year] = row["Party Name"]

    out = []
    for (gss, label), people in sorted(by_label.items()):
        ck = council_key(councils()[gss].name)
        votes = Counter()
        for p, last_used in people.items():
            if (ck, p) in parties:
                # the party listed nearest the label's last use: a member who changed party ("RUK" since 2024,
                # Conservative before) is read as at the time
                history = parties[(ck, p)]
                votes[history[min(history, key=lambda y: (abs(y - last_used), -y))]] += 1
        found = sum(votes.values())
        if not found:
            print(f"{gss} {label!r}: none of {len(people)} members found", file=sys.stderr)
            continue
        # members agree if their parties map to one code: "Nork Residents' Association" and "Independent / Other"
        # under the label "RA" are both a local group
        codes = Counter()
        for name, k in votes.items():
            codes[code_for(name, label)] += k
        code, n = codes.most_common(1)[0]
        party = max((name for name in votes if code_for(name, label) == code), key=votes.get)
        if n * 3 < found * 2:  # under two-thirds agree
            print(f"{gss} {label!r}: members disagree {dict(votes)}", file=sys.stderr)
            continue
        if n < 2:            # one member's party history is too thin to read a council's code from
            print(f"{gss} {label!r}: only one member found ({party})", file=sys.stderr)
            continue
        years = next((f, la) for lab, f, la in spans[gss] if lab == label)
        rival = [lab for lab, f, la in spans[gss] if lab != label and normalise(lab, gss) == code
                 and code not in ("IND", "LOCAL") and f <= years[1] and la >= years[0]]
        if rival:
            # the council already had a label for that party at the time ("CON" beside "IG"): the members were
            # probably listed under their former party, so a person decides
            print(f"{gss} {label!r}: {party} by Open Council Data, but {rival[0]!r} was in use", file=sys.stderr)
            continue
        out.append({"gss": gss, "label": label, "code": code, "party_name": party,
                    "evidence": f"{n} of {len(people)} members recorded as {party} by Open Council Data"
                    if votes[party] == n else
                    f"{n} of {len(people)} members recorded by Open Council Data as {NAMES[code].lower()}: "
                    + ", ".join(f"{k} {name}" for name, k in votes.most_common() if code_for(name, label) == code)})

    path = STATIC_DIR / "parties.csv"
    existing = []
    if path.exists():
        with open(path, encoding="utf-8") as fh:
            existing = [r for r in csv.DictReader(fh) if (r["gss"], r["label"]) not in {(o["gss"], o["label"]) for o in out}]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["gss", "label", "code", "party_name", "evidence"])
        w.writeheader()
        w.writerows(sorted(existing + out, key=lambda r: (r["gss"], r["label"])))
    print(path, len(out), "labels mapped")


if __name__ == "__main__":
    main()
