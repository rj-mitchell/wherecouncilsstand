"""The owner's commands for reports and withdrawn briefings (docs/OPERATIONS.md)."""

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from councils.api.app import create_app
from councils.cli import app
from councils.config import load_settings
from councils.replies import open_replies
from councils.state import open_archive, open_state


def test_reports_are_listed_closed_and_briefings_withdrawn(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    db = open_state(load_settings())
    archive = open_archive(db)
    replies = open_replies(db, lambda: None, archive)
    rid = replies.report(kind="takedown", page="/votes/x", message="Please remove my name.", contact="me@example.org")
    archive.save("Bins?", {}, [], id="abc123")
    run = CliRunner().invoke

    listing = run(app, ["reports", "list"])
    out = listing.stdout
    assert listing.stderr == ""                              # the name it has now says nothing more
    assert f"#{rid}" in out and "takedown" in out and "reply to: me@example.org" in out
    # The name the command had before still works. From wts-core 0.3.0 it says what replaces it, on standard
    # error, before it does its work; standard output and the exit status are unchanged.
    older = run(app, ["list-reports"])
    assert (older.exit_code, older.stdout) == (0, out)
    assert older.stderr == '"list-reports" is an older name for this command: it is now "reports list".\n'
    assert run(app, ["reports", "close", str(rid)]).output.strip() == "closed"
    assert run(app, ["reports", "list"]).output == ""
    assert "me@example.org" not in run(app, ["reports", "list", "--all"]).output     # deleted on closing
    r = run(app, ["reports", "close", str(rid)])
    assert r.exit_code == 1 and r.output.strip() == f"error: no open report {rid}"
    assert replies.reports(open_only=False)[0]["status"] == "resolved"

    assert run(app, ["withdraw", "abc123", "--reason", "It named the wrong council."]).output.strip() == "withdrawn"
    assert run(app, ["withdraw", "nope", "--reason", "x"]).output.strip() == "no briefing with that id"
    r = TestClient(create_app(load_settings(), state=db)).get("/api/briefings/abc123")
    assert r.status_code == 410 and r.json()["detail"] == "This briefing has been withdrawn: It named the wrong council."


def test_a_briefing_whose_id_begins_with_a_dash_is_withdrawn_with_two_dashes_before_it(tmp_path, monkeypatch):
    """Before wts-core 0.3.0 about one saved briefing in 64 had an id beginning with "-", which a command line reads
    as an option: `councils withdraw -vPeHLp1u54` ended "No such option" and withdrew nothing (tests/test_hidden.py
    met it about one run in twelve). Such ids stay valid. The owner writes `--` before the id, after any options
    (docs/OPERATIONS.md, "Running the website"); ids made from wts-core 0.3.0 on never begin with "-"."""
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    db = open_state(load_settings())
    archive = open_archive(db)
    made_earlier = "-vPeHLp1u54"
    archive.save("Bins?", {}, [], id=made_earlier)
    run = CliRunner().invoke

    without = run(app, ["withdraw", made_earlier, "--reason", "It named the wrong council."])
    assert without.exit_code == 2 and "No such option" in without.output
    assert archive.get(made_earlier).withdrawn_at is None                  # nothing was withdrawn
    done = run(app, ["withdraw", "--reason", "It named the wrong council.", "--", made_earlier])
    assert (done.exit_code, done.output.strip()) == (0, "withdrawn")
    assert archive.get(made_earlier).withdrawn_reason == "It named the wrong council."
    r = TestClient(create_app(load_settings(), state=db)).get(f"/api/briefings/{made_earlier}")
    assert r.status_code == 410
    # and `--` changes nothing for an id of the ordinary kind
    archive.save("Bins again?", {}, [], id="abc123")
    assert run(app, ["withdraw", "--reason", "x", "--", "abc123"]).output.strip() == "withdrawn"
    # an id made now never begins with "-": the first character of 2,000 drawn
    from councils.state import new_briefing_id

    assert not any(new_briefing_id().startswith("-") for _ in range(2000))


def test_load_takes_named_councils(tmp_path, monkeypatch):
    """The 26 CMIS councils read again in November 2026 are loaded once by name (docs/OPERATIONS.md)."""
    from councils import load

    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    seen = []
    monkeypatch.setattr(load, "many", lambda s, chosen, workers, resume: seen.extend(c.gss for c in chosen) or [])
    CliRunner().invoke(app, ["load", "E08000025", "Essex County Council", "--workers", "2"])
    assert sorted(seen) == ["E08000025", "E10000012"]
