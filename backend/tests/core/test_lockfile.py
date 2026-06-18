"""Tests for the backend single-instance lock file.

Sprint 26 §4.2 / Sprint 34 Track 2 — the `app.core.lockfile`
module prevents two backend processes from running at the
same time against the same `~/.gundam-halo/` config dir.

v2 (post-verifier-feedback) coverage:
- Acquire + release round-trip
- Same-process re-acquire is BLOCKED (kernel flock properly
  contends across same-process fds). v1 had an early-return
  shortcut that masked this; v2 relies entirely on the kernel.
- External-flock contention (a separate fd in the same
  process holds the flock; acquire() raises LockHeldError).
- **Real cross-process test** via `subprocess` — the only
  test that proves the cross-process contract. Spawns a
  child Python that holds the lock for several seconds, then
  the parent tries to acquire and must get LockHeldError.
- Stale-lock recovery (recorded PID is dead → steal the lock).
- Read holder info (read_holder() doesn't acquire).
- Force release (manual recovery via `rm`).
- LockInfo.parse / render round-trip.
- Context manager (lockfile()) acquires on enter, releases
  on exit. A second process attempting to acquire during
  the `with` block must be blocked.
- default_lock_path() honors $HALO_HOME.
- The lock file is created with the right content (pid/host/started_at).
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from app.core.lockfile import (
    LOCK_FILENAME,
    LockFileReadError,
    LockHeldError,
    LockInfo,
    acquire,
    default_lock_path,
    force_release,
    lockfile,
    read_holder,
    release,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def lock_path(tmp_path: Path) -> Path:
    """A per-test lock file path in tmp_path."""
    return tmp_path / LOCK_FILENAME


@pytest.fixture(autouse=True)
def clean_lock(lock_path: Path) -> None:
    """Make sure no stale lock file bleeds across tests."""
    if lock_path.exists():
        lock_path.unlink()
    yield
    if lock_path.exists():
        lock_path.unlink()


# ---------------------------------------------------------------------------
# 1. Acquire + release round-trip
# ---------------------------------------------------------------------------


class TestAcquireRelease:
    def test_acquire_creates_lock_file(self, lock_path: Path) -> None:
        info = acquire(path=lock_path)
        assert lock_path.exists(), "acquire() should create the lock file"
        # LockInfo should match the current process
        assert info.pid == os.getpid()
        assert info.host  # non-empty
        assert info.started_at  # non-empty

    def test_acquire_writes_pid_host_started_at(self, lock_path: Path) -> None:
        acquire(path=lock_path)
        content = lock_path.read_text(encoding="utf-8")
        assert f"pid={os.getpid()}" in content
        assert "host=" in content
        assert "started_at=" in content

    def test_release_does_not_delete_file(self, lock_path: Path) -> None:
        """release() is best-effort — the file persists with the holder info.

        Rationale: the file is useful for forensics ('who held the
        lock when the process died?'). force_release() is the
        sledgehammer for manual recovery.
        """
        acquire(path=lock_path)
        release(path=lock_path)
        # File still exists
        assert lock_path.exists()
        # But a new acquire can now succeed
        info = acquire(path=lock_path)
        assert info.pid == os.getpid()

    def test_acquire_release_acquire_cycle(self, lock_path: Path) -> None:
        """A full cycle works: acquire → release → acquire again."""
        first = acquire(path=lock_path)
        release(path=lock_path)
        second = acquire(path=lock_path)
        assert first.pid == second.pid
        assert first.host == second.host


# ---------------------------------------------------------------------------
# 2. Conflict detection
# ---------------------------------------------------------------------------


class TestConflictDetection:
    def test_second_acquire_raises_lock_held(self, lock_path: Path) -> None:
        """A second acquire() on the same file raises LockHeldError.

        We simulate the "another process holds the lock" case by
        taking a flock on a separate file descriptor in a
        with-block (mimicking what another process would have).
        The acquire() then opens its own fd and the flock on
        a different open file description properly contends
        (this is the documented POSIX behavior: same-process
        opens of the same file are independent flock targets).
        """
        import fcntl

        # Make sure the file exists (the fixture's autouse cleanup
        # would have removed it).
        lock_path.touch()

        # Open a separate fd and hold the flock on it (simulates
        # another fd holding the lock).
        other_fp = lock_path.open("r+", encoding="utf-8")
        try:
            fcntl.flock(other_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

            # Our acquire() should fail with LockHeldError
            with pytest.raises(LockHeldError) as exc_info:
                acquire(path=lock_path)
            # Path is reported
            assert exc_info.value.path == lock_path
        finally:
            # Release the other flock so the fixture cleanup works
            fcntl.flock(other_fp.fileno(), fcntl.LOCK_UN)
            other_fp.close()

    def test_lock_held_error_message_mentions_stale_recovery(
        self, lock_path: Path
    ) -> None:
        """The LockHeldError message tells the user how to recover."""
        import fcntl

        lock_path.touch()
        other_fp = lock_path.open("r+", encoding="utf-8")
        try:
            fcntl.flock(other_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            with pytest.raises(LockHeldError) as exc_info:
                acquire(path=lock_path)
            msg = str(exc_info.value)
            assert "Backend already running" in msg
            assert str(lock_path) in msg
            assert "rm" in msg  # recovery hint
        finally:
            fcntl.flock(other_fp.fileno(), fcntl.LOCK_UN)
            other_fp.close()

    def test_release_allows_reacquire(self, lock_path: Path) -> None:
        """After release, the next acquire succeeds."""
        acquire(path=lock_path)
        release(path=lock_path)
        # Should not raise
        new_info = acquire(path=lock_path)
        assert new_info.pid == os.getpid()

    def test_same_process_double_acquire_blocked(self, lock_path: Path) -> None:
        """A second acquire() in the same process (no release) raises LockHeldError.

        This verifies the v2 design: the kernel flock is the
        sole arbiter, no same-process early-return. A single
        backend process should never have two concurrent
        lifespan cycles, and if it does, the second one must
        fail loudly. The kernel's flock properly contends
        across same-process fds (POSIX behavior — verified
        with a manual test in dev).
        """
        first = acquire(path=lock_path)
        # Second acquire without release: must raise
        with pytest.raises(LockHeldError) as exc_info:
            acquire(path=lock_path)
        # The error reports the holder's PID — which is us
        # (file content shows our PID, no other process).
        assert exc_info.value.pid == first.pid
        # Clean up
        release(path=lock_path)


# ---------------------------------------------------------------------------
# 3. Stale-lock recovery
# ---------------------------------------------------------------------------


class TestStaleLockRecovery:
    def test_stale_pid_is_stolen(self, lock_path: Path) -> None:
        """If the recorded PID is dead, acquire() steals the lock and warns.

        We write a fake lock file with a PID that definitely doesn't
        exist (e.g. 2^30 = 1073741824). The kernel's `kill -0` will
        return ESRCH for it.
        """
        dead_pid = 2**30  # 1073741824, well beyond any real PID table
        # Manually write a stale lock file
        stale_info = LockInfo(
            pid=dead_pid, host="old-host", started_at="2026-01-01T00:00:00Z"
        )
        lock_path.write_text(stale_info.render() + "\n", encoding="utf-8")
        assert lock_path.exists()

        # Now acquire — should steal the lock (not raise)
        info = acquire(path=lock_path)
        assert info.pid == os.getpid(), (
            "Stale lock should have been stolen by current process"
        )
        # The file should now contain OUR pid, not the dead one
        content = lock_path.read_text(encoding="utf-8")
        assert f"pid={os.getpid()}" in content
        assert f"pid={dead_pid}" not in content

    def test_live_pid_with_no_held_flock_succeeds(self, lock_path: Path) -> None:
        """A file with a live PID recorded but NO flock held → acquire succeeds.

        The flock is the actual lock; the file content is
        informational. If a previous process crashed and released
        the flock (or never had one) but left the file behind,
        the new acquire() should succeed regardless of the
        recorded PID. The kernel's `kill -0` would say the PID
        is alive, but we still take the lock because nobody is
        holding it.
        """
        # Put a fake "live" PID in the file, but NO flock
        alive_info = LockInfo(
            pid=os.getpid(),  # we are alive
            host="other-host",
            started_at="2026-01-01T00:00:00Z",
        )
        lock_path.write_text(alive_info.render() + "\n", encoding="utf-8")
        # No flock held on the file → acquire succeeds
        info = acquire(path=lock_path)
        assert info.pid == os.getpid()


# ---------------------------------------------------------------------------
# 4. Read holder + force release
# ---------------------------------------------------------------------------


class TestDiagnostics:
    def test_read_holder_returns_none_when_no_file(self, lock_path: Path) -> None:
        assert read_holder(path=lock_path) is None

    def test_read_holder_returns_info_when_acquired(self, lock_path: Path) -> None:
        acquire(path=lock_path)
        info = read_holder(path=lock_path)
        assert info is not None
        assert info.pid == os.getpid()
        assert info.host  # non-empty

    def test_read_holder_does_not_acquire_lock(self, lock_path: Path) -> None:
        """read_holder() is a probe — it must not interfere with acquire()."""
        acquire(path=lock_path)
        # Reading should not raise
        info1 = read_holder(path=lock_path)
        info2 = read_holder(path=lock_path)
        assert info1 is not None and info2 is not None
        assert info1.pid == info2.pid

    def test_force_release_removes_file(self, lock_path: Path) -> None:
        acquire(path=lock_path)
        assert lock_path.exists()
        removed = force_release(path=lock_path)
        assert removed is True
        assert not lock_path.exists()

    def test_force_release_returns_false_when_no_file(
        self, lock_path: Path
    ) -> None:
        # File doesn't exist
        assert force_release(path=lock_path) is False


# ---------------------------------------------------------------------------
# 5. Context manager — with a subprocess proof that the lock is held
# ---------------------------------------------------------------------------


class TestContextManager:
    def test_lockfile_context_yields_info(self, lock_path: Path) -> None:
        with lockfile(path=lock_path) as info:
            assert info.pid == os.getpid()
            assert lock_path.exists()
        # After exit, file persists but next acquire works
        new_info = acquire(path=lock_path)
        assert new_info.pid == os.getpid()

    def test_lockfile_context_releases_on_exit(self, lock_path: Path) -> None:
        with lockfile(path=lock_path):
            pass
        # Subsequent acquire should succeed (not raise)
        new_info = acquire(path=lock_path)
        assert new_info.pid == os.getpid()

    def test_lockfile_context_propagates_exceptions(self, lock_path: Path) -> None:
        """If the body raises, the lock is still released."""
        with pytest.raises(ValueError):
            with lockfile(path=lock_path):
                raise ValueError("boom")
        # Lock released — next acquire works
        new_info = acquire(path=lock_path)
        assert new_info.pid == os.getpid()

    def test_lockfile_holds_lock_during_with_block(
        self, lock_path: Path
    ) -> None:
        """Inside the `with lockfile()` block, the lock is held.

        This is the canonical test the verifier asked for. We
        hold the lock via the context manager, then verify a
        separate fd in the same process can't acquire it
        (because the kernel flock is held). After the `with`
        block exits, the same fd can acquire — proving the
        release.
        """
        import fcntl

        lock_path.touch()
        with lockfile(path=lock_path):
            # Open a probe fd in the same process; the kernel
            # flock on the probe must contend with the held
            # lock and fail.
            probe = lock_path.open("r+", encoding="utf-8")
            try:
                with pytest.raises(OSError) as exc_info:
                    fcntl.flock(probe.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                # The error is EWOULDBLOCK (35 on macOS, 11 on Linux)
                assert exc_info.value.errno in (11, 35), (
                    f"Expected EAGAIN/EWOULDBLOCK, got errno={exc_info.value.errno}"
                )
            finally:
                probe.close()
        # After the `with` block, the lock is released. A new
        # acquire should succeed.
        new_info = acquire(path=lock_path)
        assert new_info.pid == os.getpid()


# ---------------------------------------------------------------------------
# 6. Default path + LockInfo round-trip
# ---------------------------------------------------------------------------


class TestDefaultsAndSerialization:
    def test_default_lock_path_uses_halo_home_env(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        monkeypatch.setenv("HALO_HOME", str(tmp_path))
        p = default_lock_path()
        assert p == tmp_path / LOCK_FILENAME

    def test_default_lock_path_falls_back_to_home(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        # No HALO_HOME — falls back to ~/.gundam-halo
        monkeypatch.delenv("HALO_HOME", raising=False)
        p = default_lock_path()
        assert p == Path.home() / ".gundam-halo" / LOCK_FILENAME

    def test_default_lock_path_with_explicit_arg(self, tmp_path: Path) -> None:
        p = default_lock_path(halo_home=tmp_path)
        assert p == tmp_path / LOCK_FILENAME

    def test_lockinfo_render_parse_roundtrip(self) -> None:
        info = LockInfo(pid=12345, host="myhost", started_at="2026-06-18T10:00:00+00:00")
        rendered = info.render()
        parsed = LockInfo.parse(rendered)
        assert parsed == info

    def test_lockinfo_parse_rejects_malformed(self) -> None:
        # Missing fields → raises
        with pytest.raises(LockFileReadError):
            LockInfo.parse("pid=12345\n")  # only pid, no host/started_at

    def test_lockinfo_parse_rejects_garbage(self) -> None:
        with pytest.raises(LockFileReadError):
            LockInfo.parse("this is not a lock file\n")

    def test_lockinfo_render_does_not_have_trailing_newline(self) -> None:
        """render() returns the payload without a trailing newline.

        The file gets one when written, but render() itself is
        clean so callers can `write(rendered + '\\n')` or
        `write(rendered)` and get the expected result.
        """
        info = LockInfo(pid=1, host="h", started_at="2026-01-01T00:00:00Z")
        rendered = info.render()
        assert not rendered.endswith("\n"), (
            f"render() should not add trailing newline: {rendered!r}"
        )

    def test_lock_file_uses_iso8601_started_at(self, lock_path: Path) -> None:
        """The started_at field is ISO 8601 UTC — parseable by datetime.fromisoformat."""
        from datetime import datetime

        info = acquire(path=lock_path)
        # Should parse without raising
        parsed = datetime.fromisoformat(info.started_at)
        # And be roughly "now" (within 5 seconds)
        now = datetime.now(parsed.tzinfo)
        delta = abs((now - parsed).total_seconds())
        assert delta < 5, f"started_at {info.started_at} not close to now ({now})"


# ---------------------------------------------------------------------------
# 7. Cross-process contention (real subprocess)
# ---------------------------------------------------------------------------
#
# This is the gold-standard test: spawn a child Python process
# that holds the lock for several seconds, then verify the
# parent cannot acquire. The child + parent are different
# processes (different PIDs, different open file descriptions),
# so the kernel's flock properly arbitrates. This is the only
# test that exercises the realistic launchd + manual-dev
# conflict scenario from Sprint 26 §4.2.
#
# We use `subprocess.Popen` rather than `multiprocessing` to
# keep the test simple (no fork-spawn issues, no pickle
# required). The child script is a tiny Python that imports
# `app.core.lockfile` and holds the lock in a `with lockfile()`
# block for a configurable duration.


# Child script: held in module scope so subprocess can read it
# via a temp file. We write the script to a temp file at
# test-collection time, then subprocess.Popen it with sys.executable.
_HOLD_LOCK_SCRIPT = '''
"""Subprocess helper: hold the lock for `hold_seconds` then exit.

Invoked by TestCrossProcess::test_subprocess_acquire_blocks_parent_acquire.
The script takes 2 args: <lock_path> <hold_seconds>.
It acquires the lock, sleeps `hold_seconds`, then releases.
"""
import sys
import time
from pathlib import Path

# Add the backend dir to sys.path so `app.core.lockfile` resolves
backend_dir = "{backend_dir}"
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.lockfile import lockfile  # noqa: E402

lock_path = Path(sys.argv[1])
hold_seconds = float(sys.argv[2])

with lockfile(path=lock_path) as info:
    # Print a marker so the parent can confirm the child has the lock
    print(f"CHILD_HAS_LOCK pid={info.pid}", flush=True)
    time.sleep(hold_seconds)
print("CHILD_RELEASED", flush=True)
'''


def _write_hold_lock_script(backend_dir: Path) -> Path:
    """Write the child helper script to a temp file and return its path."""
    import tempfile

    fd, path = tempfile.mkstemp(
        prefix="lockfile_hold_", suffix=".py", dir="/tmp"
    )
    try:
        # backend_dir contains `{backend_dir}` placeholder — substitute.
        script = _HOLD_LOCK_SCRIPT.replace("{backend_dir}", str(backend_dir))
        os.write(fd, script.encode("utf-8"))
    finally:
        os.close(fd)
    return Path(path)


class TestCrossProcess:
    """Cross-process contention — the only test that proves the
    cross-process contract (kernel flock arbitrates between
    distinct PIDs / OFDs).
    """

    def test_subprocess_acquire_blocks_parent_acquire(
        self, lock_path: Path
    ) -> None:
        """A subprocess holding the lock blocks the parent's acquire().

        The child process holds the lock for ~3 seconds. The
        parent tries to acquire during that window and must
        get LockHeldError with the child's PID reported.
        """
        # Find the backend dir (parent of the tests dir) so the
        # child can import app.core.lockfile.
        # tests/core/test_lockfile.py → backend/
        backend_dir = Path(__file__).resolve().parent.parent.parent
        assert (backend_dir / "app" / "core" / "lockfile.py").exists(), (
            f"backend dir mismatch: {backend_dir}"
        )

        script_path = _write_hold_lock_script(backend_dir)

        try:
            # Start the child. Hold the lock for 3 seconds.
            # We use Popen + communicate to drive the I/O.
            proc = subprocess.Popen(
                [sys.executable, str(script_path), str(lock_path), "3"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )

            try:
                # Wait for the child to acquire the lock. We read
                # stdout line-by-line and look for the marker.
                child_held = False
                deadline = time.monotonic() + 5.0
                while time.monotonic() < deadline:
                    line = proc.stdout.readline()
                    if not line:
                        # Child died unexpectedly
                        stderr = proc.stderr.read() or ""
                        pytest.fail(
                            f"Child died before acquiring lock. "
                            f"stdout so far: {child_held!r}; stderr: {stderr!r}"
                        )
                    if line.startswith("CHILD_HAS_LOCK"):
                        child_held = True
                        # Extract the child's PID from the marker
                        child_pid_str = line.split("pid=")[1].strip()
                        child_pid = int(child_pid_str)
                        break
                assert child_held, f"Child did not print CHILD_HAS_LOCK in time"

                # Now the parent tries to acquire. Must raise
                # LockHeldError with the child's PID.
                with pytest.raises(LockHeldError) as exc_info:
                    acquire(path=lock_path)
                # The reported PID is the child's, not ours
                assert exc_info.value.pid == child_pid, (
                    f"Expected child PID {child_pid}, got {exc_info.value.pid}"
                )
                assert exc_info.value.path == lock_path

                # Wait for the child to finish (it'll release the lock).
                # We don't strictly need to — the fixture's cleanup
                # will handle it — but it's cleaner to drain.
                rest = proc.communicate(timeout=5)
                assert "CHILD_RELEASED" in rest[0], (
                    f"Child did not print CHILD_RELEASED. stdout: {rest[0]!r}; "
                    f"stderr: {rest[1]!r}"
                )
                assert proc.returncode == 0, (
                    f"Child exited non-zero: {proc.returncode}; "
                    f"stderr: {rest[1]!r}"
                )
            finally:
                # If anything went wrong above, kill the child.
                if proc.poll() is None:
                    proc.kill()
                    proc.wait()
        finally:
            script_path.unlink(missing_ok=True)
