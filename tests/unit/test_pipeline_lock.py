import fcntl

import pytest

from ticket_remediation.pipeline_lock import LockHeldError, pipeline_lock


def test_second_acquire_raises_lock_held_error(tmp_path):
    lock_path = tmp_path / "state" / "remediate.lock"

    with pipeline_lock(lock_path):
        with pytest.raises(LockHeldError):
            with pipeline_lock(lock_path):
                pass


def test_lock_is_released_on_context_exit(tmp_path):
    lock_path = tmp_path / "remediate.lock"

    with pipeline_lock(lock_path):
        pass

    with pipeline_lock(lock_path):
        pass


def test_second_acquire_raises_when_held_by_another_file_descriptor(tmp_path):
    lock_path = tmp_path / "remediate.lock"
    lock_path.write_text("")

    fh = open(lock_path, "w")
    fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        with pytest.raises(LockHeldError):
            with pipeline_lock(lock_path):
                pass
    finally:
        fh.close()

    with pipeline_lock(lock_path):
        pass
