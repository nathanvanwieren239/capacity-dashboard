"""
Safe file handling for the tracker data: locking, atomic writes, backups.

Three problems this solves, all of which only appear once more than one
person uses the app on a real server:

1. LOST UPDATES.  Every save is read-whole-file, modify, write-whole-file.
   Two people saving at overlapping moments means the second write lands on
   a copy read before the first change existed, and silently discards it.
   `data_lock()` makes the whole read-modify-write sequence exclusive.

2. TORN WRITES.  Writing over a file in place leaves a window where the file
   on disk is half old and half new. An interruption there truncates it.
   `atomic_write_csv()` writes a temporary file, fsyncs it, then renames it
   over the target. Rename is atomic, so an interruption leaves either the
   old file intact or the new one, never a fragment.

3. NO WAY BACK.  A bad import replaces everything with no undo. `backup()`
   snapshots the current files before each write and keeps the most recent
   `MAX_BACKUPS` snapshots.

None of this needs a third-party package.
"""

from __future__ import annotations

import os
import shutil
import time
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"
BACKUP_DIR = DATA_DIR / "backups"
LOCK_PATH = DATA_DIR / ".tracker.lock"

MAX_BACKUPS = 40
LOCK_TIMEOUT_SECONDS = 15.0
LOCK_POLL_SECONDS = 0.05

# Files worth snapshotting before a write.
TRACKED_FILES = ("projects.csv", "gates.csv", "audit_log.csv")


class LockTimeout(RuntimeError):
    """Another save held the lock for longer than we were willing to wait."""


# ---------------------------------------------------------------------------
# Cross-platform advisory file lock
# ---------------------------------------------------------------------------
try:  # POSIX - the internal server will almost certainly be Linux
    import fcntl

    def _acquire(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)

    def _release(handle) -> None:
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

    LOCKING = "fcntl"
except ImportError:  # Windows - development machines
    try:
        import msvcrt

        def _acquire(handle) -> None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)

        def _release(handle) -> None:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)

        LOCKING = "msvcrt"
    except ImportError:  # pragma: no cover - neither available
        def _acquire(handle) -> None:
            return None

        def _release(handle) -> None:
            return None

        LOCKING = "none"


@contextmanager
def data_lock(timeout: float = LOCK_TIMEOUT_SECONDS):
    """
    Hold an exclusive lock for the duration of a read-modify-write.

    Wrap the WHOLE sequence, not just the write. Locking only the write still
    allows a stale read to overwrite a fresh change.
    """
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    handle = open(LOCK_PATH, "a+")
    deadline = time.monotonic() + timeout

    while True:
        try:
            _acquire(handle)
            break
        except OSError:
            if time.monotonic() >= deadline:
                handle.close()
                raise LockTimeout(
                    "Another save is in progress and did not finish within "
                    f"{timeout:.0f} seconds. Nothing was changed — try again."
                )
            time.sleep(LOCK_POLL_SECONDS)

    try:
        yield
    finally:
        try:
            _release(handle)
        finally:
            handle.close()


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------
def atomic_write_csv(df: pd.DataFrame, path: Path) -> None:
    """
    Write a dataframe so the target file is never left half-written.

    Writes to `<name>.tmp`, flushes it to disk, then renames over the target.
    os.replace is atomic on both Windows and POSIX.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")

    try:
        with open(tmp, "w", newline="", encoding="utf-8") as handle:
            df.to_csv(handle, index=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp, path)
    except Exception:
        # Never leave a stray temp file behind on failure.
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_append_csv(df: pd.DataFrame, path: Path, columns: list[str]) -> None:
    """
    Append rows atomically by rewriting the file. The audit log is small and
    correctness matters more than the cost of rewriting it.
    """
    path = Path(path)
    if path.exists():
        existing = pd.read_csv(path)
        combined = pd.concat(
            [existing, df.reindex(columns=columns)], ignore_index=True
        )
    else:
        combined = df.reindex(columns=columns)
    atomic_write_csv(combined, path)


# ---------------------------------------------------------------------------
# Backups
# ---------------------------------------------------------------------------
def backup(reason: str = "") -> Path | None:
    """
    Snapshot the current data files into data/backups/<timestamp>/.

    Returns the snapshot directory, or None if there was nothing to copy.
    Call this BEFORE writing, so the snapshot is the last known good state.
    """
    sources = [DATA_DIR / name for name in TRACKED_FILES]
    sources = [p for p in sources if p.exists()]
    if not sources:
        return None

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    label = f"{stamp}-{reason}" if reason else stamp
    target = BACKUP_DIR / label

    # Two saves inside the same second would collide.
    suffix = 1
    while target.exists():
        suffix += 1
        target = BACKUP_DIR / f"{label}-{suffix}"

    target.mkdir(parents=True, exist_ok=True)
    for src in sources:
        shutil.copy2(src, target / src.name)

    _prune_backups()
    return target


def _prune_backups(keep: int | None = None) -> None:
    # Read MAX_BACKUPS at call time, not as a default argument. A default is
    # evaluated once when the function is defined, so the retention limit
    # could not be changed without restarting the app.
    limit = MAX_BACKUPS if keep is None else keep
    if not BACKUP_DIR.exists() or limit < 0:
        return
    snapshots = sorted(
        (p for p in BACKUP_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.name,
    )
    for stale in snapshots[:-limit] if len(snapshots) > limit else []:
        shutil.rmtree(stale, ignore_errors=True)


def list_backups() -> list[Path]:
    if not BACKUP_DIR.exists():
        return []
    return sorted(
        (p for p in BACKUP_DIR.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )


def restore(snapshot: Path) -> list[str]:
    """Copy a snapshot back over the live files. Backs up first."""
    snapshot = Path(snapshot)
    if not snapshot.is_dir():
        raise FileNotFoundError(f"No such snapshot: {snapshot}")

    backup(reason="pre-restore")
    restored = []
    for name in TRACKED_FILES:
        src = snapshot / name
        if src.exists():
            shutil.copy2(src, DATA_DIR / name)
            restored.append(name)
    return restored
