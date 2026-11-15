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

    out = run(app, ["reports", "list"]).output
    assert f"#{rid}" in out and "takedown" in out and "reply to: me@example.org" in out
    assert run(app, ["list-reports"]).output == out          # the name the command had before still works
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


def test_load_takes_named_councils(tmp_path, monkeypatch):
    """The 26 CMIS councils read again in November 2026 are loaded once by name (docs/OPERATIONS.md)."""
    from councils import load

    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    seen = []
    monkeypatch.setattr(load, "many", lambda s, chosen, workers, resume: seen.extend(c.gss for c in chosen) or [])
    CliRunner().invoke(app, ["load", "E08000025", "Essex County Council", "--workers", "2"])
    assert sorted(seen) == ["E08000025", "E10000012"]
