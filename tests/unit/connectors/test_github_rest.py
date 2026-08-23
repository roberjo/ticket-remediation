from unittest.mock import MagicMock, patch

from ticket_remediation.connectors.github.rest import GitHubRestClient


@patch("ticket_remediation.connectors.github.rest.Github")
def test_get_default_branch(mock_github_cls):
    mock_repo = MagicMock(default_branch="main")
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    client = GitHubRestClient("fake-token")
    branch = client.get_default_branch("org/repo")

    assert branch == "main"
    mock_github_cls.return_value.get_repo.assert_called_once_with("org/repo")


@patch("ticket_remediation.connectors.github.rest.Github")
def test_create_pull_request_calls_repo_create_pull_with_expected_args(mock_github_cls):
    mock_pr = MagicMock(number=42, html_url="https://github.com/org/repo/pull/42")
    mock_repo = MagicMock()
    mock_repo.create_pull.return_value = mock_pr
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    client = GitHubRestClient("fake-token")
    ref = client.create_pull_request(
        "org/repo", head="remediate/AVREM-1-fix", base="main", title="[AVREM-1] Fix", body="body"
    )

    mock_repo.create_pull.assert_called_once_with(
        title="[AVREM-1] Fix", body="body", head="remediate/AVREM-1-fix", base="main"
    )
    assert ref.number == 42
    assert ref.url == "https://github.com/org/repo/pull/42"


@patch("ticket_remediation.connectors.github.rest.Github")
def test_get_pull_request_reports_merged_state(mock_github_cls):
    mock_pr = MagicMock(number=42, state="closed", merged=True)
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    client = GitHubRestClient("fake-token")
    state = client.get_pull_request("org/repo", 42)

    mock_repo.get_pull.assert_called_once_with(42)
    assert state.number == 42
    assert state.state == "closed"
    assert state.merged is True


@patch("ticket_remediation.connectors.github.rest.Github")
def test_get_pull_request_reports_open_state(mock_github_cls):
    mock_pr = MagicMock(number=7, state="open", merged=False)
    mock_repo = MagicMock()
    mock_repo.get_pull.return_value = mock_pr
    mock_github_cls.return_value.get_repo.return_value = mock_repo

    client = GitHubRestClient("fake-token")
    state = client.get_pull_request("org/repo", 7)

    assert state.state == "open"
    assert state.merged is False
