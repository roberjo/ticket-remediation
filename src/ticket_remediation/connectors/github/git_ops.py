import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)


def _authenticated_url(repo_full_name: str, token: str) -> str:
    return f"https://x-access-token:{token}@github.com/{repo_full_name}.git"


def clone_or_update(repo_full_name: str, token: str, default_branch: str, work_dir: Path) -> Path:
    """Clone into work_dir/<repo_name> if absent, otherwise fetch + hard-reset to the
    default branch. Reused (not deleted) across runs so a failed remediation is
    inspectable on disk."""
    repo_path = work_dir / repo_full_name.split("/")[-1]
    url = _authenticated_url(repo_full_name, token)
    if not (repo_path / ".git").exists():
        repo_path.parent.mkdir(parents=True, exist_ok=True)
        # Destination is relative to cwd=work_dir, so pass just the basename here —
        # passing the full repo_path (which already includes work_dir) would clone
        # into work_dir/work_dir/<repo_name> instead.
        _run(["git", "clone", url, repo_path.name], cwd=work_dir)
    else:
        _run(["git", "remote", "set-url", "origin", url], cwd=repo_path)
        _run(["git", "fetch", "origin", default_branch], cwd=repo_path)
        _run(["git", "checkout", default_branch], cwd=repo_path)
        _run(["git", "reset", "--hard", f"origin/{default_branch}"], cwd=repo_path)
    return repo_path


def create_branch(repo_path: Path, branch_name: str, base_branch: str) -> None:
    _run(["git", "checkout", base_branch], cwd=repo_path)
    _run(["git", "checkout", "-b", branch_name], cwd=repo_path)


def commit_all(repo_path: Path, message: str) -> None:
    _run(["git", "add", "-A"], cwd=repo_path)
    _run(["git", "commit", "-m", message], cwd=repo_path)


def push_branch(repo_path: Path, branch_name: str) -> None:
    _run(["git", "push", "-u", "origin", branch_name, "--force-with-lease"], cwd=repo_path)
