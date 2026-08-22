import re
import subprocess
from pathlib import Path

# Matches the credentials portion of an _authenticated_url(...) result, independent of
# the token's actual value, so it can redact that value out of argv *and* out of git's
# own stdout/stderr (which often echoes the remote URL back verbatim on failure).
_TOKEN_URL_RE = re.compile(r"x-access-token:[^@]+@")
_REDACTED = "x-access-token:***REDACTED***@"


class GitCommandError(subprocess.SubprocessError):
    """Raised instead of subprocess.CalledProcessError for any failed git invocation.
    CalledProcessError.__str__ embeds argv verbatim, which for us can contain an
    authenticated clone URL (https://x-access-token:{token}@...); that string ends up
    stored in remediation_runs.error_message and shown by `remediate show`, so it must
    never carry the raw token."""


def _redact(value: str) -> str:
    return _TOKEN_URL_RE.sub(_REDACTED, value)


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        redacted_args = [_redact(a) for a in exc.cmd]
        stdout = _redact(exc.stdout or "")
        stderr = _redact(exc.stderr or "")
        raise GitCommandError(
            f"Command {redacted_args} returned non-zero exit status {exc.returncode}. "
            f"stdout={stdout!r} stderr={stderr!r}"
        ) from None


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
    """Uses -B (create-or-reset) rather than -b: local dedup state (data/state.db) is
    documented as safe to delete to reset dev state, but a leftover local branch from an
    earlier attempt can still exist in the reused work/ clone — -B resets it to the
    current base_branch instead of failing with "branch already exists"."""
    _run(["git", "checkout", base_branch], cwd=repo_path)
    _run(["git", "checkout", "-B", branch_name], cwd=repo_path)


def commit_all(repo_path: Path, message: str) -> None:
    _run(["git", "add", "-A"], cwd=repo_path)
    _run(["git", "commit", "-m", message], cwd=repo_path)


def push_branch(repo_path: Path, branch_name: str) -> None:
    _run(["git", "push", "-u", "origin", branch_name, "--force-with-lease"], cwd=repo_path)
