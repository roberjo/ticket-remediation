from typing import Protocol

from pydantic import BaseModel


class JiraIssuePayload(BaseModel):
    project_key: str
    issue_type: str
    summary: str
    description: str
    components: list[str] = []
    labels: list[str] = []


class JiraIssueRef(BaseModel):
    key: str
    url: str


class JiraIssue(BaseModel):
    key: str
    project_key: str
    summary: str
    description: str
    status: str
    components: list[str] = []
    labels: list[str] = []


class JiraClient(Protocol):
    def create_issue(self, payload: JiraIssuePayload) -> JiraIssueRef: ...

    def search_issues(self, jql: str) -> list[JiraIssue]: ...

    def add_comment(self, key: str, body: str) -> None: ...

    def transition_issue(self, key: str, transition_name: str) -> None: ...
