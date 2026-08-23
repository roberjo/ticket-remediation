from ticket_remediation.connectors.github.base import PullRequestState
from ticket_remediation.db.repository import RemediationRunRepository
from ticket_remediation.remediate.pr_sync import PrStatusSyncer


class FakeGitHubClient:
    def __init__(self, states: dict[tuple[str, int], PullRequestState]):
        self._states = states

    def get_default_branch(self, repo_full_name: str) -> str:
        raise NotImplementedError

    def create_pull_request(self, repo_full_name, head, base, title, body):
        raise NotImplementedError

    def get_pull_request(self, repo_full_name: str, pr_number: int) -> PullRequestState:
        return self._states[(repo_full_name, pr_number)]


def test_sync_marks_a_merged_pr_as_pr_merged(db_conn):
    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="pr_open", repo_full_name="org/repo", pr_number=1)
    github = FakeGitHubClient(
        {("org/repo", 1): PullRequestState(number=1, state="closed", merged=True)}
    )

    result = PrStatusSyncer(github, runs).sync()

    assert result.merged == ["AVREM-1"]
    assert result.closed == []
    assert result.checked == 1
    assert runs.get_run("AVREM-1")["status"] == "pr_merged"


def test_sync_marks_a_closed_unmerged_pr_as_pr_closed(db_conn):
    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="pr_open", repo_full_name="org/repo", pr_number=1)
    github = FakeGitHubClient(
        {("org/repo", 1): PullRequestState(number=1, state="closed", merged=False)}
    )

    result = PrStatusSyncer(github, runs).sync()

    assert result.closed == ["AVREM-1"]
    assert result.merged == []
    run = runs.get_run("AVREM-1")
    assert run["status"] == "pr_closed"
    # A closed-without-merge PR is a human decision — future runs must not silently retry it.
    assert runs.should_skip("AVREM-1", max_retries=5)


def test_sync_leaves_a_still_open_pr_untouched(db_conn):
    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="pr_open", repo_full_name="org/repo", pr_number=1)
    github = FakeGitHubClient(
        {("org/repo", 1): PullRequestState(number=1, state="open", merged=False)}
    )

    result = PrStatusSyncer(github, runs).sync()

    assert result.merged == []
    assert result.closed == []
    assert result.checked == 1
    assert runs.get_run("AVREM-1")["status"] == "pr_open"


def test_sync_only_checks_runs_currently_in_pr_open(db_conn):
    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="failed", error_message="boom")
    runs.upsert_run("AVREM-2", status="pr_merged", repo_full_name="org/repo", pr_number=2)
    github = FakeGitHubClient({})

    result = PrStatusSyncer(github, runs).sync()

    assert result.checked == 0


def test_sync_records_an_error_without_raising_when_github_lookup_fails(db_conn):
    class FailingGitHubClient:
        def get_pull_request(self, repo_full_name, pr_number):
            raise RuntimeError("GitHub is down")

    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="pr_open", repo_full_name="org/repo", pr_number=1)

    result = PrStatusSyncer(FailingGitHubClient(), runs).sync()

    assert result.errors == ["AVREM-1"]
    assert runs.get_run("AVREM-1")["status"] == "pr_open"  # unchanged, retried on the next sync
