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


def test_clone_branch_commit_push_against_local_bare_remote(tmp_path):
    """Integration-style: no network, no mocking of git — a real local bare repo stands in
    for GitHub so the actual clone/branch/commit/push argv is exercised end to end."""
    origin = tmp_path / "origin.git"
    subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(origin)], check=True)

    seed = tmp_path / "seed"
    _init_repo(seed)
    subprocess.run(["git", "push", "-q", str(origin), "main"], cwd=seed, check=True)

    work_dir = tmp_path / "work"
    work_dir.mkdir()
    repo_path = work_dir / "repo"
    subprocess.run(["git", "clone", "-q", str(origin), str(repo_path)], check=True)

    git_ops.create_branch(repo_path, "remediate/AVREM-1-fix", "main")
    (repo_path / "README.md").write_text("# demo (fixed)\n")
    git_ops.commit_all(repo_path, "AVREM-1: fix")
    git_ops.push_branch(repo_path, "remediate/AVREM-1-fix")

    branches = subprocess.run(
        ["git", "branch"], cwd=origin, check=True, capture_output=True, text=True
    ).stdout
    assert "remediate/AVREM-1-fix" in branches
