import shutil
import subprocess
from collections.abc import Callable
from pathlib import Path

MAX_FILES_IN_TREE = 500
MAX_FILE_READS = 15
MAX_FILE_BYTES = 20_000

# Resolved once at import time to an absolute path so a cron job's PATH can't be used to
# smuggle in a different "git" ahead of the real one.
_GIT = shutil.which("git") or "git"


def build_file_tree(repo_path: Path) -> list[str]:
    # repo_path is our own clone destination, never external input.
    result = subprocess.run(  # noqa: S603
        [_GIT, "ls-files"], cwd=repo_path, check=True, capture_output=True, text=True
    )
    return result.stdout.splitlines()[:MAX_FILES_IN_TREE]


def make_file_reader(repo_path: Path) -> Callable[[str], str]:
    """Bounded callback handed to the LLM provider: caps total reads and file size,
    and refuses any path that escapes the repo working directory — required because
    these paths originate from a model response."""
    repo_root = repo_path.resolve()
    state = {"reads": 0}

    def file_reader(relative_path: str) -> str:
        if state["reads"] >= MAX_FILE_READS:
            raise ValueError("max file-read limit reached for this remediation run")
        state["reads"] += 1

        target = (repo_root / relative_path).resolve()
        if target != repo_root and repo_root not in target.parents:
            raise ValueError(f"path escapes repository working directory: {relative_path}")
        if not target.is_file():
            raise ValueError(f"no such file: {relative_path}")

        return target.read_text(errors="replace")[:MAX_FILE_BYTES]

    return file_reader
