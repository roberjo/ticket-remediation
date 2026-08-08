import httpx

from .base import JiraIssue, JiraIssuePayload, JiraIssueRef


class JiraRestClient:
    """httpx-based client against the Jira Cloud REST API v2."""

    def __init__(self, base_url: str, email: str, api_token: str, timeout: float = 30.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            auth=(email, api_token),
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            timeout=timeout,
        )

    def create_issue(self, payload: JiraIssuePayload) -> JiraIssueRef:
        body = {
            "fields": {
                "project": {"key": payload.project_key},
                "issuetype": {"name": payload.issue_type},
                "summary": payload.summary,
                "description": payload.description,
                "components": [{"name": c} for c in payload.components],
                "labels": payload.labels,
            }
        }
        response = self._client.post("/rest/api/2/issue", json=body)
        response.raise_for_status()
        key = response.json()["key"]
        return JiraIssueRef(key=key, url=f"{self._base_url}/browse/{key}")

    def search_issues(self, jql: str) -> list[JiraIssue]:
        response = self._client.get("/rest/api/2/search", params={"jql": jql, "maxResults": 200})
        response.raise_for_status()
        issues = []
        for row in response.json()["issues"]:
            fields = row["fields"]
            issues.append(
                JiraIssue(
                    key=row["key"],
                    project_key=fields["project"]["key"],
                    summary=fields["summary"],
                    description=fields.get("description", ""),
                    status=fields["status"]["name"],
                    components=[c["name"] for c in fields.get("components", [])],
                    labels=fields.get("labels", []),
                )
            )
        return issues

    def add_comment(self, key: str, body: str) -> None:
        response = self._client.post(f"/rest/api/2/issue/{key}/comment", json={"body": body})
        response.raise_for_status()

    def transition_issue(self, key: str, transition_name: str) -> None:
        response = self._client.get(f"/rest/api/2/issue/{key}/transitions")
        response.raise_for_status()
        transitions = response.json()["transitions"]
        matching = next((t for t in transitions if t["name"] == transition_name), None)
        if matching is None:
            raise ValueError(f"No transition named {transition_name!r} available for {key}")
        response = self._client.post(
            f"/rest/api/2/issue/{key}/transitions",
            json={"transition": {"id": matching["id"]}},
        )
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
