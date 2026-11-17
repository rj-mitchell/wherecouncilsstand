"""Off-site copies of the nightly backup in Backblaze B2 (a simulated B2; no real key is used): wts-core's
(``wts_core.ops``, ``wts_core.adapters.b2``), with this site's names, what it keeps and its own alert wording."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import UTC, datetime, timedelta

import httpx
import pytest
from wts_core import ops
from wts_core.adapters import b2
from wts_core.ops import OffsiteError

from councils.config import SITE
from councils.state import BACKUP_ALERTS, BACKUPS


def configured(env, client=None):
    return b2.configured(SITE, env, client=client)


def send(archive, *, keep=None, env, client=None):
    return ops.send_offsite(archive, configured(env, client), BACKUPS, keep=keep)


def check(*, env, client=None):
    return ops.check_offsite(configured(env, client), BACKUPS, how_to_set_up=b2.how_to_set_up(SITE))


def backup_alerts(folder, env=None):
    """What `councils backup-check` is given to print, as the site's own code returned it."""
    alerts = ops.backup_alerts(folder, BACKUPS, offsite_set_up=configured(env or {}) is not None,
                               wording=BACKUP_ALERTS)
    return [{"level": a.level, "text": a.text} for a in alerts]


ENV = {"COUNCILS_B2_BUCKET": "wts-backups", "COUNCILS_B2_KEY_ID": "kid", "COUNCILS_B2_APPLICATION_KEY": "secret"}


class FakeB2:
    def __init__(self, bucket="wts-backups", fail_uploads=0, can_delete=True):
        self.bucket, self.fail_uploads, self.can_delete = bucket, fail_uploads, can_delete
        self.files: dict[str, bytes] = {}

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("b2_authorize_account"):
            if request.headers.get("authorization") != httpx.BasicAuth("kid", "secret")._auth_header:
                return httpx.Response(401)
            return httpx.Response(200, json={"accountId": "acc", "apiUrl": "https://api.b2.test",
                                             "authorizationToken": "tok",
                                             "allowed": {"bucketId": "b1", "bucketName": self.bucket}})
        assert request.headers.get("authorization") in ("tok", "up"), "every call carries a token"
        body = json.loads(request.content or b"{}") if path.startswith("/b2api") else {}
        if path.endswith("b2_get_upload_url"):
            return httpx.Response(200, json={"uploadUrl": "https://up.b2.test/upload", "authorizationToken": "up"})
        if path == "/upload":
            if self.fail_uploads:
                self.fail_uploads -= 1
                return httpx.Response(503)
            assert request.headers["x-bz-content-sha1"] == hashlib.sha1(request.content).hexdigest()  # noqa: S324
            self.files[request.headers["x-bz-file-name"]] = request.content
            return httpx.Response(200, json={"fileName": request.headers["x-bz-file-name"]})
        if path.endswith("b2_list_file_names"):
            return httpx.Response(200, json={"files": [{"fileName": n, "fileId": f"id-{n}"} for n in sorted(self.files)
                                                       if n.startswith(body["prefix"])]})
        if path.endswith("b2_delete_file_version"):
            if not self.can_delete:
                return httpx.Response(401, json={"code": "unauthorized"})
            del self.files[body["fileName"]]
            return httpx.Response(200, json={})
        return httpx.Response(404)


def archive(tmp_path, day):
    p = tmp_path / f"councils-state-{day}.sqlite.gz"
    p.write_bytes(f"backup {day}".encode())
    return p


def test_not_set_up_does_nothing(tmp_path):
    assert configured({}) is None
    assert send(archive(tmp_path, "2026-10-12"), env={}) == {"offsite": "not set up"}
    assert check(env={}) == {"ok": False, "error": "not set up: add COUNCILS_B2_BUCKET, COUNCILS_B2_KEY_ID and "
                                                   "COUNCILS_B2_APPLICATION_KEY to deploy/.env"}


def test_upload_retries_and_keeps_the_newest(tmp_path):
    b2 = FakeB2(fail_uploads=1)
    client = httpx.Client(transport=httpx.MockTransport(b2))
    for day in ("2026-10-10", "2026-10-11", "2026-10-12"):
        out = send(archive(tmp_path, day), keep=2, env=ENV, client=client)
    assert out["ok"] and out["stored"] == 2 and out["deleted"] == 1
    assert sorted(b2.files) == ["councils-state-2026-10-11.sqlite.gz", "councils-state-2026-10-12.sqlite.gz"]
    assert json.loads((tmp_path / "offsite.json").read_text())["ok"]
    assert check(env=ENV, client=client) == {"ok": True, "bucket": "wts-backups", "backups": 2,
                                             "newest": "councils-state-2026-10-12.sqlite.gz"}


def test_a_key_without_delete_rights_still_stores(tmp_path):
    b2 = FakeB2(can_delete=False)
    client = httpx.Client(transport=httpx.MockTransport(b2))
    send(archive(tmp_path, "2026-10-11"), keep=1, env=ENV, client=client)
    assert send(archive(tmp_path, "2026-10-12"), keep=1, env=ENV, client=client)["stored"] == 2


def test_failures_are_reported_and_recorded(tmp_path):
    with pytest.raises(OffsiteError, match="did not accept the key"):
        send(archive(tmp_path, "2026-10-12"), env={**ENV, "COUNCILS_B2_APPLICATION_KEY": "wrong"},
             client=httpx.Client(transport=httpx.MockTransport(FakeB2())))
    status = json.loads((tmp_path / "offsite.json").read_text())
    assert status["ok"] is False and "wrong" not in json.dumps(status), "the key is never written down"
    with pytest.raises(OffsiteError, match="bucket"):
        send(archive(tmp_path, "2026-10-12"), env=ENV,
             client=httpx.Client(transport=httpx.MockTransport(FakeB2(bucket="someone-else"))))


def test_sites_sharing_a_bucket_keep_their_own_backups(tmp_path):
    """Where MPs Stand's backups in the same bucket are neither counted nor deleted."""
    b2 = FakeB2()
    b2.files["where-they-stand-2026-10-01.tar.gz"] = b"another site's"
    client = httpx.Client(transport=httpx.MockTransport(b2))
    for day in ("2026-10-11", "2026-10-12"):
        out = send(archive(tmp_path, day), keep=1, env=ENV, client=client)
    assert out["stored"] == 1 and "where-they-stand-2026-10-01.tar.gz" in b2.files


def test_backup_alerts(tmp_path):
    """As Where MPs Stand's admin page: a backup over two days old, or a failed off-site copy, is an error."""
    now = datetime.now(UTC)
    assert backup_alerts(tmp_path / "missing") == []
    assert "No backups" in backup_alerts(tmp_path, env=ENV)[0]["text"]
    a = archive(tmp_path, "2026-10-12")
    old = (now - timedelta(days=3)).timestamp()
    os.utime(a, (old, old))
    alerts = backup_alerts(tmp_path, env={})
    assert alerts[0]["level"] == "error" and "over two days ago" in alerts[0]["text"]
    assert "server only" in alerts[1]["text"]
    os.utime(a, None)
    assert "No off-site copy has been made yet" in backup_alerts(tmp_path, env=ENV)[0]["text"]
    (tmp_path / "offsite.json").write_text(json.dumps({"ok": False, "when": now.isoformat(), "error": "503"}))
    assert backup_alerts(tmp_path, env=ENV)[0]["level"] == "error"
    # a failed copy whose record has no usable time (null, or a number) is still reported, not an exception
    for when in (None, 1731400000):
        (tmp_path / "offsite.json").write_text(json.dumps({"ok": False, "when": when, "error": "503"}))
        alert = backup_alerts(tmp_path, env=ENV)[0]
        assert alert["level"] == "error" and alert["text"].endswith("): 503")
    stale = (now - timedelta(days=3)).isoformat()
    (tmp_path / "offsite.json").write_text(json.dumps({"ok": True, "when": stale}))
    assert "off-site copy was over two days ago" in backup_alerts(tmp_path, env=ENV)[0]["text"]
    (tmp_path / "offsite.json").write_text(json.dumps({"ok": True, "when": now.isoformat()}))
    assert backup_alerts(tmp_path, env=ENV) == []


def test_backup_check_command_exits_1_when_backups_are_stale(tmp_path, monkeypatch):
    from typer.testing import CliRunner

    from councils.cli import app

    for k in ENV:
        monkeypatch.delenv(k, raising=False)
    runner = CliRunner()
    assert runner.invoke(app, ["backup-check", "--in", str(tmp_path / "missing")]).exit_code == 1
    a = archive(tmp_path, "2026-10-12")
    ok = runner.invoke(app, ["backup-check", "--in", str(tmp_path)])
    assert ok.exit_code == 0 and "server only" in ok.output   # a warning, not a failure
    old = (datetime.now(UTC) - timedelta(days=3)).timestamp()
    os.utime(a, (old, old))
    stale = runner.invoke(app, ["backup-check", "--in", str(tmp_path)])
    assert stale.exit_code == 1 and "over two days ago" in stale.output
