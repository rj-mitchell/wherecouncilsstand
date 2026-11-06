"""The Where They Stand family kit in web/public/family (README, "In the family").

The kit is copied in by the charity's family/kit/sync.mjs and committed; the copies must not be edited. Its VERSION
file records a hash of every file it wrote, so this checks the copy against its own record without needing the
charity's repository. Whether the copy is the latest kit is checked by `sync.mjs --check` before merging.
"""

import hashlib
import re
from pathlib import Path

from fastapi.testclient import TestClient
from test_api import client  # noqa: F401 - the fixture
from test_pipeline import settings  # noqa: F401 - the fixture

from councils.api.app import create_app

FAMILY = Path(__file__).resolve().parents[1] / "web" / "public" / "family"


def test_the_kit_copy_matches_its_own_record():
    version = (FAMILY / "VERSION").read_text(encoding="utf-8")
    assert "site councils" in version and "base /family/" in version
    expected = re.search(r"^sha256 ([0-9a-f]{64})$", version, re.M).group(1)
    files = sorted(p.relative_to(FAMILY).as_posix() for p in FAMILY.rglob("*") if p.is_file() and p.name != "VERSION")
    h = hashlib.sha256()
    for path in files:
        h.update(path.encode())
        h.update(b"\0")
        h.update((FAMILY / path).read_bytes())
        h.update(b"\0")
    assert h.hexdigest() == expected, "web/public/family was edited, or a file is missing: sync the kit again"


def test_the_kit_asks_for_nothing_from_another_site():
    """The front door's content security policy allows this site's own files only (default-src 'self')."""
    head = (FAMILY / "head.html").read_text(encoding="utf-8")
    for tag in re.findall(r"<link [^>]*>", head):
        assert re.search(r'href="/family/', tag), tag
    css = (FAMILY / "family.css").read_text(encoding="utf-8") + (FAMILY / "fonts.css").read_text(encoding="utf-8")
    assert "http" not in re.sub(r"/\*.*?\*/", "", css, flags=re.S)
    assert "<script" not in "".join(p.read_text(encoding="utf-8") for p in FAMILY.glob("*.html"))


def test_the_kit_and_favicon_are_served(client, tmp_path):  # noqa: F811
    _, _, state, cfg = client
    dist = tmp_path / "dist"
    (dist / "family" / "fonts").mkdir(parents=True)
    (dist / "index.html").write_text("<!doctype html><title>Where Councils Stand</title>")
    for name in ("favicon.ico", "family.css", "fonts/OFL.txt"):
        (dist / "family" / name).write_bytes((FAMILY / name).read_bytes())
    cfg.raw.setdefault("paths", {})["web_dist"] = str(dist)
    t = TestClient(create_app(cfg, state=state))
    icon = t.get("/favicon.ico")
    assert icon.status_code == 200 and icon.content == (FAMILY / "favicon.ico").read_bytes()
    assert t.get("/family/family.css").headers["content-type"].startswith("text/css")
    assert t.get("/family/fonts/OFL.txt").status_code == 200
    assert t.get("/family/nothing.css").status_code == 404


def test_council_pages_link_to_where_landlords_stand(client):  # noqa: F811
    """data_static/landlords_links.csv (scripts/landlords_links.py): the council as a landlord, and its area."""
    c, _, _, _ = client
    page = c.get("/api/councils/E08000038").json()  # Barnsley owns homes, and has an area page
    assert page["landlords"]["council"]["url"] == \
        "https://wherelandlordsstand.com/landlords/barnsley-metropolitan-borough-council/"
    assert page["landlords"]["area"]["url"] == "https://wherelandlordsstand.com/areas/barnsley/"
    assert page["landlords"]["area"]["landlords"] > 0
    assert c.get("/api/councils/W06000015").json()["landlords"] is None  # Where Landlords Stand covers England


def test_the_landlords_lookup_covers_only_councils_in_scope():
    import csv

    root = FAMILY.parents[2] / "data_static"
    with open(root / "councils.csv", encoding="utf-8") as fh:
        ours = {r["gss"] for r in csv.DictReader(fh)}
    with open(root / "landlords_links.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert rows and all(r["gss"] in ours for r in rows)
    assert all(re.fullmatch(r"[a-z0-9-]+", r["area_slug"] + r["council_landlord_slug"] or "x") for r in rows)
