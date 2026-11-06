"""The letters in outreach/ and scripts/outreach.py, which writes them.

The repository is public and Cloudflare keeps the server's address hidden, so no letter carries it: a letter that
needs it says SERVER_ADDRESS instead, and the address goes in only in the copy sent (outreach/README.md).
"""

import importlib.util
import ipaddress
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
IPV4 = re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])")
# Addresses that are fine to show: the documentation ranges (RFC 5737) and loopback
ALLOWED = [ipaddress.ip_network(n) for n in ("192.0.2.0/24", "198.51.100.0/24", "203.0.113.0/24", "127.0.0.0/8")]


def addresses(text: str) -> list[str]:
    """Every IPv4 address in the text outside the allowed ranges."""
    found = []
    for m in IPV4.findall(text):
        try:
            ip = ipaddress.ip_address(m)
        except ValueError:      # not an address, such as 999.1.1.1
            continue
        if not any(ip in net for net in ALLOWED):
            found.append(m)
    return found


@pytest.fixture(scope="module")
def outreach():
    spec = importlib.util.spec_from_file_location("outreach", ROOT / "scripts" / "outreach.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_check_finds_addresses():
    assert addresses("It is at 10.1.2.3, and") == ["10.1.2.3"]
    assert addresses("at 192.0.2.10 or 127.0.0.1; Mozilla/5.0; 1.2.3.4.5; 300.1.1.1") == []


def test_no_committed_letter_or_the_script_carries_a_server_address():
    files = sorted(p for p in (ROOT / "outreach").rglob("*") if p.is_file())
    files.append(ROOT / "scripts" / "outreach.py")
    # names the files, never the address: CI logs are public too
    found = [str(p.relative_to(ROOT)) for p in files if addresses(p.read_text())]
    assert not found, "a server address is committed; use the placeholder (outreach/README.md)"


def test_the_letters_written_carry_the_placeholder_not_an_address(outreach):
    rows = outreach.council_rows()
    letters = [outreach.letter(rows[g], a, gr, p) for g, (a, gr, p) in outreach.LETTERS.items()]
    letters += [outreach.letter(rows[g], a, gr, False, why) for g, (a, gr, why) in outreach.NAMED.items()]
    letters += [outreach.letter(rows[g], "", "Democratic Services team", False, by_post=postal)
                for g, postal in outreach.POST.items()]
    # every kind of letter, whatever the registry says of each council today
    row = rows[next(iter(outreach.LETTERS))]
    for status, system, url in [("blocked", "modgov", "https://democracy.example.gov.uk"),
                                ("blocked", "cmis", "https://democracy.example.gov.uk"),
                                ("unreachable", "modgov", "https://democracy.example.gov.uk"),
                                ("forbidden", "cmis", "https://example.cmis.uk.com"),
                                ("forbidden", "modgov", "https://democracy.example.gov.uk")]:
        kind = {**row, "modgov_status": status, "system": system, "modgov_url": url}
        letters.append(outreach.letter(kind, "someone@example.gov.uk", "Democratic Services team", False))
        letters.append(outreach.letter(kind, "", "Democratic Services team", False, by_post="An address"))
    assert sum(len(addresses(text)) for text in letters) == 0
    asking = [text for text in letters if "let our server's requests through" in text]
    assert asking and all(f"It is at {outreach.SERVER_ADDRESS}, and" in text for text in asking)
    assert outreach.SERVER_ADDRESS == "[the server's IP address, as given in the letter sent]"


def test_the_robots_letters_are_honest_and_carry_placeholders(outreach):
    """Decision 21: one letter for each Modern.gov site whose robots.txt forbids reading, not to councils already
    asked, saying plainly where the site had already been read."""
    rows = outreach.council_rows()
    written = outreach.robots_rows(rows)
    names = {r["gss"] for r in written}
    assert "E10000011" in names and "E12000007" in names          # East Sussex, and the GLA
    assert "SA-SUSSEX-BRIGHTON" not in names                       # on East Sussex's site: asked in its letter
    assert not names & outreach.ALREADY_ASKED and len({r["modgov_url"] for r in written}) == len(written)
    east_sussex = outreach.robots_letter(rows["E10000011"], read_before=137)
    assert "I'm sorry" in east_sussex and "The 137 meetings already read are kept" in east_sussex
    assert "the Sussex and Brighton Combined County Authority" in east_sussex
    assert east_sussex.startswith(f"To: {outreach.ADDRESS_TO_FIND}\n")
    assert f"at {outreach.SERVER_ADDRESS}," in east_sussex and not addresses(east_sussex)
    for path in (ROOT / "outreach" / outreach.ROBOTS_BATCH).glob("*.txt"):
        assert outreach.SERVER_ADDRESS in path.read_text()
