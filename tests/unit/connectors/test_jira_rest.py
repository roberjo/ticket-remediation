import json

import httpx
import pytest
import respx

from ticket_remediation.connectors.jira.base import JiraIssuePayload
from ticket_remediation.connectors.jira.rest import JiraRestClient


@respx.mock
def test_create_issue_posts_expected_body_and_returns_ref():
    route = respx.post("http://jira.example.com/rest/api/2/issue").mock(
        return_value=httpx.Response(201, json={"key": "AVREM-1"})
    )
    client = JiraRestClient("http://jira.example.com", "dev@example.com", "token")

    ref = client.create_issue(
        JiraIssuePayload(
            project_key="AVREM",
            issue_type="Vulnerability",
            summary="Reflected XSS in /search",
            description="desc",
            components=["frontend"],
            labels=["High"],
        )
    )

    assert route.called
    body = json.loads(route.calls[0].request.content)
    assert body["fields"]["project"]["key"] == "AVREM"
    assert body["fields"]["components"] == [{"name": "frontend"}]
    assert ref.key == "AVREM-1"
    assert ref.url == "http://jira.example.com/browse/AVREM-1"


@respx.mock
def test_search_issues_parses_issues(fixtures_dir):
    payload = json.loads((fixtures_dir / "jira_issue_sample.json").read_text())
    respx.get("http://jira.example.com/rest/api/2/search").mock(
        return_value=httpx.Response(200, json=payload)
    )
    client = JiraRestClient("http://jira.example.com", "dev@example.com", "token")

    issues = client.search_issues('project = AVREM AND status = "Ready for Remediation"')

    assert len(issues) == 1
    assert issues[0].key == "AVREM-1"
    assert issues[0].components == ["frontend"]
    assert issues[0].status == "Ready for Remediation"


@respx.mock
def test_create_issue_raises_on_http_error():
    respx.post("http://jira.example.com/rest/api/2/issue").mock(return_value=httpx.Response(400))
    client = JiraRestClient("http://jira.example.com", "dev@example.com", "token")

    with pytest.raises(httpx.HTTPStatusError):
        client.create_issue(
            JiraIssuePayload(project_key="AVREM", issue_type="Vulnerability", summary="x", description="y")
        )
