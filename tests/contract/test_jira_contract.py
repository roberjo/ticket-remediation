"""Contract tests: JiraRestClient against the real jira_mock FastAPI app, started
in-process and hit over real HTTP (see conftest.py). These exist to catch "the
request/response shape doesn't actually match" bugs that a respx-mocked fixture
(tests/unit/connectors/test_jira_rest.py) can't — respx only ever confirms the client
matches the shape *we* wrote into the fixture, not the shape the server sends.
"""

import pytest

from ticket_remediation.connectors.jira.base import JiraIssuePayload
from ticket_remediation.connectors.jira.rest import JiraRestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(jira_mock_url):
    c = JiraRestClient(jira_mock_url, "user@example.com", "fake-token")
    yield c
    c.close()


def test_search_issues_returns_the_seeded_ready_for_remediation_issues(client, reset_jira_mock):
    issues = client.search_issues('project = AVREM AND status = "Ready for Remediation"')

    assert len(issues) == 2
    assert {i.components[0] for i in issues} == {"frontend", "infra-config"}
    assert all(i.status == "Ready for Remediation" for i in issues)


def test_create_issue_then_find_it_via_search(client, reset_jira_mock):
    payload = JiraIssuePayload(
        project_key="AVREM",
        issue_type="Vulnerability",
        summary="Contract-test-created issue",
        description="Created by a contract test.",
        components=["backend-api"],
        labels=["Medium"],
    )

    ref = client.create_issue(payload)

    assert ref.key.startswith("AVREM-")
    assert ref.url.endswith(f"/browse/{ref.key}")

    found = client.search_issues("project = AVREM AND status = Backlog")
    assert any(i.key == ref.key and i.summary == payload.summary for i in found)


def test_add_comment_then_transition_issue_moves_status(client, reset_jira_mock):
    payload = JiraIssuePayload(
        project_key="AVREM",
        issue_type="Vulnerability",
        summary="Issue to transition",
        description="...",
    )
    ref = client.create_issue(payload)

    client.add_comment(ref.key, "Remediation PR opened.")
    client.transition_issue(ref.key, "Triage")

    found = client.search_issues("project = AVREM AND status = Triage")
    assert any(i.key == ref.key for i in found)


def test_transition_issue_raises_for_a_transition_name_the_workflow_does_not_have(client, reset_jira_mock):
    payload = JiraIssuePayload(
        project_key="AVREM", issue_type="Vulnerability", summary="x", description="y"
    )
    ref = client.create_issue(payload)

    with pytest.raises(ValueError, match="No transition named"):
        client.transition_issue(ref.key, "Not A Real Status")
