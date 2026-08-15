"""Cross-process advisory locks for state transitions."""

from __future__ import annotations

import hashlib
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

try:
    import fcntl
except ImportError:  # Windows: fall back to msvcrt byte-range locking
    fcntl = None  # type: ignore[assignment]
try:
    import msvcrt
except ImportError:
    msvcrt = None  # type: ignore[assignment]


class LockManager:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)

    @contextmanager
    def acquire(self, name: str) -> Iterator[None]:
        digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
        path = self.root / f"{digest}.lock"
        fd = os.open(path, os.O_CREAT | os.O_RDWR, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            elif msvcrt is not None:
                # Lock the first byte for the process lifetime of the context.
                msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            yield
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            elif msvcrt is not None:
                try:
                    os.lseek(fd, 0, os.SEEK_SET)
                    msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            os.close(fd)
