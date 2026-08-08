from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ticket_remediation.connectors.llm.anthropic_provider import (
    MAX_FILE_READS,
    AnthropicRemediationProvider,
)
from ticket_remediation.connectors.llm.base import RemediationRequest


def _tool_use_response(name: str, input_: dict, call_id: str = "call_1"):
    block = SimpleNamespace(type="tool_use", name=name, input=input_, id=call_id)
    return SimpleNamespace(content=[block])


def _request() -> RemediationRequest:
    return RemediationRequest(
        jira_key="AVREM-1",
        summary="Reflected XSS in /search",
        description="desc",
        file_tree=["src/app.js"],
    )


@patch("ticket_remediation.connectors.llm.anthropic_provider.Anthropic")
def test_generate_remediation_reads_a_file_then_submits(mock_anthropic_cls):
    read_response = _tool_use_response("read_file", {"path": "src/app.js"}, call_id="call_1")
    submit_response = _tool_use_response(
        "submit_remediation",
        {
            "summary": "Escape the query param",
            "commit_message": "Fix reflected XSS",
            "edits": [{"path": "src/app.js", "action": "modify", "content": "fixed"}],
        },
        call_id="call_2",
    )
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [read_response, submit_response]
    mock_anthropic_cls.return_value = mock_client

    file_reader = MagicMock(return_value="console.log('hi');")
    provider = AnthropicRemediationProvider(api_key="fake", model="claude-sonnet-5")

    result = provider.generate_remediation(_request(), file_reader)

    file_reader.assert_called_once_with("src/app.js")
    assert result.commit_message == "Fix reflected XSS"
    assert result.edits[0].path == "src/app.js"
    assert mock_client.messages.create.call_count == 2


@patch("ticket_remediation.connectors.llm.anthropic_provider.Anthropic")
def test_generate_remediation_enforces_max_file_reads(mock_anthropic_cls):
    reads = [
        _tool_use_response("read_file", {"path": f"src/file{i}.js"}, call_id=f"call_{i}")
        for i in range(MAX_FILE_READS + 2)
    ]
    submit = _tool_use_response(
        "submit_remediation",
        {"summary": "s", "commit_message": "c", "edits": []},
        call_id="call_final",
    )
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = [*reads, submit]
    mock_anthropic_cls.return_value = mock_client

    file_reader = MagicMock(return_value="content")
    provider = AnthropicRemediationProvider(api_key="fake", model="claude-sonnet-5")

    result = provider.generate_remediation(_request(), file_reader)

    assert result.commit_message == "c"
    # file_reader itself is only ever called for reads within the limit.
    assert file_reader.call_count == MAX_FILE_READS


@patch("ticket_remediation.connectors.llm.anthropic_provider.Anthropic")
def test_generate_remediation_raises_if_llm_never_submits(mock_anthropic_cls):
    mock_client = MagicMock()
    mock_client.messages.create.return_value = SimpleNamespace(content=[])
    mock_anthropic_cls.return_value = mock_client

    provider = AnthropicRemediationProvider(api_key="fake", model="claude-sonnet-5")

    with pytest.raises(ValueError, match="submit_remediation"):
        provider.generate_remediation(_request(), MagicMock())
