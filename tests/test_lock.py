"""`councils index` and the server's update lock (decision 29): it takes the lock every site's nightly update takes,
and waits for it, so that the two never run together. On 19 and 20 November 2026 they did, for ten hours, and both
wrote the search index's state file."""

import fcntl
import os
import re
import subprocess
import sys
import time
from pathlib import Path

from typer.testing import CliRunner

from councils.cli import app
from councils.lock import ENV, SERVER_LOCK, lock_path

DEPLOY = Path(__file__).resolve().parents[1] / "deploy"


def _held(path: Path) -> int:
    """The lock taken as the update's unit takes it (`flock`, exclusive), on a file of its own opening."""
    fd = os.open(path, os.O_RDONLY | os.O_CREAT, 0o644)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    return fd


def test_index_waits_while_an_update_holds_the_lock_and_runs_when_it_ends(tmp_path):
    data, lock, said = tmp_path / "data", tmp_path / "update.lock", tmp_path / "stderr"
    env = {**os.environ, "COUNCILS_DATA_DIR": str(data), ENV: str(lock)}
    held = _held(lock)
    with open(said, "w") as err:
        index = subprocess.Popen([sys.executable, "-c", "from councils.cli import app; app()", "index"], env=env,
                                 stdout=subprocess.PIPE, stderr=err, text=True)
    try:
        deadline = time.monotonic() + 60
        while "Waiting for the server's update lock" not in said.read_text() and time.monotonic() < deadline:
            assert index.poll() is None, "index ran while the update held the lock"
            time.sleep(0.1)
        time.sleep(0.5)
        assert index.poll() is None                          # still waiting
        assert "Waiting for the server's update lock" in said.read_text()
        assert f"fuser -v {SERVER_LOCK}" in said.read_text()
        assert not (data / "index").exists()                 # nothing of the index written meanwhile
    finally:
        os.close(held)                                       # the update ends
    out, _ = index.communicate(timeout=120)
    assert index.returncode == 0 and out.strip() == "0 passages indexed"
    assert (data / "index").is_dir()


def test_no_update_can_take_the_lock_while_index_runs(tmp_path, monkeypatch):
    from councils.index.build import Indexer

    lock = tmp_path / "update.lock"
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(ENV, str(lock))
    tried = []

    def index_all(self, codes=None):
        try:
            os.close(_held(lock))                            # the update's `flock`, without waiting
            tried.append("taken")
        except BlockingIOError:
            tried.append("refused")
        return 0

    monkeypatch.setattr(Indexer, "index_all", index_all)
    done = CliRunner().invoke(app, ["index"])
    assert (done.exit_code, done.stdout.strip(), done.stderr) == (0, "0 passages indexed", "")   # no wait: free
    assert tried == ["refused"]
    os.close(_held(lock))                                    # and free again once index has finished


def test_index_refuses_when_the_lock_it_is_given_is_not_there(tmp_path, monkeypatch):
    """In the server's containers the lock is a mount: without it, index would guard nothing, so it does nothing."""
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv(ENV, str(tmp_path / "not-mounted" / "wheretheystand-update.lock"))
    done = CliRunner().invoke(app, ["index"])
    assert done.exit_code == 1 and done.stdout == ""
    assert done.stderr.startswith("error: The server's update lock could not be opened")
    assert "nothing was done" in done.stderr and f"touch {SERVER_LOCK}" in done.stderr
    assert not (tmp_path / "data" / "index").exists()


def test_where_the_lock_is_looked_for(tmp_path):
    assert lock_path({ENV: str(tmp_path / "x.lock")}) == (tmp_path / "x.lock", True)
    assert lock_path({ENV: ""}) == (None, False)             # set to nothing: no lock
    expected = (Path(SERVER_LOCK), False) if Path(SERVER_LOCK).parent.is_dir() else (None, False)
    assert lock_path({}) == expected


def test_the_containers_lock_is_the_one_the_update_unit_takes():
    """The update's unit takes the lock on the server; the containers see the same file through the mount."""
    unit = (DEPLOY / "councils-update.service").read_text()
    assert f"ExecStart=/usr/bin/flock {SERVER_LOCK} \\\n" in unit
    compose = (DEPLOY / "docker-compose.yml").read_text()
    mount = re.search(r"^      - (/\S+):(/\S+):ro$", compose, re.M)
    named = re.search(rf"^      {ENV}: (\S+)$", compose, re.M)
    assert mount and named
    assert mount.group(1) == str(Path(SERVER_LOCK).parent)
    assert named.group(1) == f"{mount.group(2)}/{Path(SERVER_LOCK).name}"
