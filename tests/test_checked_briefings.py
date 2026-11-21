"""Checked briefings as the Where They Stand family shows them (the charity's family/BRIEFINGS.md, kit 2.1.0, and the
review plan of 21 November 2026, B3 to B6; decision 34): the display rule for quotations on every answer a reader is
shown, the check strip's counts, the share card of a saved briefing, and the home page's proof of the checking.

The example is made the way Where Countries Stand's saved briefing kGfKBI3cRLw went wrong: the model attached a
citation to "in February 2025" rather than to the quotation before it, which the verifier found word for word in that
source, so the page showed the minutes' own words as if nothing supported them. It also has a quotation found word for
word, one not found, a sentence with no source and one whose only citation was removed, all on the made-up record of
tests/test_pipeline.py. The renderer's tests (web/src/__tests__/checked.test.tsx) read the answer as the server shows
it from web/src/__tests__/fixtures/shown-briefing.json, which the first test here checks is exactly what the server
sends: set COUNCILS_WRITE_FIXTURES=1 to write it again after an intended change."""

import copy
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient
from test_api import events, site_with
from test_pipeline import FakeClient, settings  # noqa: F401 - the fixture
from wts_core.checks import CheckCounts, check_counts
from wts_core.dates import long_date

from councils.api.app import CouncilsHooks, create_app
from councils.api.plaintext import with_text
from councils.sources import documents

ROOT = Path(__file__).parents[1]
SHOWN = ROOT / "web" / "src" / "__tests__" / "fixtures" / "shown-briefing.json"
QUESTION = {"question": "What have councils decided about bin collections?"}
BESIDE = "“that weekly bin collections be restored”"
FOUND = "“the waste and recycling strategy, including fortnightly bin collections”"
MISSING = "“bins will be emptied every week”"
QUOTE = re.compile(r'["“]([^"“”\n]{6,}?)["”]')


def final_of(evs):
    return next(e for e in evs if e.get("type") == "final")


def seg(text, status, sources=(), misquotes=()):
    return {"text": text, "sources": list(sources), "cited": [], "status": status, "loaded": [],
            "misquotes": list(misquotes)}


def the_answer(barnsley: int, guildford: int) -> dict:
    """The checks' answer, as the verifier wrote it under the current rules (version 2), which keep its marks when
    it is shown again."""
    missing = f" The minutes record the cabinet as saying {MISSING}"
    return {"segments": [
        seg("At Barnsley, the minutes record a motion on how often bins are emptied, as when Councillor Kitching moved "
            + BESIDE, "unsupported"),
        seg(" in February 2025", "cited", [barnsley]),
        seg(". ", "connective"),
        seg(f"At Guildford, the minutes record that Councillor Julia McShane introduced {FOUND}", "cited", [guildford]),
        seg(".", "connective"),
        seg(missing, "cited", [guildford], [{"start": missing.index(MISSING), "end": len(missing), "text": MISSING}]),
        seg(". ", "connective"),
        seg("Every council in the region did the same.", "unsupported"),
        seg(" ", "connective"),
        seg("Guildford ended weekly collections in 2019.", "invalid"),
    ], "markdown": "", "no_records": False, "citations_total": 4, "citations_invalid": 1, "grounded_ratio": 0.5,
        "unsupported_segments": 2, "loaded_words": 0, "quotes_total": 3, "quotes_unverified": 1, "rules": 2}


def quotes_with_no_source(answer):
    """The quotations found word for word that are shown inside a passage marked as having no source."""
    out = []
    for s in answer["segments"]:
        if s["status"] in ("unsupported", "invalid") and not s.get("misquotes"):
            out += [q for q in QUOTE.findall(s["text"]) if len(q.split()) >= 3]
    return out


def saved_example(c, site):
    """A saved briefing on the made-up record: the plan and the sources the site found for the question, and the
    answer above."""
    found = events(c.post("/api/ask", json=QUESTION))
    plan = next(e for e in found if e["type"] == "plan")
    sources = next(e for e in found if e["type"] == "sources")
    n = {card["council_name"].split()[0]: card["n"] for card in sources["sources"]}
    final = {"type": "final", "answer": the_answer(n["Barnsley"], n["Guildford"]), "briefing_id": "beside01"}
    site.parts.archive.save(QUESTION["question"], {"mode": "summary"}, [plan, sources, final], id="beside01")
    return sources["sources"], final["answer"]


def test_a_quotation_found_word_for_word_is_never_shown_as_having_no_source(settings):  # noqa: F811
    c, _, site, _ = site_with(settings)
    sources, saved = saved_example(c, site)
    assert quotes_with_no_source(saved)  # as it was saved: the quotation inside a passage with no source
    shown = final_of(c.get("/api/briefings/beside01").json()["events"])["answer"]
    assert quotes_with_no_source(shown) == []
    beside = next(s for s in shown["segments"] if s["text"] == BESIDE)
    assert beside["status"] == "cited" and beside["sources"] == saved["segments"][1]["sources"] and beside["beside"]
    # the words around it keep their mark, and the checks' own counts and text are unchanged
    assert shown["segments"][shown["segments"].index(beside) - 1]["status"] == "unsupported"
    assert {k: v for k, v in shown.items() if k != "segments"} == \
        {k: v for k, v in saved.items() if k != "segments"}
    assert "".join(s["text"] for s in shown["segments"]) == "".join(s["text"] for s in saved["segments"])
    # the strip's counts: 3 of 4 citations, 2 of 3 quotations, 3 passages without a source (the words before the
    # quotation, the sentence no source supports, and the one whose citation was removed)
    assert check_counts(shown) == CheckCounts(3, 4, 2, 3, 3)
    # the saved copy keeps the verifier's own segments: only what is shown changes
    kept = final_of(site.parts.archive.get("beside01").events)["answer"]
    assert kept["segments"] == saved["segments"]
    # what the renderer's tests read is exactly what the server sends
    fixture = {"id": "beside01", "sources": sources, "answer": shown, "counts": asdict(check_counts(shown))}
    if os.environ.get("COUNCILS_WRITE_FIXTURES"):
        SHOWN.parent.mkdir(parents=True, exist_ok=True)
        SHOWN.write_text(json.dumps(fixture, ensure_ascii=False, indent=1) + "\n")
    assert json.loads(SHOWN.read_text()) == fixture


def test_new_cached_and_saved_briefings_are_all_shown_through_the_display_rule(settings, monkeypatch):  # noqa: F811
    """A new briefing's final event, the same question again from the cache, and the saved briefing at its address
    each show the quotation as its source's; the copies kept are the verifier's."""
    import councils.rag.pipeline as pipeline

    c, _, site, _ = site_with(settings)
    answer = the_answer(1, 2)
    monkeypatch.setattr(pipeline, "check_briefing", lambda *a, **k: copy.deepcopy(answer))
    first = final_of(events(c.post("/api/ask", json=QUESTION)))
    again = final_of(events(c.post("/api/ask", json=QUESTION)))
    bid = first["briefing_id"]
    saved = final_of(c.get(f"/api/briefings/{bid}").json()["events"])
    assert again.get("cached") and again["briefing_id"] == bid
    for final in (first, again, saved):
        segs = final["answer"]["segments"]
        assert [s["status"] for s in segs[:4]] == ["unsupported", "cited", "cited", "connective"], segs
        assert segs[1]["text"] == BESIDE and segs[1]["beside"] is True and segs[1]["sources"] == [1]
        assert quotes_with_no_source(final["answer"]) == []
        assert check_counts(final["answer"]) == CheckCounts(3, 4, 2, 3, 3)
    kept = final_of(site.parts.archive.get(bid).events)["answer"]["segments"]
    assert kept == answer["segments"]


def test_the_hooks_show_cached_answers_and_new_ones_through_the_display_rule():
    hooks = CouncilsHooks(None)
    final = {"type": "final", "answer": the_answer(1, 2)}
    for answer in (final_of(hooks.on_cached(None, [final]))["answer"], hooks.for_this_reader(None, final)["answer"]):
        assert any(s["text"] == BESIDE and s.get("beside") for s in answer["segments"])
    assert final["answer"]["segments"][0]["text"].endswith(BESIDE)  # the event given is not changed


SHELL = """<!doctype html>
<html lang="en-GB">
  <head>
    <title>Where Councils Stand</title>
    <meta property="og:image" content="https://wherecouncilsstand.com/family/card.png">
    <meta property="og:image:alt" content="Where Councils Stand. A Where They Stand project.">
  </head>
  <body><main id="main"><div id="app"></div></main></body>
</html>"""


def test_a_saved_briefing_has_its_own_share_card(settings, tmp_path):  # noqa: F811
    """Drawn once by wts-core's briefing_card and kept on disk; the link preview points at it, with the site's
    neutral title and the strip's counts in words, never the reader's question (decision 33)."""
    from PIL import Image

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text(SHELL)
    settings.raw.setdefault("paths", {})["web_dist"] = str(dist)
    c, _, site, _ = site_with(settings)
    saved_example(c, site)
    page = c.get("/b/beside01").text
    written = long_date(site.parts.archive.get("beside01").created_at[:10])
    assert '<meta property="og:image" content="https://wherecouncilsstand.com/b/beside01/card.png">' in page
    alt = re.search(r'<meta property="og:image:alt" content="([^"]*)">', page)[1]
    assert alt == (f"Briefing from council minutes, {written}: a briefing written by AI, checked against the council "
                   "minutes. 3 of 4 citations matched to the record, 2 of 3 quotations found word for word, 3 "
                   "sentences without a source. Where Councils Stand.")
    assert "bin collections" not in alt and QUESTION["question"] not in page
    card = c.get("/b/beside01/card.png")
    assert card.status_code == 200 and card.headers["content-type"] == "image/png"
    kept = list((settings.data_dir / "cards").glob("beside01.*.png"))
    assert len(kept) == 1 and kept[0].read_bytes() == card.content
    with Image.open(kept[0]) as image:
        assert image.size == (1200, 630)
    mtime = kept[0].stat().st_mtime_ns
    assert c.get("/b/beside01/card.png").content == card.content and kept[0].stat().st_mtime_ns == mtime  # drawn once
    # nothing for a briefing that isn't there, wrote nothing, or was withdrawn; their pages keep the family's card
    assert c.get("/b/nosuchone/card.png").status_code == 404
    site.parts.archive.save("Bins?", {}, [{"type": "final", "answer": None, "note": "Sources only."}], id="only001")
    assert c.get("/b/only001/card.png").status_code == 404
    assert "/family/card.png" in c.get("/b/only001").text
    assert site.parts.archive.withdraw("beside01", "A test.")
    assert c.get("/b/beside01/card.png").status_code == 404
    # the home page keeps the family's card
    assert '<meta property="og:image" content="https://wherecouncilsstand.com/family/card.png">' in c.get("/").text


def test_a_hidden_briefing_has_no_card(settings, tmp_path):  # noqa: F811
    c, _, site, cfg = site_with(settings)
    saved_example(c, site)
    site.replies.hide("/b/beside01", "A made-up note, for testing.")
    assert TestClient(create_app(cfg, state=site.db)).get("/b/beside01/card.png").status_code == 404


def flat(html: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html)).strip()


def test_the_home_page_shows_the_checking_without_a_script():
    """The proof (family/BRIEFINGS.md, "The home page"): three steps, a sentence with a record quotation and its chip,
    beside the passage it came from with the same words highlighted, and a link to the methodology, in the page's
    HTML. The quotation and the passage are a genuine council minute, the site's test copy of Glasgow City Council's
    City Administration Committee of 25 January 2024, and the page says where they come from."""
    page = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
    proof = page[page.index('<section class="wts-proof'):]
    proof = proof[:proof.index("</section>")]
    steps = re.findall(r"<li>([^<]+)</li>", proof[:proof.index("</ol>")])
    assert steps == ["Searches only the official record", "AI writes only from what was found",
                     "Every citation and quotation is checked before you see it"]
    minutes = re.sub(r"\s+", " ", documents.pdf_text((ROOT / "tests" / "fixtures" / "coins" /
                                                       "glasgow_minutes_19226.pdf").read_bytes()))
    marked = re.findall(r"<mark[^>]*>([^<]+)</mark>", proof)
    assert marked == ["the principles and process for a review of collecting priorities"] and marked[0] in minutes
    said = flat(re.search(r'<p class="wts-proof__said">(.*?)</p>', proof, re.S)[1])
    assert f"“{marked[0]}”" in said and "word for word" in said
    assert "Source 1Glasgow City Council, City Administration Committee, 25 January 2024" in said
    passage = flat(re.search(r'<p class="wts-passage"[^>]*>(.*?)</p>', proof, re.S)[1])
    for part in passage.strip("… ").split(" … "):
        assert re.sub(r"\(\w+\) ", "", part.strip("… ")) in re.sub(r"\(\w+\) ", "", minutes), part
    assert "Glasgow Life Museums Collections Development Policy 2024-29 approved." in minutes
    assert "Bailie Christie, City Convener for Culture, Sport and International Relations" in minutes
    assert "From the minutes of Glasgow City Council, City Administration Committee, 25 January 2024" in proof
    assert "The quotation and the passage are real" in proof and 'href="/methodology#ai-briefings"' in proof
    assert "<script" not in proof and 'class="wts-proof wts-cloth--councils' in proof
    assert '<link rel="stylesheet" href="/family/briefing.css" />' in page
    # outside the app's root, so the server's text for readers without scripts leaves it in place
    assert page.index('<div id="app"></div>') < page.index('<section class="wts-proof')
    assert "wts-proof" in with_text(page, "<h1>Council decisions, from the minutes</h1>")


def test_the_question_box_offers_sources_only_as_an_equal_choice_and_the_wait_speaks_once():
    """Two submit buttons side by side, a briefing or the sources alone with no AI (the review plan, B4); and one
    status region, in which the wait says each stage once (family/BRIEFINGS.md, "The wait")."""
    app = (ROOT / "web" / "src" / "ask.tsx").read_text(encoding="utf-8")
    assert re.search(r'type="submit" name="how" value="briefing"', app)
    assert re.search(r'type="submit" name="how" value="sources"[^>]*>\s*Sources only \(no AI\)\s*</button>', app)
    assert app.count('role="status"') == 1 and "aria-live" not in app.replace('role="status" aria-live="polite"', "")
    assert "<Why />" in app and 'className="why panel"' not in (ROOT / "web" / "src" / "components" / "Why.tsx").read_text()
