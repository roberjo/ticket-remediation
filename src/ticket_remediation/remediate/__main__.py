import logging

import typer

from ticket_remediation.config.mapping import load_repo_routing
from ticket_remediation.config.settings import Settings
from ticket_remediation.connectors.github.rest import GitHubRestClient
from ticket_remediation.connectors.jira.rest import JiraRestClient
from ticket_remediation.connectors.llm.factory import get_llm_provider
from ticket_remediation.connectors.notify.composite import build_notifier
from ticket_remediation.db.connection import get_connection
from ticket_remediation.db.repository import RemediationRunRepository
from ticket_remediation.logging_config import configure_logging
from ticket_remediation.pipeline_lock import LockHeldError, pipeline_lock

from .pipeline import RemediatePipeline

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.callback()
def main() -> None:
    """Jira (AVREM) -> GitHub PR remediation pipeline."""


@app.command()
def run(
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Generate and write the fix locally but skip commit/push/PR/notify"
    ),
) -> None:
    settings = Settings()
    configure_logging(
        level=getattr(logging, settings.log_level.upper()),
        json_output=settings.log_format == "json",
    )
    routing = load_repo_routing(settings.repo_routing_path)

    jira = JiraRestClient(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    github = GitHubRestClient(settings.github_token)
    llm = get_llm_provider(settings)
    notifier = build_notifier(settings)
    conn = get_connection(settings.sqlite_db_path)
    runs = RemediationRunRepository(conn)

    pipeline = RemediatePipeline(
        jira_client=jira,
        github_client=github,
        llm_provider=llm,
        notifier=notifier,
        routing=routing,
        runs=runs,
        github_token=settings.github_token,
        jira_base_url=settings.jira_base_url,
        work_dir=settings.work_dir,
        max_retries=settings.remediate_max_retries,
        max_llm_calls=settings.remediate_max_llm_calls_per_run,
    )

    lock_path = settings.sqlite_db_path.parent / "remediate.lock"
    try:
        with pipeline_lock(lock_path):
            result = pipeline.run(
                jql_status=settings.jira_remediation_jql_status,
                project_key=settings.jira_project_key,
                dry_run=dry_run,
            )
    except LockHeldError:
        logger.info("Another remediate run is already in progress, skipping this tick")
        raise typer.Exit(0) from None

    logger.info(
        "Remediate complete: opened=%d skipped=%d blocked=%d deferred=%d failed=%d",
        len(result.opened_prs),
        result.skipped,
        len(result.blocked),
        result.deferred,
        len(result.failed),
    )
    if result.batch_error:
        logger.error("Remediate batch failed: %s", result.batch_error)
    if result.failed or result.batch_error:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
