import logging

import typer

from ticket_remediation.config.mapping import load_ingest_mapping
from ticket_remediation.config.settings import Settings
from ticket_remediation.connectors.jira.rest import JiraRestClient
from ticket_remediation.connectors.servicenow.rest import ServiceNowRestClient
from ticket_remediation.db.connection import get_connection
from ticket_remediation.db.repository import LinkRepository
from ticket_remediation.logging_config import configure_logging
from ticket_remediation.pipeline_lock import LockHeldError, pipeline_lock

from .pipeline import IngestPipeline

app = typer.Typer()
logger = logging.getLogger(__name__)


@app.callback()
def main() -> None:
    """ServiceNow (AVIT) -> Jira ingest pipeline."""


@app.command()
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Log what would be created without calling Jira"),
) -> None:
    configure_logging()
    settings = Settings()
    mapping = load_ingest_mapping(settings.ingest_mapping_path)

    snow = ServiceNowRestClient(settings.snow_instance_url, settings.snow_api_token)
    jira = JiraRestClient(settings.jira_base_url, settings.jira_email, settings.jira_api_token)
    conn = get_connection(settings.sqlite_db_path)
    links = LinkRepository(conn)

    lock_path = settings.sqlite_db_path.parent / "ingest.lock"
    try:
        with pipeline_lock(lock_path):
            result = IngestPipeline(snow, jira, mapping, links).run(dry_run=dry_run)
    except LockHeldError:
        logger.info("Another ingest run is already in progress, skipping this tick")
        raise typer.Exit(0) from None

    logger.info(
        "Ingest complete: created=%d skipped=%d failed=%d",
        len(result.created),
        result.skipped,
        len(result.failed),
    )
    if result.failed:
        raise typer.Exit(code=1)


if __name__ == "__main__":
    app()
