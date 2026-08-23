import subprocess
from pathlib import Path

import pytest

from ticket_remediation.config.mapping import RepoRoutingConfig
from ticket_remediation.connectors.github.base import PullRequestRef
from ticket_remediation.connectors.jira.base import JiraIssue
from ticket_remediation.connectors.llm.base import FileEdit, RemediationRequest, RemediationResponse
from ticket_remediation.connectors.notify.base import NotificationMessage
from ticket_remediation.db.repository import RemediationRunRepository
from ticket_remediation.remediate import pipeline as pipeline_module
from ticket_remediation.remediate.pipeline import RemediatePipeline


def _issue(key: str = "AVREM-1", status: str = "Ready for Remediation") -> JiraIssue:
    return JiraIssue(
        key=key,
        project_key="AVREM",
        summary="Reflected XSS in /search",
        description="desc",
        status=status,
        components=["frontend"],
        labels=["High"],
    )


class FakeJiraClient:
    def __init__(self, issues: list[JiraIssue], fail_comment: bool = False, fail_search: bool = False):
        self._issues = issues
        self._fail_comment = fail_comment
        self._fail_search = fail_search
        self.comments: list[tuple[str, str]] = []
        self.last_jql: str | None = None

    def create_issue(self, payload):
        raise NotImplementedError

    def search_issues(self, jql: str) -> list[JiraIssue]:
        self.last_jql = jql
        if self._fail_search:
            raise RuntimeError("Jira search is down")
        return self._issues

    def add_comment(self, key: str, body: str) -> None:
        if self._fail_comment:
            raise RuntimeError("Jira is down")
        self.comments.append((key, body))

    def transition_issue(self, key: str, transition_name: str) -> None:
        raise NotImplementedError


class FakeGitHubClient:
    def __init__(self):
        self.prs_opened: list[tuple[str, str, str, str]] = []

    def get_default_branch(self, repo_full_name: str) -> str:
        return "main"

    def create_pull_request(
        self, repo_full_name: str, head: str, base: str, title: str, body: str
    ) -> PullRequestRef:
        self.prs_opened.append((repo_full_name, head, base, title))
        return PullRequestRef(number=1, url="https://github.com/org/repo/pull/1")

    def get_pull_request(self, repo_full_name: str, pr_number: int):
        raise NotImplementedError


class FakeLLMProvider:
    def generate_remediation(self, request: RemediationRequest, file_reader) -> RemediationResponse:
        return RemediationResponse(
            summary="Escape the query param before rendering",
            commit_message="Fix reflected XSS in search results",
            edits=[FileEdit(path="src/app.js", action="modify", content="console.log('fixed');\n")],
        )


class TooManyEditsLLMProvider:
    def generate_remediation(self, request: RemediationRequest, file_reader) -> RemediationResponse:
        edits = [
            FileEdit(path=f"src/file{i}.js", action="modify", content="x")
            for i in range(pipeline_module.MAX_EDIT_FILES + 1)
        ]
        return RemediationResponse(
            summary="Too many files changed",
            commit_message="Change everything",
            edits=edits,
        )


class CountingLLMProvider:
    def __init__(self):
        self.calls = 0

    def generate_remediation(self, request: RemediationRequest, file_reader) -> RemediationResponse:
        self.calls += 1
        return RemediationResponse(
            summary="Escape the query param before rendering",
            commit_message="Fix reflected XSS in search results",
            edits=[FileEdit(path="src/app.js", action="modify", content="console.log('fixed');\n")],
        )


class FailingLLMProvider:
    def generate_remediation(self, request: RemediationRequest, file_reader) -> RemediationResponse:
        raise RuntimeError("LLM provider is down")


class FakeNotifier:
    def __init__(self):
        self.messages: list[NotificationMessage] = []

    def notify(self, message: NotificationMessage) -> None:
        self.messages.append(message)


@pytest.fixture
def local_repo(tmp_path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "app.js").write_text("console.log('hi');\n")
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@example.com", "-c", "user.name=t", "commit", "-q", "-m", "init"],
        cwd=repo,
        check=True,
    )
    return repo


@pytest.fixture
def routing() -> RepoRoutingConfig:
    return RepoRoutingConfig.model_validate(
        {
            "routes": [
                {
                    "match": {"project_key": "AVREM", "components": ["frontend"]},
                    "repo": {
                        "owner": "demo-org",
                        "name": "vulnerable-react-demo-app",
                        "default_branch": "main",
                    },
                }
            ]
        }
    )


def _routing_with_verify(verify_command: str) -> RepoRoutingConfig:
    return RepoRoutingConfig.model_validate(
        {
            "routes": [
                {
                    "match": {"project_key": "AVREM", "components": ["frontend"]},
                    "repo": {
                        "owner": "demo-org",
                        "name": "vulnerable-react-demo-app",
                        "default_branch": "main",
                        "verify_command": verify_command,
                    },
                }
            ]
        }
    )


def _pipeline(
    jira,
    github,
    llm,
    notifier,
    routing,
    runs,
    work_dir,
    max_retries: int = 5,
    max_llm_calls: int | None = None,
) -> RemediatePipeline:
    return RemediatePipeline(
        jira_client=jira,
        github_client=github,
        llm_provider=llm,
        notifier=notifier,
        routing=routing,
        runs=runs,
        github_token="fake-token",
        jira_base_url="https://example.atlassian.net",
        work_dir=work_dir,
        max_retries=max_retries,
        max_llm_calls=max_llm_calls,
    )


def test_remediate_pipeline_opens_pr_and_notifies(monkeypatch, local_repo, routing, db_conn, tmp_path):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    notifier = FakeNotifier()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(jira, github, FakeLLMProvider(), notifier, routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.opened_prs == ["AVREM-1"]
    assert result.failed == []
    assert len(github.prs_opened) == 1
    assert len(notifier.messages) == 1
    assert jira.comments  # PR link commented back onto the ticket
    assert runs.is_already_delivered("AVREM-1")
    assert (local_repo / "src" / "app.js").read_text() == "console.log('fixed');\n"


def test_verify_command_success_still_opens_the_pr(monkeypatch, local_repo, db_conn, tmp_path):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(
        jira, github, FakeLLMProvider(), FakeNotifier(), _routing_with_verify("true"), runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert result.opened_prs == ["AVREM-1"]
    assert len(github.prs_opened) == 1


def test_verify_command_failure_blocks_the_pr(monkeypatch, local_repo, db_conn, tmp_path):
    """A syntactically broken or test-failing LLM edit must never reach PR review as if it
    were untested — a nonzero verify_command exit stops the pipeline before commit/push."""
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(
        jira, github, FakeLLMProvider(), FakeNotifier(), _routing_with_verify("false"), runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert result.opened_prs == []
    assert result.failed == ["AVREM-1"]
    assert github.prs_opened == []
    run = runs.get_run("AVREM-1")
    assert run["stage"] == "verify"
    assert run["status"] == "failed"


def test_verify_command_timeout_blocks_the_pr(monkeypatch, local_repo, db_conn, tmp_path):
    real_run = subprocess.run

    def _run_or_timeout(args, *posargs, **kwargs):
        # subprocess is a process-wide singleton module, so this fake must only intercept the
        # verify_command call and pass everything else (git_ops's own calls) through untouched.
        if kwargs.get("shell"):
            raise subprocess.TimeoutExpired(cmd=args, timeout=pipeline_module.VERIFY_TIMEOUT_SECONDS)
        return real_run(args, *posargs, **kwargs)

    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)
    monkeypatch.setattr(pipeline_module.subprocess, "run", _run_or_timeout)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(
        jira, github, FakeLLMProvider(), FakeNotifier(), _routing_with_verify("sleep 999"), runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert result.opened_prs == []
    assert result.failed == ["AVREM-1"]
    assert runs.get_run("AVREM-1")["stage"] == "verify"


def test_no_verify_command_configured_skips_verification(monkeypatch, local_repo, routing, db_conn, tmp_path):
    """routing has no verify_command set — confirms the feature is opt-in per route and doesn't
    change behavior for a route that never configured one."""
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(
        jira, github, FakeLLMProvider(), FakeNotifier(), routing, runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert result.opened_prs == ["AVREM-1"]


def test_remediate_pipeline_skips_already_delivered_issue(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)
    runs.upsert_run("AVREM-1", status="pr_open", pr_url="https://github.com/org/repo/pull/1", pr_number=1)

    result = _pipeline(jira, github, FakeLLMProvider(), FakeNotifier(), routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.skipped == 1
    assert result.opened_prs == []
    assert github.prs_opened == []


def test_pr_stays_recorded_as_open_even_if_the_jira_comment_fails(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    """Regression test: a failure in add_comment used to propagate up to the pipeline's
    outer except and overwrite status="pr_open" with status="failed", even though a real
    PR was already created — causing the next run to retry and collide with GitHub's
    "a pull request already exists for this branch" error. The comment step must fail
    without undoing the pr_open state."""
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()], fail_comment=True)
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(jira, github, FakeLLMProvider(), FakeNotifier(), routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.opened_prs == ["AVREM-1"]
    assert result.failed == []
    assert len(github.prs_opened) == 1
    run = runs.get_run("AVREM-1")
    assert run["status"] == "pr_open"
    assert runs.is_already_delivered("AVREM-1")


def test_remediate_pipeline_records_batch_error_when_search_issues_fails(
    monkeypatch, routing, db_conn, tmp_path
):
    jira = FakeJiraClient([], fail_search=True)
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)
    notifier = FakeNotifier()

    result = _pipeline(jira, github, FakeLLMProvider(), notifier, routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.batch_error == "Jira search is down"
    assert result.opened_prs == []
    assert result.failed == []
    assert github.prs_opened == []
    assert len(notifier.messages) == 1
    assert notifier.messages[0].level == "failure"
    assert notifier.messages[0].pr_url is None


def test_remediate_pipeline_fails_and_writes_nothing_when_llm_returns_too_many_edits(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(
        jira, github, TooManyEditsLLMProvider(), FakeNotifier(), routing, runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert result.failed == ["AVREM-1"]
    assert result.opened_prs == []
    assert github.prs_opened == []
    assert not (local_repo / "src" / "file0.js").exists()
    assert (local_repo / "src" / "app.js").read_text() == "console.log('hi');\n"


def test_permanently_failed_ticket_is_blocked_without_calling_llm_or_github(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    llm = CountingLLMProvider()
    runs = RemediationRunRepository(db_conn)
    for _ in range(2):
        runs.upsert_run("AVREM-1", status="failed", error_message="boom")

    result = _pipeline(jira, github, llm, FakeNotifier(), routing, runs, tmp_path, max_retries=2).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.blocked == ["AVREM-1"]
    assert result.opened_prs == []
    assert result.failed == []
    assert llm.calls == 0
    assert github.prs_opened == []


def test_ignored_ticket_is_blocked_without_calling_llm_or_github(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    llm = CountingLLMProvider()
    runs = RemediationRunRepository(db_conn)
    runs.mark_ignored("AVREM-1", reason="known false positive")

    result = _pipeline(jira, github, llm, FakeNotifier(), routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.blocked == ["AVREM-1"]
    assert result.opened_prs == []
    assert result.failed == []
    assert llm.calls == 0
    assert github.prs_opened == []


def test_max_llm_calls_caps_processing_and_defers_the_rest(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    issues = [_issue(key=f"AVREM-{i}") for i in range(1, 4)]
    jira = FakeJiraClient(issues)
    github = FakeGitHubClient()
    llm = CountingLLMProvider()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(jira, github, llm, FakeNotifier(), routing, runs, tmp_path, max_llm_calls=1).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert len(result.opened_prs) == 1
    assert result.deferred == 2
    assert llm.calls == 1

    processed_key = result.opened_prs[0]
    for issue in issues:
        if issue.key != processed_key:
            assert runs.get_run(issue.key) is None


def test_failure_at_a_specific_stage_is_recorded_on_the_run(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)
    notifier = FakeNotifier()

    result = _pipeline(jira, github, FailingLLMProvider(), notifier, routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM"
    )

    assert result.failed == ["AVREM-1"]
    run = runs.get_run("AVREM-1")
    assert run["stage"] == "llm_generate"
    assert "LLM provider is down" in run["error_message"]
    assert len(notifier.messages) == 1
    assert notifier.messages[0].level == "failure"
    assert "AVREM-1" in notifier.messages[0].body


def test_remediate_pipeline_sends_one_failure_notification_for_multiple_failed_tickets(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    issues = [_issue(key="AVREM-1"), _issue(key="AVREM-2")]
    jira = FakeJiraClient(issues)
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)
    notifier = FakeNotifier()

    result = _pipeline(
        jira, github, FailingLLMProvider(), notifier, routing, runs, tmp_path
    ).run(jql_status="Ready for Remediation", project_key="AVREM")

    assert sorted(result.failed) == ["AVREM-1", "AVREM-2"]
    assert len(notifier.messages) == 1
    assert notifier.messages[0].level == "failure"
    assert "AVREM-1" in notifier.messages[0].body
    assert "AVREM-2" in notifier.messages[0].body


def test_ticket_key_narrows_the_jql_instead_of_using_the_status_filter(
    monkeypatch, local_repo, routing, db_conn, tmp_path
):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    jira = FakeJiraClient([_issue()])
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)

    result = _pipeline(jira, github, FakeLLMProvider(), FakeNotifier(), routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM", ticket_key="AVREM-1"
    )

    assert jira.last_jql == 'key = "AVREM-1"'
    assert result.opened_prs == ["AVREM-1"]


def test_bypass_skip_for_only_bypasses_the_named_ticket(monkeypatch, local_repo, routing, db_conn, tmp_path):
    monkeypatch.setattr(pipeline_module.git_ops, "clone_or_update", lambda *a, **k: local_repo)
    monkeypatch.setattr(pipeline_module.git_ops, "push_branch", lambda *a, **k: None)

    issues = [_issue(key="AVREM-1"), _issue(key="AVREM-2")]
    jira = FakeJiraClient(issues)
    github = FakeGitHubClient()
    runs = RemediationRunRepository(db_conn)
    runs.mark_ignored("AVREM-1")
    runs.mark_ignored("AVREM-2")

    result = _pipeline(jira, github, FakeLLMProvider(), FakeNotifier(), routing, runs, tmp_path).run(
        jql_status="Ready for Remediation", project_key="AVREM", bypass_skip_for="AVREM-1"
    )

    assert result.opened_prs == ["AVREM-1"]
    assert result.blocked == ["AVREM-2"]
