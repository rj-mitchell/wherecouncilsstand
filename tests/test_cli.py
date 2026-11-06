"""The owner's commands for reports and withdrawn briefings (docs/OPERATIONS.md)."""

from fastapi.testclient import TestClient
from typer.testing import CliRunner

from councils.api.app import create_app
from councils.api.state import StateDB
from councils.cli import app
from councils.config import load_settings


def test_reports_are_listed_closed_and_briefings_withdrawn(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path))
    state = StateDB(tmp_path / "state.db")
    rid = state.add_report("takedown", "/votes/x", "Please remove my name.", "me@example.org")
    state.save_briefing("abc123", "Bins?", {}, [])
    run = CliRunner().invoke

    out = run(app, ["list-reports"]).output
    assert f"#{rid}" in out and "takedown" in out and "reply to: me@example.org" in out
    assert run(app, ["close-report", str(rid)]).output.strip() == "closed"
    assert run(app, ["list-reports"]).output == ""
    assert "me@example.org" not in run(app, ["list-reports", "--all"]).output     # deleted on closing
    assert run(app, ["close-report", str(rid)]).output.strip() == "no open report with that number"

    assert run(app, ["withdraw", "abc123", "--reason", "It named the wrong council."]).output.strip() == "withdrawn"
    assert run(app, ["withdraw", "nope", "--reason", "x"]).output.strip() == "no briefing with that id"
    r = TestClient(create_app(load_settings(), state=state)).get("/api/briefings/abc123")
    assert r.status_code == 410 and r.json()["detail"] == "This briefing has been withdrawn: It named the wrong council."
