"""Portable advisory writer lock for canonical ledger mutations.

The lock file is a sibling of the canonical ledger, an ignored local artifact
(see the repository `.gitignore`). The advisory lock covers load,
expected-revision comparison, complete candidate validation and atomic
replacement; it is acquired blocking and always released in failure paths.
"""

import contextlib
import os

from . import RequirementsError

try:
    import fcntl
except ImportError:  # pragma: no cover - Windows path
    fcntl = None

try:
    import msvcrt
except ImportError:
    msvcrt = None


def lock_path_for(ledger_path):
    return str(ledger_path) + ".lock"


def _lock_posix(fd):
    fcntl.flock(fd, fcntl.LOCK_EX)


def _lock_windows(fd):
    retries = 0
    while True:
        try:
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            return
        except OSError:
            retries += 1
            if retries >= 20:
                raise


def _acquire(fd):
    if fcntl is not None:
        _lock_posix(fd)
    elif msvcrt is not None:  # pragma: no cover - Windows path
        _lock_windows(fd)
    else:  # pragma: no cover
        raise RequirementsError(
            "storage-write-failed",
            "No advisory locking primitive available on this platform.",
            {"lock": "fcntl/msvcrt"},
        )


@contextlib.contextmanager
def writer_lock(ledger_path):
    """Hold the canonical ledger writer lock for the enclosed critical section.

    Raises ``RequirementsError("storage-write-failed")`` when the lock file
    cannot be created or acquired. The lock is released (never unlink-ed) when
    the context exits, including on error paths.
    """
    path = lock_path_for(ledger_path)
    try:
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o666)
    except OSError as exc:
        raise RequirementsError(
            "storage-write-failed",
            "Cannot create the advisory writer lock sibling.",
            {"lock": path, "reason": str(exc)},
        ) from exc
    try:
        try:
            _acquire(fd)
        except OSError as exc:
            raise RequirementsError(
                "storage-write-failed",
                "Cannot acquire the advisory writer lock.",
                {"lock": path, "reason": str(exc)},
            ) from exc
        try:
            yield path
        finally:
            if fcntl is not None:
                try:
                    fcntl.flock(fd, fcntl.LOCK_UN)
                except OSError:
                    pass
    finally:
        os.close(fd)
