from typing import Protocol

from pydantic import BaseModel


class PullRequestRef(BaseModel):
    number: int
    url: str


class PullRequestState(BaseModel):
    number: int
    state: str  # GitHub's own "open" | "closed"
    merged: bool


class GitHubClient(Protocol):
    def get_default_branch(self, repo_full_name: str) -> str: ...

    def create_pull_request(
        self, repo_full_name: str, head: str, base: str, title: str, body: str
    ) -> PullRequestRef: ...

    def get_pull_request(self, repo_full_name: str, pr_number: int) -> PullRequestState: ...
