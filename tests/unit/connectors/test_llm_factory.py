import pytest

from ticket_remediation.config.settings import Settings
from ticket_remediation.connectors.llm.anthropic_provider import AnthropicRemediationProvider
from ticket_remediation.connectors.llm.factory import get_llm_provider
from ticket_remediation.connectors.llm.gemini_provider import GeminiRemediationProvider


def test_get_llm_provider_returns_anthropic_provider_for_anthropic():
    settings = Settings(
        _env_file=None, llm_provider="anthropic", anthropic_api_key="fake-key", anthropic_model="claude-x"
    )

    provider = get_llm_provider(settings)

    assert isinstance(provider, AnthropicRemediationProvider)


def test_get_llm_provider_returns_gemini_provider_for_gemini():
    settings = Settings(
        _env_file=None, llm_provider="gemini", gemini_api_key="fake-key", gemini_model="gemini-x"
    )

    provider = get_llm_provider(settings)

    assert isinstance(provider, GeminiRemediationProvider)


def test_get_llm_provider_raises_for_an_unknown_provider_name():
    settings = Settings(_env_file=None, llm_provider="not-a-real-provider")

    with pytest.raises(ValueError, match="Unknown LLM_PROVIDER"):
        get_llm_provider(settings)
