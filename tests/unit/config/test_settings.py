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
