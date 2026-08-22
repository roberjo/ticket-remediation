import logging
from dataclasses import dataclass, field

from ticket_remediation.config.mapping import IngestMappingConfig
from ticket_remediation.connectors.jira.base import JiraClient
from ticket_remediation.connectors.servicenow.base import ServiceNowClient
from ticket_remediation.db.repository import LinkRepository

from .mapper import to_jira_payload

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    created: list[str] = field(default_factory=list)
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    failed_tables: list[str] = field(default_factory=list)


class IngestPipeline:
    def __init__(
        self,
        snow_client: ServiceNowClient,
        jira_client: JiraClient,
        mapping: IngestMappingConfig,
        links: LinkRepository,
    ):
        self._snow = snow_client
        self._jira = jira_client
        self._mapping = mapping
        self._links = links

    def run(self, dry_run: bool = False) -> IngestResult:
        result = IngestResult()

        for rule in self._mapping.rules:
            try:
                tickets = self._snow.fetch_tickets(rule.snow_table)
            except Exception:
                logger.exception("Failed to fetch tickets from SNOW table %s", rule.snow_table)
                result.failed_tables.append(rule.snow_table)
                continue

            for ticket in tickets:
                if self._links.get_jira_key(rule.snow_table, ticket.sys_id) is not None:
                    result.skipped += 1
                    continue

                try:
                    payload = to_jira_payload(ticket, rule)

                    if dry_run:
                        logger.info(
                            "[dry-run] would create Jira issue for %s: %s",
                            ticket.number,
                            payload.summary,
                        )
                        result.created.append(f"[dry-run] {ticket.number}")
                        continue

                    ref = self._jira.create_issue(payload)
                except Exception:
                    logger.exception("Failed to create Jira issue for SNOW ticket %s", ticket.number)
                    result.failed.append(ticket.number)
                    continue

                self._links.record_link(rule.snow_table, ticket.sys_id, ticket.number, ref.key)
                logger.info("Created %s from SNOW ticket %s", ref.key, ticket.number)
                result.created.append(ref.key)

        return result
