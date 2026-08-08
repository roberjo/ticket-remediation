from ticket_remediation.config.settings import Settings

from .anthropic_provider import AnthropicRemediationProvider
from .base import LLMProvider
from .gemini_provider import GeminiRemediationProvider


def get_llm_provider(settings: Settings) -> LLMProvider:
    if settings.llm_provider == "anthropic":
        return AnthropicRemediationProvider(
            api_key=settings.anthropic_api_key, model=settings.anthropic_model
        )
    if settings.llm_provider == "gemini":
        return GeminiRemediationProvider(api_key=settings.gemini_api_key, model=settings.gemini_model)
    raise ValueError(f"Unknown LLM_PROVIDER: {settings.llm_provider!r}")
