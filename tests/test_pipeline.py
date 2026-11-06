"""Index, search and briefing on synthetic minutes, with a fake Claude client (no network, no API key)."""

from dataclasses import replace
from datetime import date
from types import SimpleNamespace as NS

import pytest

from councils import store
from councils.config import load_settings
from councils.embed.base import HashingEmbedder
from councils.engine import Engine, Filters
from councils.index.build import Indexer, embed_pending
from councils.rag.pipeline import AskRequest, Pipeline, answer_once
from councils.rag.query_parse import parse_offline

TODAY = date(2026, 10, 24)
BARNSLEY, GUILDFORD = "E08000038", "E07000209"


class FakeStream:
    def __init__(self, blocks):
        self.blocks = blocks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        for b in self.blocks:
            yield NS(type="content_block_delta", delta=NS(type="text_delta", text=b["text"]))

    def get_final_message(self):
        content = [NS(type="text", text=b["text"], citations=[NS(type="search_result_location", **c)
                                                              for c in b.get("citations", [])])
                   for b in self.blocks]
        return NS(content=content, stop_reason="end_turn", model="claude-sonnet-5-5",
                  usage=NS(input_tokens=1000, output_tokens=200, cache_read_input_tokens=0,
                           cache_creation_input_tokens=0))


class FakeClient:
    """Cites the first block of the first source, then adds a sentence with a loaded word and no citation."""

    def __init__(self):
        self.calls = []
        self.beta = NS(messages=NS(stream=self._stream))
        self.messages = NS(stream=self._stream, parse=self._parse)

    def _parse(self, **kw):
        raise RuntimeError("offline parse in tests")

    def _stream(self, **kw):
        self.calls.append(kw)
        first = next(b for b in kw["messages"][0]["content"] if b["type"] == "search_result")
        quote = first["content"][0]["text"]
        return FakeStream([
            {"text": "The minutes record that "},
            {"text": quote[:60], "citations": [{"search_result_index": 0, "cited_text": quote, "source": "x"}]},
            {"text": " The scheme was a fiasco that residents across the borough opposed for many months."},
        ])


def meeting(gss, mid, d, kind="council"):
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "council": gss, "committee_id": 1,
            "committee_title": "Full Council" if kind == "council" else "Cabinet", "kind": kind, "date": d,
            "year": d.year, "status": "", "location": "", "webcast": False, "minutes_published": True, "items": 1,
            "items_with_minutes": 1, "earlier_minutes": "", "minutes_document": "", "attendees": 3, "url": "u"}


def item(gss, mid, iid, d, title, text):
    return {"item_id": f"{gss}:{mid}:{iid}", "meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year,
            "position": 0, "number": f"{iid}.", "title": title, "agenda_text": "", "minutes_text": text,
            "minutes_source": "html", "vote_tables": "", "is_decision": False, "is_restricted": False,
            "is_call_in": False, "declaration_count": 0, "documents": 0, "url": f"https://example/{gss}/{iid}"}


def member(gss, mid, d, member_id, name, party):
    return {"meeting_id": f"{gss}:{mid}", "gss": gss, "date": d, "year": d.year, "member_id": member_id,
            "member_type": "U", "name": name, "role": "Committee Member", "attendance": "Present, as expected",
            "party_label": party, "party": party, "ward": ""}


@pytest.fixture
def settings(tmp_path):
    s = load_settings(**{"embedding.backend": "hashing", "embedding.dim": 64})
    s = replace(s, data_dir=tmp_path)
    d1, d2 = date(2025, 2, 26), date(2025, 3, 5)
    root = s.parquet_dir
    store.parquet.write(root, "meetings", BARNSLEY, [meeting(BARNSLEY, 1, d1)])
    store.parquet.write(root, "items", BARNSLEY, [item(
        BARNSLEY, 1, 10, d1, "Notice of Motion - Weekly Bin Collections",
        "Councillor Kitching moved that weekly bin collections be restored.\nMr J Bloggs asked about recycling "
        "centres.\nUpon being put to the vote the motion was lost.")])
    store.parquet.write(root, "attendance", BARNSLEY, [
        member(BARNSLEY, 1, d1, "1", "Councillor Hannah Kitching", "LD"),
        member(BARNSLEY, 1, d1, "2", "Councillor Sir Steve Houghton", "LAB"),
        member(BARNSLEY, 1, d1, "3", "Councillor Robin Franklin", "LAB")])
    store.parquet.write(root, "meetings", GUILDFORD, [meeting(GUILDFORD, 2, d2)])
    store.parquet.write(root, "items", GUILDFORD, [item(
        GUILDFORD, 2, 20, d2, "Waste and Recycling Strategy",
        "Councillor Julia McShane introduced the waste and recycling strategy, including fortnightly bin "
        "collections.\nRESOLVED that the strategy be adopted.")])
    store.parquet.write(root, "attendance", GUILDFORD, [
        member(GUILDFORD, 2, d2, "7", "Councillor Julia McShane", "LD"),
        member(GUILDFORD, 2, d2, "8", "Councillor Tim Anderson", "LD"),
        member(GUILDFORD, 2, d2, "9", "Councillor Paul Spooner", "CON")])
    for gss in (BARNSLEY, GUILDFORD):
        store.parquet.write(root, "votes", gss, [])
    idx = Indexer(s)
    idx.index_all()
    embed_pending(s, idx.index, idx.state, HashingEmbedder(64))
    return s


def test_passages_carry_control_parties_and_redaction(settings):
    rows = Engine(settings, HashingEmbedder(64), TODAY).index.passages().to_arrow().to_pylist()
    barnsley = next(r for r in rows if r["gss"] == BARNSLEY)
    assert barnsley["control"] == "LAB"                 # two of three members listed are Labour
    assert barnsley["parties"] == ["LD"]                # Councillor Kitching is named
    assert "Bloggs" not in barnsley["text"] and "[name removed]" in barnsley["text"]
    guildford = next(r for r in rows if r["gss"] == GUILDFORD)
    assert guildford["control"] == "LD"


def test_search_is_balanced_and_filters(settings):
    eng = Engine(settings, HashingEmbedder(64), TODAY)
    res = eng.search("bin collections", Filters(), limit=5)
    assert {r["gss"] for r in res.records} == {BARNSLEY, GUILDFORD}
    assert set(res.evidence["groups"]) == {"Councils controlled by Labour", "Councils controlled by the Liberal Democrats"}
    res = eng.search("bin collections", Filters(control=["LD"]), limit=5)
    assert {r["gss"] for r in res.records} == {GUILDFORD}
    res = eng.search("bin collections", Filters(parties=["LD"], councils=[BARNSLEY]), limit=5)
    assert [r["gss"] for r in res.records] == [BARNSLEY]


def test_offline_plan():
    plan = parse_offline("What have Labour-run councils decided about bin collections since 2023?", TODAY)
    assert plan.filters.control == ["LAB"] and plan.filters.date_from == date(2023, 1, 1)
    assert "bin collections" in plan.search_text and "labour" not in plan.search_text
    plan = parse_offline("What have Green councillors in Barnsley said about libraries?", TODAY)
    assert plan.filters.parties == ["GRN"] and plan.filters.councils == [BARNSLEY]


def test_pipeline_end_to_end_is_grounded(settings):
    client = FakeClient()
    pipe = Pipeline(settings, Engine(settings, HashingEmbedder(64), TODAY), client=client, today=TODAY)
    out = answer_once(pipe, AskRequest("What have councils decided about bin collections?"))
    srcs = out["sources"]["sources"]
    assert srcs and all("party in overall control of the council on the date" in s["title"] for s in srcs)
    assert any("Councillor Hannah Kitching (Liberal Democrats)" in s["title"] for s in srcs)
    answer = out["final"]["answer"]
    assert answer["citations_total"] == 1 and answer["citations_invalid"] == 0
    assert answer["unsupported_segments"] == 1          # the uncited sentence is marked, not passed off as sourced
    assert answer["loaded_words"] == 1                  # "fiasco" in the model's own voice is flagged
    sent = client.calls[0]["messages"][0]["content"]
    assert all("Bloggs" not in b["text"] for s in sent if s["type"] == "search_result" for b in s["content"])


def test_reindex_keeps_embeddings_of_unchanged_passages_and_updates_tags(settings):
    idx = Indexer(settings)
    before = idx.index.vectors().count_rows()
    assert before and all(v["embedded"] for v in idx.state.data.values())
    # the party label changes (as after a new rule in parse/parties.py): tags change, text doesn't
    rows = store.parquet.read(settings.parquet_dir, "attendance", GUILDFORD)
    store.parquet.write(settings.parquet_dir, "attendance", GUILDFORD,
                        [r | {"party": "GRN"} if r["member_id"] == "7" else r for r in rows])
    idx.index_all()
    assert idx.index.vectors().count_rows() == before
    assert all(v["embedded"] for v in idx.state.data.values())
    vec_rows = idx.index.vectors().search().where(f"gss = '{GUILDFORD}'").limit(None).to_list()
    assert all("GRN" in r["parties"] for r in vec_rows)


def test_one_sided_vote_is_marked_as_possibly_incomplete(settings):
    from councils.rag.sources import Lookup
    store.parquet.write(settings.parquet_dir, "votes", BARNSLEY, [{
        "vote_id": f"{BARNSLEY}:1:10:0", "item_id": f"{BARNSLEY}:1:10", "meeting_id": f"{BARNSLEY}:1", "gss": BARNSLEY,
        "date": date(2025, 2, 26), "year": 2025, "question": "motion", "outcome": "", "member_id": "1",
        "name": "Kitching", "vote": "for", "excerpt": ""}])
    blocks = Lookup(settings, {BARNSLEY}).vote_blocks(f"{BARNSLEY}:1:10", BARNSLEY, date(2025, 2, 26))
    assert len(blocks) == 1 and "Only this side is recorded here" in blocks[0]
    assert "Kitching (Liberal Democrats)" in blocks[0]


def test_councils_stored_under_replaced_codes_can_be_moved(tmp_path):
    import importlib.util
    import sys
    from pathlib import Path

    scripts = Path(__file__).resolve().parents[1] / "scripts"
    sys.path.insert(0, str(scripts))
    spec = importlib.util.spec_from_file_location("recode_councils", scripts / "recode_councils.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    raw, pq = tmp_path / "raw", tmp_path / "parquet"
    (raw / "modgov" / "E08000016" / "meeting").mkdir(parents=True)
    (raw / "modgov" / "E08000016" / "meeting" / "1.xml").write_text("<x/>")
    (pq / "items").mkdir(parents=True)
    (pq / "items" / "E08000016.parquet").write_text("old")
    assert mod.recode(raw, pq, "E08000016", "E08000038", dry_run=True)
    assert (raw / "modgov" / "E08000016").exists()
    mod.recode(raw, pq, "E08000016", "E08000038", dry_run=False)
    assert (raw / "modgov" / "E08000038" / "meeting" / "1.xml").exists()
    assert not (raw / "modgov" / "E08000016").exists() and not (pq / "items" / "E08000016.parquet").exists()


def test_the_claude_client_gives_up_after_five_minutes(monkeypatch):
    from councils.rag.answer import make_client

    monkeypatch.setenv("COUNCILS_ANTHROPIC_API_KEY", "test-key")
    client = make_client()
    assert client.timeout.read == 300.0 and client.timeout.connect == 10.0 and client.max_retries == 2


def test_an_update_with_no_changes_writes_nothing_to_the_index(settings):
    """Every write to a LanceDB table makes a new version, and each rebuild of the indices leaves the old one on
    disk, so an update with nothing new must write nothing; one with changes merges them and cleans up."""
    from councils.index.build import update_index
    from councils.index.lance import SearchIndex

    idx = SearchIndex(settings.index_dir, 64)

    def versions():
        return idx.passages().version, idx.vectors().version

    before = versions()
    out = update_index(settings, [], HashingEmbedder(64))
    assert out == {"passages_embedded": 0, "still_to_embed": 0, "index": "unchanged"} and versions() == before

    # a council whose stored meetings changed: its rows are merged into the indices, not built again
    out = update_index(settings, [GUILDFORD], HashingEmbedder(64))
    assert out["index"] == "merged" and versions() != before
    assert not idx.unmerged() and not idx.needs_build()
    eng = Engine(settings, HashingEmbedder(64), TODAY)
    assert {r["gss"] for r in eng.search("bin collections", Filters(), limit=5).records} == {BARNSLEY, GUILDFORD}


def test_meaning_search_is_trained_again_once_it_has_grown_by_a_fifth(tmp_path, monkeypatch):
    from councils.index import lance

    monkeypatch.setattr(lance, "MIN_VECTORS_FOR_INDEX", 1)
    idx = lance.SearchIndex(tmp_path, 4)
    assert not idx.needs_build()                     # nothing indexed yet
    (tmp_path / lance.TRAINED).write_text('{"vectors": 100}')
    monkeypatch.setattr(idx, "has_data", lambda: True)
    monkeypatch.setattr(idx, "has_keyword_index", lambda: True)
    monkeypatch.setattr(idx, "_names", lambda: {lance.PASSAGES, lance.VECTORS})

    class Table:
        def __init__(self, n):
            self.n = n

        def count_rows(self):
            return self.n

        def list_indices(self):
            return [NS(columns=["vector"])]

    for n, rebuild in ((119, False), (120, True)):
        monkeypatch.setattr(idx, "vectors", lambda n=n: Table(n))
        assert idx.needs_build() is rebuild
