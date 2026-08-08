import subprocess
from unittest.mock import patch

from ticket_remediation.connectors.github import git_ops


@patch("ticket_remediation.connectors.github.git_ops.subprocess.run")
def test_create_branch_runs_expected_argv(mock_run, tmp_path):
    git_ops.create_branch(tmp_path, "remediate/AVREM-1-fix", "main")

    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["git", "checkout", "main"] in calls
    assert ["git", "checkout", "-b", "remediate/AVREM-1-fix"] in calls


@patch("ticket_remediation.connectors.github.git_ops.subprocess.run")
def test_clone_or_update_clones_when_repo_absent(mock_run, tmp_path):
    repo_path = git_ops.clone_or_update("org/repo", "tok", "main", tmp_path)

    assert repo_path == tmp_path / "repo"
    clone_call = mock_run.call_args_list[0].args[0]
    assert clone_call[:2] == ["git", "clone"]
    assert clone_call[2] == "https://x-access-token:tok@github.com/org/repo.git"


@patch("ticket_remediation.connectors.github.git_ops.subprocess.run")
def test_clone_or_update_fetches_and_resets_when_repo_present(mock_run, tmp_path):
    repo_path = tmp_path / "repo"
    (repo_path / ".git").mkdir(parents=True)

    git_ops.clone_or_update("org/repo", "tok", "main", tmp_path)

    calls = [c.args[0] for c in mock_run.call_args_list]
    assert [
        "git",
        "remote",
        "set-url",
        "origin",
        "https://x-access-token:tok@github.com/org/repo.git",
    ] in calls
    assert ["git", "fetch", "origin", "main"] in calls
    assert ["git", "reset", "--hard", "origin/main"] in calls


@patch("ticket_remediation.connectors.github.git_ops.subprocess.run")
def test_commit_all_runs_expected_argv(mock_run, tmp_path):
    git_ops.commit_all(tmp_path, "AVREM-1: fix")

    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["git", "add", "-A"] in calls
    assert ["git", "commit", "-m", "AVREM-1: fix"] in calls


def _init_repo(path, initial_file="README.md", content="# demo\n"):
    path.mkdir(parents=True, exist_ok=True)
    (path / initial_file).write_text(content)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=path,
        check=True,
    )


def test_clone_or_update_fresh_clone_lands_at_the_correct_path(tmp_path, monkeypatch):
    """Regression test: clone_or_update once passed the full work_dir-prefixed repo_path
    as the clone destination while also cwd-ing into work_dir, landing the clone at
    work_dir/work_dir/<repo> instead of work_dir/<repo>. Mocked-subprocess tests didn't
    catch it since they only assert argv, not where the destination path actually
    resolves — so this one runs the real function against a real local bare repo."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)
    seed = tmp_path / "seed"
    _init_repo(seed)
    subprocess.run(["git", "push", "-q", str(origin), "main"], cwd=seed, check=True)

    monkeypatch.setattr(git_ops, "_authenticated_url", lambda repo_full_name, token: str(origin))

    work_dir = tmp_path / "work"
    repo_path = git_ops.clone_or_update("org/repo", "tok", "main", work_dir)

    assert repo_path == work_dir / "repo"
    assert (repo_path / ".git").is_dir()
    assert (repo_path / "README.md").read_text() == "# demo\n"
    assert not (work_dir / "work").exists()  # the bug would have created this

    # second call: repo already exists, should fetch+reset in place, not re-clone
    (seed / "README.md").write_text("# demo (updated upstream)\n")
    subprocess.run(["git", "add", "-A"], cwd=seed, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "update"],
        cwd=seed,
        check=True,
    )
    subprocess.run(["git", "push", "-q", str(origin), "main"], cwd=seed, check=True)

    repo_path_2 = git_ops.clone_or_update("org/repo", "tok", "main", work_dir)

    assert repo_path_2 == repo_path
    assert (repo_path / "README.md").read_text() == "# demo (updated upstream)\n"


def test_clone_branch_commit_push_against_local_bare_remote(tmp_path, monkeypatch):
    """Integration-style: no network, no mocking of git — a real local bare repo stands in
    for GitHub so the actual clone/branch/commit/push argv is exercised end to end, via
    the same clone_or_update entrypoint the remediate pipeline actually calls."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    seed = tmp_path / "seed"
    _init_repo(seed)
    subprocess.run(["git", "push", "-q", str(origin), "main"], cwd=seed, check=True)

    monkeypatch.setattr(git_ops, "_authenticated_url", lambda repo_full_name, token: str(origin))

    work_dir = tmp_path / "work"
    repo_path = git_ops.clone_or_update("org/repo", "tok", "main", work_dir)

    git_ops.create_branch(repo_path, "remediate/AVREM-1-fix", "main")
    (repo_path / "README.md").write_text("# demo (fixed)\n")
    git_ops.commit_all(repo_path, "AVREM-1: fix")
    git_ops.push_branch(repo_path, "remediate/AVREM-1-fix")

    branches = subprocess.run(
        ["git", "branch"], cwd=origin, check=True, capture_output=True, text=True
    ).stdout
    assert "remediate/AVREM-1-fix" in branches
