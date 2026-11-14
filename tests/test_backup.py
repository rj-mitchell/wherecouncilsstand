"""Backups of the state database and putting one back: wts-core's (``wts_core.ops``), with this site's names, what
it keeps and its own lines (src/councils/state.py, src/councils/cli.py)."""

import gzip
import sqlite3

from typer.testing import CliRunner
from wts_core import ops
from wts_core.testing import FixedClock

from councils.cli import app
from councils.state import BACKUPS


def old_database(path, cost=0.12):
    """A state database as the site made it before the shared package: its own tables, and none of the package's."""
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute("CREATE TABLE usage (cost REAL)")
    con.execute("CREATE TABLE briefings (id TEXT PRIMARY KEY)")
    con.execute("INSERT INTO usage VALUES (?)", (cost,))
    con.commit()
    con.close()
    return path


def test_backup_copies_the_state_database_and_keeps_the_newest(tmp_path):
    db = old_database(tmp_path / "state.db")
    dest = tmp_path / "backups"
    for day in ("2026-10-01", "2026-10-02", "2026-10-03"):
        out = ops.make_backup(db, dest, BACKUPS, keep=2, clock=FixedClock(f"{day}T04:10:00+00:00"))
    assert sorted(p.name for p in dest.iterdir()) == ["councils-state-2026-10-02.sqlite.gz",
                                                     "councils-state-2026-10-03.sqlite.gz"]
    assert out.stat().st_mode & 0o777 == 0o600
    restored = tmp_path / "restored.db"
    restored.write_bytes(gzip.decompress(out.read_bytes()))
    assert sqlite3.connect(restored).execute("SELECT cost FROM usage").fetchone() == (0.12,)


def test_a_new_site_has_nothing_to_back_up(tmp_path, monkeypatch):
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(tmp_path / "data"))
    r = CliRunner().invoke(app, ["backup", "--to", str(tmp_path / "b")])
    assert r.exit_code == 0 and "nothing to back up" in r.output


def test_restore_puts_a_backup_back_and_keeps_what_it_replaced(tmp_path, monkeypatch):
    """New with the shared package: `councils restore`. A backup made before the move (the site's old tables and
    none of the package's) is taken too: on the day of the move it is the newest there is."""
    data = tmp_path / "data"
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(data))
    db = old_database(data / "state.db", cost=0.5)
    run = CliRunner().invoke
    made = run(app, ["backup", "--to", str(tmp_path / "b")])
    archive = next((tmp_path / "b").glob("councils-state-*.sqlite.gz"))
    assert made.exit_code == 0 and made.stdout.splitlines()[0] == f"backup: {archive}"
    con = sqlite3.connect(db)
    con.execute("UPDATE usage SET cost = 9.9")
    con.commit()
    con.close()
    # asked first; "no" changes nothing
    r = run(app, ["restore", str(archive)], input="n\n")
    assert r.exit_code == 1 and f"Replace {db} with {archive}? Stop the site first." in r.output
    assert sqlite3.connect(db).execute("SELECT cost FROM usage").fetchone() == (9.9,)
    r = run(app, ["restore", str(archive), "--yes"])
    assert r.exit_code == 0
    assert r.stdout == f"restored {db} from {archive}; the database it replaced is {db}.before-restore\n"
    assert sqlite3.connect(db).execute("SELECT cost FROM usage").fetchone() == (0.5,)
    assert sqlite3.connect(f"{db}.before-restore").execute("SELECT cost FROM usage").fetchone() == (9.9,)
    # the kept copy is never written over: a second restore is refused until it is moved or deleted
    r = run(app, ["restore", str(archive), "--yes"])
    assert r.exit_code == 1 and r.stderr.startswith("Not restored: ") and "move or delete it first" in r.stderr


def test_restore_refuses_what_is_not_this_sites_backup(tmp_path, monkeypatch):
    data = tmp_path / "data"
    monkeypatch.setenv("COUNCILS_DATA_DIR", str(data))
    old_database(data / "state.db")
    run = CliRunner().invoke
    # a sound database of some other kind
    other = tmp_path / "other.db"
    con = sqlite3.connect(other)
    con.execute("CREATE TABLE something (x)")
    con.commit()
    con.close()
    r = run(app, ["restore", str(other), "--yes"])
    assert r.exit_code == 1 and "is not a backup of this site's state database" in r.stderr
    # a sister site's, with the same tables but marked as its own (the mark wts-core's StateDB makes)
    sister = old_database(tmp_path / "sister.db")
    con = sqlite3.connect(sister)
    con.execute("CREATE TABLE wts_kv (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
    con.execute("INSERT INTO wts_kv VALUES ('site', 'wcs')")
    con.commit()
    con.close()
    r = run(app, ["restore", str(sister), "--yes"])
    assert r.exit_code == 1 and "another site's state database" in r.stderr and "'wcs'" in r.stderr
    # something that is no database at all, and a file that is not there
    (tmp_path / "junk.sqlite.gz").write_bytes(b"not gzip")
    for path in (tmp_path / "junk.sqlite.gz", tmp_path / "nowhere.sqlite.gz"):
        r = run(app, ["restore", str(path), "--yes"])
        assert r.exit_code == 1 and r.stderr.startswith("Not restored: "), path
    assert not (data / "state.db.before-restore").exists()                # nothing was replaced
