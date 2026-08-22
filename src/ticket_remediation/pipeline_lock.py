import fcntl
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class LockHeldError(Exception):
    pass


@contextmanager
def pipeline_lock(path: Path) -> Iterator[None]:
    path.parent.mkdir(parents=True, exist_ok=True)
    fh = open(path, "w")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise LockHeldError(f"lock held: {path}") from exc
        yield
    finally:
        fh.close()
