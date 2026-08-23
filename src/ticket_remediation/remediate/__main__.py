import json
import logging
from dataclasses import asdict

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
from .pr_sync import PrStatusSyncer

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
    verbose: bool = typer.Option(
        False, "--verbose", help="Set the log level to DEBUG for this run, overriding log_level"
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Print the final run summary as a JSON object instead of log lines"
    ),
    ticket: str | None = typer.Option(
        None, "--ticket", help="Remediate only this Jira issue key, bypassing the jql_status filter"
    ),
    force: bool = typer.Option(
        False,
        "--force",
        help="Bypass the skip gate (delivered/ignored/permanently-failed) for --ticket. Requires --ticket.",
    ),
) -> None:
    if force and not ticket:
        raise typer.BadParameter(
            "--force has no effect without --ticket; it never applies to a full batch run"
        )

    settings = Settings()
    log_level = logging.DEBUG if verbose else getattr(logging, settings.log_level.upper())
    configure_logging(level=log_level, json_output=settings.log_format == "json")
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
                ticket_key=ticket,
                bypass_skip_for=ticket if force else None,
            )
    except LockHeldError:
        logger.info("Another remediate run is already in progress, skipping this tick")
        raise typer.Exit(0) from None

    if json_output:
        typer.echo(json.dumps(asdict(result)))
    else:
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


@app.command(name="sync-pr-status")
def sync_pr_status(
    json_output: bool = typer.Option(
        False, "--json", help="Print the sync summary as a JSON object instead of a log line"
    ),
) -> None:
    """Poll GitHub for every pr_open run and mark it pr_merged/pr_closed as its PR resolves.
    Meant to run on its own, more frequent cron schedule than `run` — it never touches Jira,
    the LLM, or a git working directory, only GitHub's PR state and local run records."""
    settings = Settings()
    configure_logging(
        level=getattr(logging, settings.log_level.upper()), json_output=settings.log_format == "json"
    )
    github = GitHubRestClient(settings.github_token)
    conn = get_connection(settings.sqlite_db_path)
    runs = RemediationRunRepository(conn)

    lock_path = settings.sqlite_db_path.parent / "sync-pr-status.lock"
    try:
        with pipeline_lock(lock_path):
            result = PrStatusSyncer(github, runs).sync()
    except LockHeldError:
        logger.info("Another sync-pr-status run is already in progress, skipping this tick")
        raise typer.Exit(0) from None

    if json_output:
        typer.echo(json.dumps(asdict(result)))
    else:
        logger.info(
            "PR status sync complete: checked=%d merged=%d closed=%d errors=%d",
            result.checked,
            len(result.merged),
            len(result.closed),
            len(result.errors),
        )


@app.command()
def status(
    status_filter: str | None = typer.Option(
        None, "--status", help="Only show runs with this status (e.g. pr_open, failed, ignored)"
    ),
) -> None:
    """List recorded remediation runs, optionally filtered by status."""
    settings = Settings()
    conn = get_connection(settings.sqlite_db_path)
    runs = RemediationRunRepository(conn)
    rows = runs.list_runs(status=status_filter)

    if not rows:
        typer.echo("No remediation runs recorded.")
        return

    header = f"{'JIRA_KEY':<12} {'STATUS':<15} {'REPO':<32} {'FAILURES':<8} {'STAGE':<14} {'PR_URL'}"
    typer.echo(header)
    for row in rows:
        typer.echo(
            f"{row['jira_key']:<12} {row['status']:<15} {(row['repo_full_name'] or '-'):<32} "
            f"{row['failure_count']:<8} {(row['stage'] or '-'):<14} {row['pr_url'] or '-'}"
        )


@app.command()
def show(jira_key: str) -> None:
    """Print full detail for a single remediation run."""
    settings = Settings()
    conn = get_connection(settings.sqlite_db_path)
    runs = RemediationRunRepository(conn)
    run_row = runs.get_run(jira_key)

    if run_row is None:
        typer.echo(f"No run recorded for {jira_key}")
        raise typer.Exit(code=1)

    for key in run_row.keys():
        typer.echo(f"{key}: {run_row[key]}")


@app.command()
def ignore(
    jira_key: str,
    reason: str | None = typer.Option(None, "--reason", help="Optional reason recorded with the ignore"),
) -> None:
    """Mark a Jira issue as ignored so future runs skip it without retrying."""
    settings = Settings()
    conn = get_connection(settings.sqlite_db_path)
    runs = RemediationRunRepository(conn)
    runs.mark_ignored(jira_key, reason=reason)
    suffix = f" ({reason})" if reason else ""
    typer.echo(f"{jira_key} marked as ignored{suffix}")


if __name__ == "__main__":
    app()
