from typing import Any, cast

from google import genai

from .base import FileReader, RemediationRequest, RemediationResponse
from .limits import MAX_FILE_BYTES, MAX_FILE_READS

READ_FILE_TOOL = {
    "type": "function",
    "name": "read_file",
    "description": "Read the contents of a file in the target repository, by repo-relative path.",
    "parameters": {
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
}

SUBMIT_TOOL = {
    "type": "function",
    "name": "submit_remediation",
    "description": "Submit the final file edits that remediate the ticket. Call exactly once.",
    "parameters": {
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


class GeminiRemediationProvider:
    """Uses the Gemini API's interactions endpoint (client.interactions.create), a
    stateful conversation API distinct from both Anthropic's messages/tool_use shape
    and OpenAI's chat-completions shape: function calls arrive as `steps` with
    type == "function_call", and continuing the conversation is done by passing
    previous_interaction_id rather than resending the full message history.
    """

    def __init__(self, api_key: str, model: str):
        self._client = genai.Client(api_key=api_key)
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
        tools = [READ_FILE_TOOL, SUBMIT_TOOL]
        interaction: Any = self._client.interactions.create(
            model=self._model,
            input=user_content,
            system_instruction=SYSTEM_PROMPT,
            tools=cast(Any, tools),
        )
        reads = 0

        while True:
            steps = cast(list[Any], interaction.steps)
            call_steps = [step for step in steps if step.type == "function_call"]
            if not call_steps:
                raise ValueError("Gemini ended its turn without calling submit_remediation")

            results: list[dict[str, Any]] = []
            submitted: RemediationResponse | None = None
            for step in call_steps:
                if step.name == "submit_remediation":
                    submitted = RemediationResponse.model_validate(step.arguments)
                    break
                if step.name == "read_file":
                    reads += 1
                    if reads > MAX_FILE_READS:
                        content = "Error: max file-read limit reached. Submit your remediation now."
                    else:
                        try:
                            content = file_reader(str(step.arguments["path"]))[:MAX_FILE_BYTES]
                        except Exception as exc:  # noqa: BLE001 - surfaced to the model, not raised
                            content = f"Error reading file: {exc}"
                    results.append(
                        {
                            "type": "function_result",
                            "name": step.name,
                            "call_id": step.id,
                            "result": [{"type": "text", "text": content}],
                        }
                    )

            if submitted is not None:
                return submitted

            interaction = self._client.interactions.create(
                model=self._model,
                input=cast(Any, results),
                tools=cast(Any, tools),
                previous_interaction_id=interaction.id,
            )
