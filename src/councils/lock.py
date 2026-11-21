"""The server's update lock, for the data commands run by hand (decision 29).

Every site's nightly update on the charity's shared server runs under one lock, ``/var/lock/wheretheystand-update.lock``
(family/GLOSSARY.md and family/OPERATIONS.md in the charity's repository): its systemd unit wraps the command in
``flock``, so a second update waits for the first to finish. ``councils index`` takes the same lock in the same way,
an exclusive ``flock`` that waits, so that it never runs beside an update. On 19 and 20 November 2026 an index run by
hand and the nightly update ran together for ten hours and both wrote the search index's state file.

The commands run in a container, which cannot see the server's ``/var/lock`` unless it is given it:
deploy/docker-compose.yml mounts it, read-only, at ``/run/wheretheystand-lock``, and names the lock file there in
``COUNCILS_UPDATE_LOCK``. Where that variable is set, the lock must be there, or the command refuses (the folder isn't
mounted, say). Where it is not set (a developer's machine), the lock is taken at its server path if that folder
exists, and the command carries on without it if not. Set it to nothing to take no lock.

The lock is released when the command ends, however it ends: the kernel lets go of it when the process exits.
"""

from __future__ import annotations

import fcntl
import os
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from pathlib import Path

# the lock's name on the server, as every site's update unit and the family's documents give it
SERVER_LOCK = "/var/lock/wheretheystand-update.lock"
ENV = "COUNCILS_UPDATE_LOCK"


class LockUnavailable(RuntimeError):
    """The lock the settings name can't be opened, so the command does nothing rather than run unguarded."""


def lock_path(env: Mapping[str, str] | None = None) -> tuple[Path | None, bool]:
    """Where the lock is, and whether it was named (so must be there). ``None`` when there is no lock to take."""
    env = os.environ if env is None else env
    if ENV in env:
        named = env[ENV].strip()
        return (Path(named), True) if named else (None, False)
    default = Path(SERVER_LOCK)
    return (default, False) if default.parent.is_dir() else (None, False)


def _open(path: Path) -> int:
    """The lock file, opened for reading as ``flock`` opens it, made first if it isn't there yet (a read-only mount
    of a folder can open an existing file but not make one)."""
    try:
        return os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return os.open(path, os.O_RDONLY | os.O_CREAT, 0o644)


@contextmanager
def update_lock(say: Callable[[str], None], env: Mapping[str, str] | None = None) -> Iterator[None]:
    """Hold the server's update lock while the block runs, waiting for it if another job has it, and saying so
    through ``say`` once."""
    path, named = lock_path(env)
    if path is None:
        yield
        return
    try:
        fd = _open(path)
    except OSError as exc:
        if not named:
            yield              # not a server: nothing else takes the lock here
            return
        raise LockUnavailable(
            f"The server's update lock could not be opened at {path} ({exc.strerror or exc}), so nothing was done. "
            f"In the server's containers it is {SERVER_LOCK} on the server, mounted by deploy/docker-compose.yml; "
            f"if the file is not there yet (after a restart of the server, before any update has run), make it "
            f"there with: touch {SERVER_LOCK}") from exc
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            say(f"Waiting for the server's update lock ({SERVER_LOCK}): an update or another data job is running, "
                f"on this site or another. This carries on by itself when it finishes, which can take hours; "
                f"Ctrl-C stops waiting. To see who holds it, on the server: fuser -v {SERVER_LOCK}")
            fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)
