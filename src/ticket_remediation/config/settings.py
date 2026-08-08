from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # ServiceNow
    snow_instance_url: str = "http://localhost:8001"
    snow_api_token: str = ""
    snow_avit_table: str = "x_avit_findings"

    # Jira
    jira_base_url: str = "http://localhost:8002"
    jira_email: str = ""
    jira_api_token: str = ""
    jira_project_key: str = "AVREM"
    jira_remediation_jql_status: str = "Ready for Remediation"

    # GitHub
    github_token: str = ""

    # LLM remediation provider: "anthropic" (paid) or "gemini" (free tier)
    llm_provider: str = "anthropic"
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.6-flash"

    # Notifications
    teams_webhook_url: str = ""
    slack_webhook_url: str = ""
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_addr: str = ""
    notify_email_to: str = ""

    # Local paths
    sqlite_db_path: Path = Path("data/state.db")
    ingest_mapping_path: Path = Path("config/ingest_mapping.yaml")
    repo_routing_path: Path = Path("config/repo_routing.yaml")
    work_dir: Path = Field(default=Path("work"))
