from typing import Any, cast

from anthropic import Anthropic

from .base import FileReader, RemediationRequest, RemediationResponse
from .limits import MAX_FILE_BYTES, MAX_FILE_READS

READ_FILE_TOOL = {
    "name": "read_file",
    "description": "Read the contents of a file in the target repository, by repo-relative path.",
    "input_schema": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}

SUBMIT_TOOL = {
    "name": "submit_remediation",
    "description": "Submit the final file edits that remediate the ticket. Call exactly once.",
    "input_schema": {
        "type": "object",
        "properties": {
            "summary": {"type": "string"},
            "commit_message": {"type": "string"},
            "edits": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "action": {"type": "string", "enum": ["create", "modify", "delete"]},
                        "content": {"type": ["string", "null"]},
                    },
                    "required": ["path", "action"],
                },
            },
        },
        "required": ["summary", "commit_message", "edits"],
    },
}

SYSTEM_PROMPT = (
    "You are an automated security-remediation engineer. You will be given a Jira vulnerability "
    "ticket and a repository file tree. Use the read_file tool to inspect a small, targeted set "
    "of relevant files, then call submit_remediation exactly once with the FULL new content of "
    "every file you are changing (not a diff). Only touch files necessary to fix the described "
    "vulnerability."
)


class AnthropicRemediationProvider:
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
        self._model = model

    def generate_remediation(
        self, request: RemediationRequest, file_reader: FileReader
    ) -> RemediationResponse:
        user_content = (
            f"Jira ticket {request.jira_key}\n"
            f"Summary: {request.summary}\n"
            f"Description:\n{request.description}\n"
            + (
                f"Acceptance criteria:\n{request.acceptance_criteria}\n"
                if request.acceptance_criteria
                else ""
            )
            + "\nRepository file tree:\n"
            + "\n".join(request.file_tree)
        )
        messages: list[dict[str, Any]] = [{"role": "user", "content": user_content}]
        reads = 0

        while True:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                tools=cast(Any, [READ_FILE_TOOL, SUBMIT_TOOL]),
                messages=cast(Any, messages),
            )
            messages.append({"role": "assistant", "content": response.content})

            tool_uses = [block for block in response.content if block.type == "tool_use"]
            if not tool_uses:
                raise ValueError("LLM ended its turn without calling submit_remediation")

            tool_results = []
            submitted: RemediationResponse | None = None
            for block in tool_uses:
                if block.name == "submit_remediation":
                    submitted = RemediationResponse.model_validate(block.input)
                    break
                if block.name == "read_file":
                    reads += 1
                    if reads > MAX_FILE_READS:
                        content = "Error: max file-read limit reached. Submit your remediation now."
                    else:
                        try:
                            content = file_reader(str(block.input["path"]))[:MAX_FILE_BYTES]
                        except Exception as exc:  # noqa: BLE001 - surfaced to the model, not raised
                            content = f"Error reading file: {exc}"
                    tool_results.append({"type": "tool_result", "tool_use_id": block.id, "content": content})

            if submitted is not None:
                return submitted

            messages.append({"role": "user", "content": tool_results})
