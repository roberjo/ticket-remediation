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
    def __init__(self, issues: list[JiraIssue]):
        self._issues = issues
        self.comments: list[tuple[str, str]] = []

    def create_issue(self, payload):
        raise NotImplementedError

    def search_issues(self, jql: str) -> list[JiraIssue]:
        return self._issues

    def add_comment(self, key: str, body: str) -> None:
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


class FakeLLMProvider:
    def generate_remediation(self, request: RemediationRequest, file_reader) -> RemediationResponse:
        return RemediationResponse(
            summary="Escape the query param before rendering",
            commit_message="Fix reflected XSS in search results",
            edits=[FileEdit(path="src/app.js", action="modify", content="console.log('fixed');\n")],
        )


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


def _pipeline(jira, github, llm, notifier, routing, runs, work_dir) -> RemediatePipeline:
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
