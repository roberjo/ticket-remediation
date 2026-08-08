from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from ticket_remediation.connectors.llm.base import RemediationRequest
from ticket_remediation.connectors.llm.gemini_provider import GeminiRemediationProvider
from ticket_remediation.connectors.llm.limits import MAX_FILE_READS


def _interaction(steps: list, interaction_id: str = "int_1"):
    return SimpleNamespace(id=interaction_id, steps=steps)


def _call_step(name: str, arguments: dict, step_id: str = "call_1"):
    return SimpleNamespace(type="function_call", name=name, arguments=arguments, id=step_id)


def _request() -> RemediationRequest:
    return RemediationRequest(
        jira_key="AVREM-1",
        summary="Reflected XSS in /search",
        description="desc",
        file_tree=["src/app.js"],
    )


@patch("ticket_remediation.connectors.llm.gemini_provider.genai.Client")
def test_generate_remediation_reads_a_file_then_submits(mock_client_cls):
    read_interaction = _interaction(
        [_call_step("read_file", {"path": "src/app.js"}, step_id="call_1")], interaction_id="int_1"
    )
    submit_interaction = _interaction(
        [
            _call_step(
                "submit_remediation",
                {
                    "summary": "Escape the query param",
                    "commit_message": "Fix reflected XSS",
                    "edits": [{"path": "src/app.js", "action": "modify", "content": "fixed"}],
                },
                step_id="call_2",
            )
        ],
        interaction_id="int_2",
    )
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = [read_interaction, submit_interaction]
    mock_client_cls.return_value = mock_client

    file_reader = MagicMock(return_value="console.log('hi');")
    provider = GeminiRemediationProvider(api_key="fake", model="gemini-3.6-flash")

    result = provider.generate_remediation(_request(), file_reader)

    file_reader.assert_called_once_with("src/app.js")
    assert result.commit_message == "Fix reflected XSS"
    assert result.edits[0].path == "src/app.js"
    assert mock_client.interactions.create.call_count == 2

    second_call_kwargs = mock_client.interactions.create.call_args_list[1].kwargs
    assert second_call_kwargs["previous_interaction_id"] == "int_1"
    assert second_call_kwargs["input"][0]["call_id"] == "call_1"


@patch("ticket_remediation.connectors.llm.gemini_provider.genai.Client")
def test_generate_remediation_enforces_max_file_reads(mock_client_cls):
    reads = [
        _interaction(
            [_call_step("read_file", {"path": f"src/file{i}.js"}, step_id=f"call_{i}")],
            interaction_id=f"int_{i}",
        )
        for i in range(MAX_FILE_READS + 2)
    ]
    submit = _interaction(
        [_call_step("submit_remediation", {"summary": "s", "commit_message": "c", "edits": []})],
        interaction_id="int_final",
    )
    mock_client = MagicMock()
    mock_client.interactions.create.side_effect = [*reads, submit]
    mock_client_cls.return_value = mock_client

    file_reader = MagicMock(return_value="content")
    provider = GeminiRemediationProvider(api_key="fake", model="gemini-3.6-flash")

    result = provider.generate_remediation(_request(), file_reader)

    assert result.commit_message == "c"
    assert file_reader.call_count == MAX_FILE_READS


@patch("ticket_remediation.connectors.llm.gemini_provider.genai.Client")
def test_generate_remediation_raises_if_llm_never_submits(mock_client_cls):
    mock_client = MagicMock()
    mock_client.interactions.create.return_value = _interaction([])
    mock_client_cls.return_value = mock_client

    provider = GeminiRemediationProvider(api_key="fake", model="gemini-3.6-flash")

    with pytest.raises(ValueError, match="submit_remediation"):
        provider.generate_remediation(_request(), MagicMock())
