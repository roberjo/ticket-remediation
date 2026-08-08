from collections.abc import Callable
from typing import Literal, Protocol

from pydantic import BaseModel


class RemediationRequest(BaseModel):
    jira_key: str
    summary: str
    description: str
    acceptance_criteria: str | None = None
    file_tree: list[str]


class FileEdit(BaseModel):
    path: str
    action: Literal["create", "modify", "delete"]
    content: str | None = None


class RemediationResponse(BaseModel):
    summary: str
    commit_message: str
    edits: list[FileEdit]


FileReader = Callable[[str], str]


class LLMProvider(Protocol):
    def generate_remediation(
        self, request: RemediationRequest, file_reader: FileReader
    ) -> RemediationResponse: ...
