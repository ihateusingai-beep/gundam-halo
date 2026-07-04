"""Single-instance lock file for the Gundam Halo backend.

Prevents two backend processes from running at the same time
against the same `~/.gundam-halo/` config dir. The
launchd-supervised daemon (Track 2 / Sprint 26 §4.2) and the
manual dev mode (`./run.sh`) both call `acquire()` on startup
so that whichever loses the race exits cleanly with a clear
error pointing at the winner's PID.

The lock file lives at `<halo_home>/.backend.lock` by default
(overridable for tests). Its contents are a single line of
`pid=<n>\\nhost=<hostname>\\nstarted_at=<iso8601>` so a
human can `cat` it to see who holds the lock.

Concurrency:
- POSIX (Linux + macOS): `fcntl.flock(LOCK_EX | LOCK_NB)`.
  This is the same primitive the `app.memory.user_memory`
  module uses — non-blocking, kernel-managed, automatically
  released on process death. Cross-process safe.
- Windows: `msvcrt.locking()` with a non-blocking attempt.
  The current CI / dev workflow is macOS-only, but the import
  is wrapped so `import` itself never fails on Windows.

Stale-lock recovery:
- If the file exists AND we can't acquire the lock AND the
  recorded PID is dead (no `/proc/<pid>` on Linux, no
  `kill -0` on macOS, no `tasklist` on Windows), we steal
  the lock and emit a warning. This handles the "process
  crashed without releasing" case.
- We do NOT steal from a live PID — that's the
  "two processes accidentally running" case and the
  caller should sort it out.

Design note (v2, post-verifier-feedback):
The first cut of this module had two bugs:
1. A "same-process early-return" that returned `existing`
   when the recorded PID matched our own. That short-circuit
   masked the real kernel flock semantics — tests that opened
   two fds in the same process never actually exercised the
   flock path.
2. The acquired fd was closed on `acquire()`'s return (only
   the `except` path closed it; the success path leaked it,
   but more importantly, no fd was held across the function
   boundary). This meant the kernel flock was released as
   soon as `acquire()` returned, so subsequent `acquire()`
   calls in the same process ALWAYS succeeded — the lock
   was effectively per-call, not per-process.

The v2 design fixes both:
- The fd is held in a module-level registry (`_HELD_LOCKS`)
  keyed by absolute path. `acquire()` puts the fd in the
  registry; `release()` finds it and closes it. The
  `lockfile()` context manager uses the same registry.
- The same-process early-return is REMOVED. The kernel
  flock is the sole arbiter. A second `acquire()` in the
  same process (without an intervening `release()`) fails
  with `LockHeldError` because the registry already holds
  the fd with the flock.
- A real cross-process test
  (`test_subprocess_acquire_blocks_parent_acquire`) uses
  `subprocess.Popen` to spawn a child Python that holds
  the lock for several seconds, then the parent tries to
  acquire and must get `LockHeldError`. This is the only
  test that proves the cross-process contract end-to-end.
"""

from __future__ import annotations

import errno
import logging
import os
import socket
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Iterator, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Layout constants
# ---------------------------------------------------------------------------

# Path relative to halo_home where the lock file lives. Hidden
# (dotfile) so it doesn't clutter `ls ~/.gundam-halo/`.
LOCK_FILENAME = ".backend.lock"

# Format of the payload. We use plain text (not JSON) so a
# human can `cat` the file and immediately understand it.
# Format:
#   pid=<n>
#   host=<hostname>
#   started_at=<iso8601-utc>
PID_PREFIX = "pid="
HOST_PREFIX = "host="
STARTED_PREFIX = "started_at="


# ---------------------------------------------------------------------------
# Module-level held-lock registry
# ---------------------------------------------------------------------------
#
# `acquire()` opens an fd, takes a flock on it, and STORES
# the fd in this dict keyed by absolute path. The flock is
# only released when `release()` finds the fd here and
# closes it. This makes the lock per-process (not
# per-function-call) and is what the cross-process + same-
# process contention tests rely on.
#
# In CPython, the dict operations are thread-safe at the
# bytecode level. We don't claim full thread-safety for
# concurrent acquire() from multiple threads of the same
# process — if you need that, use a threading.Lock around
# the acquire/release pair. The realistic call pattern is
# one acquire per process (the lifespan startup).

_HELD_LOCKS: dict[str, IO[str]] = {}


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class LockFileError(RuntimeError):
    """Base class for lock file failures."""


class LockHeldError(LockFileError):
    """Another live process (or the same process, no release) holds the lock."""

    def __init__(self, pid: int, host: str, path: Path) -> None:
        self.pid = pid
        self.host = host
        self.path = path
        super().__init__(
            f"Backend already running (PID {pid}); "
            f"another instance holds {path}. "
            f"If this is stale, run `rm {path}`."
        )


class LockFileReadError(LockFileError):
    """The lock file exists but can't be parsed."""

    def __init__(self, path: Path, raw: str) -> None:
        self.path = path
        self.raw = raw
        super().__init__(
            f"Lock file at {path} is malformed: {raw!r}. "
            f"Inspect with `cat {path}` and remove if stale."
        )


# ---------------------------------------------------------------------------
# Data class
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class LockInfo:
    """Metadata for whoever currently holds the lock."""

    pid: int
    host: str
    started_at: str  # ISO 8601 UTC

    def render(self) -> str:
        """Render the lock file payload (single string, no trailing newline).

        The trailing newline is added on write.
        """
        return (
            f"{PID_PREFIX}{self.pid}\n"
            f"{HOST_PREFIX}{self.host}\n"
            f"{STARTED_PREFIX}{self.started_at}"
        )

    @classmethod
    def parse(cls, raw: str) -> "LockInfo":
        """Parse the lock file payload. Raises LockFileReadError on failure."""
        pid: Optional[int] = None
        host: Optional[str] = None
        started_at: Optional[str] = None
        for line in raw.splitlines():
            line = line.strip()
            if not line:
                continue
            if line.startswith(PID_PREFIX):
                try:
                    pid = int(line[len(PID_PREFIX):])
                except ValueError as e:
                    raise LockFileReadError(Path("?"), raw) from e
            elif line.startswith(HOST_PREFIX):
                host = line[len(HOST_PREFIX):]
            elif line.startswith(STARTED_PREFIX):
                started_at = line[len(STARTED_PREFIX):]
        if pid is None or host is None or started_at is None:
            raise LockFileReadError(Path("?"), raw)
        return cls(pid=pid, host=host, started_at=started_at)


# ---------------------------------------------------------------------------
# PID liveness check
# ---------------------------------------------------------------------------


def _is_pid_alive(pid: int) -> bool:
    """Return True iff the given PID is alive on this machine.

    POSIX (Linux + macOS): `os.kill(pid, 0)` — succeeds on
    live processes, raises `ProcessLookupError` on dead ones,
    raises `PermissionError` if we don't own the process
    (still alive though).
    Windows: best-effort `os.kill` (the `msvcrt` path is
    secondary; we don't have a true Windows test env).
    """
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # Not ours, but it IS running.
        return True
    except OSError as e:
        # Some platforms raise OSError(errno.EPERM) for "exists but
        # not ours". Treat as alive.
        if e.errno in (errno.EPERM, errno.EACCES):
            return True
        return False


# ---------------------------------------------------------------------------
# Cross-platform fcntl/msvcrt wrapper
# ---------------------------------------------------------------------------


def _try_lock_exclusive(fd: int) -> bool:
    """Try to acquire an exclusive lock on `fd` without blocking.

    Returns True on success, False if another process (or the
    same process on a different fd) holds the lock.
    Raises OSError on platform errors.
    """
    if sys.platform == "win32":
        # Windows: use msvcrt.locking with LK_NBLCK. We lock 1 byte.
        import msvcrt  # type: ignore[import-not-found]

        try:
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    # POSIX (Linux + macOS): fcntl.flock
    import fcntl  # local import so the module loads on Windows

    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError as e:
        if e.errno in (errno.EWOULDBLOCK, errno.EAGAIN):
            return False
        raise


def _unlock(fd: int) -> None:
    """Release the lock on `fd`. Safe to call even if not held."""
    if sys.platform == "win32":
        # On Windows the lock is released automatically when the
        # file is closed. No-op here.
        return
    import fcntl

    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def default_lock_path(halo_home: Optional[Path] = None) -> Path:
    """Return the default lock file path: `<halo_home>/.backend.lock`.

    `halo_home` defaults to `$HALO_HOME` or `~/.gundam-halo/`.
    Sprint 56 R1: route through `app.paths.halo_home()` for the
    canonical env-var resolution.
    """
    if halo_home is None:
        from app.paths import halo_home as _halo_home
        halo_home = _halo_home()
    return Path(halo_home) / LOCK_FILENAME


def _read_lock_payload(path: Path) -> Optional[LockInfo]:
    """Read the lock file payload, or None if the file doesn't exist / is empty."""
    if not path.exists():
        return None
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return None
    try:
        return LockInfo.parse(raw)
    except LockFileReadError:
        # Malformed file — treat as "no known holder". The caller
        # can decide whether to warn + steal.
        return None


def acquire(path: Optional[Path] = None) -> LockInfo:
    """Acquire the backend lock file. Returns the LockInfo on success.

    On conflict (another fd, same or different process, holds
    the lock), raises `LockHeldError`. The caller (usually
    `create_app()` lifespan startup) is expected to exit
    cleanly on `LockHeldError` so the user sees the clear
    error message.

    The acquired fd is stored in the module-level registry
    keyed by absolute path. It is released by `release(path)`
    or when the process dies (kernel auto-cleanup). A second
    `acquire()` on the same path in the same process (without
    an intervening `release()`) will FAIL with `LockHeldError`.

    Args:
        path: Lock file path. Defaults to `default_lock_path()`.

    Stale-lock recovery: if the file exists AND we can't
    acquire the lock AND the recorded PID is dead on this
    machine, we steal the lock and emit a warning log line.
    This handles the "previous process crashed without
    releasing" case.
    """
    if path is None:
        path = default_lock_path()
    path = Path(path).resolve()
    key = str(path)

    # Ensure parent dir exists. If the user has never launched
    # the backend, the halo_home may not even exist yet.
    path.parent.mkdir(parents=True, exist_ok=True)

    # Ensure the file exists. We use "a+" (append + read) which
    # creates the file if missing.
    if not path.exists():
        path.touch()
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    info = LockInfo(
        pid=os.getpid(),
        host=socket.gethostname(),
        started_at=datetime.now(timezone.utc).isoformat(),
    )

    # Open the file in r+ mode. The file is guaranteed to exist
    # after the touch above. Each acquire() call opens a new fd;
    # the kernel treats the new fd's OFD as independent of any
    # previously opened fd. The flock on the new fd will fail
    # with EWOULDBLOCK if any other fd (in this process or
    # another) holds the lock — same-process contention is
    # handled by the kernel, not by the module-level registry.
    fp = path.open("r+", encoding="utf-8")
    try:
        # Read the file's current payload BEFORE trying the flock,
        # so that on a conflict we can report the holder's PID.
        existing = _read_lock_payload(path)

        # Try to acquire the lock first. If it succeeds, we own
        # the lock and we write our info.
        got = _try_lock_exclusive(fp.fileno())
        if got:
            # We have the lock. Truncate the file (in case a
            # previous holder wrote to it) and write our info.
            fp.truncate(0)
            fp.seek(0)
            fp.write(info.render())
            fp.flush()
            # Store the fd in the module-level registry so the
            # lock survives past this function's return. The
            # kernel-level flock is held on this fd; closing
            # it would release the lock.
            _HELD_LOCKS[key] = fp
            logger.debug("Acquired lock at %s (pid=%d)", path, info.pid)
            return info

        # Lock is held by someone else. Decide whether to steal
        # (stale recovery) or report a conflict.
        if existing is not None and not _is_pid_alive(existing.pid):
            logger.warning(
                "Stale lock file at %s (PID %d is dead); stealing lock",
                path,
                existing.pid,
            )
            # Try to re-acquire after a short backoff (the
            # kernel reaps the OFD when the process dies, but
            # it may not be instantaneous).
            stolen = False
            for _attempt in range(20):
                fp.close()
                fp = path.open("r+", encoding="utf-8")
                if _try_lock_exclusive(fp.fileno()):
                    stolen = True
                    break
                time.sleep(0.05)
            if not stolen:
                # Still can't get the lock. Fall through to
                # LockHeldError.
                fp.close()
                raise LockHeldError(
                    pid=existing.pid,
                    host=existing.host,
                    path=path,
                )
            # Truncate the stale payload + write our info
            fp.truncate(0)
            fp.seek(0)
            fp.write(info.render())
            fp.flush()
            _HELD_LOCKS[key] = fp
            return info

        # Lock is held by another live process (or by us on a
        # different fd, but the registry check above should
        # have caught that — if not, it's a true conflict).
        # Close our fd and report.
        fp.close()
        if existing is not None:
            raise LockHeldError(
                pid=existing.pid,
                host=existing.host,
                path=path,
            )
        # Can't even read the holder info. Best-effort.
        raise LockHeldError(
            pid=-1,
            host="<unknown>",
            path=path,
        )
    except BaseException:
        # On any failure (LockHeldError, etc.), close the fd if
        # it wasn't stored in the registry. The except block
        # catches BaseException so it covers LockHeldError
        # raised above. Note: `_HELD_LOCKS` was NOT set on the
        # failure path, so this close is the right behavior.
        try:
            fp.close()
        except Exception:
            pass
        raise


def release(path: Optional[Path] = None) -> None:
    """Release the lock file.

    Looks up the fd in the module-level registry (keyed by
    absolute path) and closes it. Closing the fd releases
    the kernel flock. The file content is NOT deleted — the
    last holder's PID info persists for forensics. Use
    `force_release()` to actually delete the file.

    Idempotent: if the lock is not held (registry miss or
    file gone), this is a no-op.
    """
    if path is None:
        path = default_lock_path()
    path = Path(path).resolve()
    key = str(path)
    fp = _HELD_LOCKS.pop(key, None)
    if fp is None:
        return
    try:
        _unlock(fp.fileno())
    except Exception:
        pass
    try:
        fp.close()
    except Exception:
        pass
    logger.debug("Released lock at %s", path)


@contextmanager
def lockfile(path: Optional[Path] = None) -> Iterator[LockInfo]:
    """Context manager: acquire on enter, release on exit.

    Usage:
        from app.core.lockfile import lockfile, LockHeldError

        try:
            with lockfile() as info:
                ...  # run backend
        except LockHeldError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)
    """
    info = acquire(path=path)
    try:
        yield info
    finally:
        release(path=path)


# ---------------------------------------------------------------------------
# Diagnostics (used by /api/health-style probes; not wired in this sprint)
# ---------------------------------------------------------------------------


def read_holder(path: Optional[Path] = None) -> Optional[LockInfo]:
    """Read who currently holds the lock, or None if the file is gone.

    Does NOT acquire the lock. Safe to call from a health probe.
    Note: this only reports the file's content — it does NOT
    verify the lock is currently held. A process may have
    crashed and left the file behind. Use `_is_pid_alive` on
    the returned `pid` to check liveness.
    """
    if path is None:
        path = default_lock_path()
    return _read_lock_payload(Path(path))


def force_release(path: Optional[Path] = None) -> bool:
    """Delete the lock file unconditionally. Returns True if a file was removed.

    Intended for CLI / manual recovery (`rm ~/.gundam-halo/.backend.lock`).
    Test fixtures also use this between tests. The caller is expected
    to know what they're doing — this is a sledgehammer.

    Note: deleting the file does NOT release any kernel flock
    held by another process on the file (the kernel cleans up
    the flock on process death). After `force_release()`, the
    file is gone and a new `acquire()` will create a fresh one.
    """
    if path is None:
        path = default_lock_path()
    path = Path(path)
    if not path.exists():
        return False
    # Also drop from the registry, in case WE are the holder
    # and we're force-releasing our own lock.
    _HELD_LOCKS.pop(str(path.resolve()), None)
    path.unlink()
    return True

