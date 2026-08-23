import pytest
from pydantic import ValidationError

from ticket_remediation.config.settings import Settings


def test_log_settings_defaults():
    settings = Settings(_env_file=None)
    assert settings.log_level == "INFO"
    assert settings.log_format == "text"


def test_log_settings_env_overrides(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("LOG_FORMAT", "json")

    settings = Settings(_env_file=None)

    assert settings.log_level == "DEBUG"
    assert settings.log_format == "json"


def test_log_level_rejects_invalid_value(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "NOT_A_LEVEL")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_blank_max_llm_calls_env_value_means_unset(monkeypatch):
    """Regression test: .env.example documents REMEDIATE_MAX_LLM_CALLS_PER_RUN= (blank = no
    cap), matching the pattern every str field here uses. Copying that literally into a real
    .env, or passing it via `docker run --env-file`, sets the process env var to the literal
    empty string — which used to crash Settings() outright trying to parse "" as an int."""
    monkeypatch.setenv("REMEDIATE_MAX_LLM_CALLS_PER_RUN", "")

    settings = Settings(_env_file=None)

    assert settings.remediate_max_llm_calls_per_run is None


def test_nonblank_max_llm_calls_env_value_still_parses(monkeypatch):
    monkeypatch.setenv("REMEDIATE_MAX_LLM_CALLS_PER_RUN", "7")

    settings = Settings(_env_file=None)

    assert settings.remediate_max_llm_calls_per_run == 7
