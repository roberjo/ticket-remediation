SYSTEM_PROMPT = (
    "You are an automated security-remediation engineer. You will be given a Jira vulnerability "
    "ticket and a repository file tree. Use the read_file tool to inspect a small, targeted set "
    "of relevant files, then call submit_remediation exactly once with the FULL new content of "
    "every file you are changing (not a diff). Only touch files necessary to fix the described "
    "vulnerability."
)

READ_FILE_TOOL_NAME = "read_file"
READ_FILE_TOOL_DESCRIPTION = "Read the contents of a file in the target repository, by repo-relative path."
READ_FILE_SCHEMA = {
    "type": "object",
    "properties": {"path": {"type": "string"}},
    "required": ["path"],
}

SUBMIT_TOOL_NAME = "submit_remediation"
SUBMIT_TOOL_DESCRIPTION = "Submit the final file edits that remediate the ticket. Call exactly once."
SUBMIT_SCHEMA = {
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
}
