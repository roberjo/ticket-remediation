import subprocess

import pytest

from ticket_remediation.remediate.context_builder import (
    MAX_FILE_READS,
    build_file_tree,
    make_file_reader,
)


@pytest.fixture
def git_repo(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.js").write_text("console.log('hi');\n")
    (repo / "README.md").write_text("# demo\n")
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )
    return repo


def test_build_file_tree_lists_tracked_files(git_repo):
    tree = build_file_tree(git_repo)
    assert set(tree) == {"README.md", "src/app.js"}


def test_file_reader_reads_tracked_file_content(git_repo):
    reader = make_file_reader(git_repo)
    assert reader("src/app.js") == "console.log('hi');\n"


def test_file_reader_rejects_path_escaping_repo(git_repo):
    reader = make_file_reader(git_repo)
    with pytest.raises(ValueError, match="escapes repository"):
        reader("../outside.txt")


def test_file_reader_enforces_max_reads(git_repo):
    reader = make_file_reader(git_repo)
    for _ in range(MAX_FILE_READS):
        reader("src/app.js")
    with pytest.raises(ValueError, match="max file-read limit"):
        reader("src/app.js")
