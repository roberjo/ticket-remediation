from datetime import datetime

from ticket_remediation.config.mapping import IngestMappingConfig
from ticket_remediation.connectors.jira.base import JiraIssuePayload, JiraIssueRef
from ticket_remediation.connectors.notify.base import NotificationMessage
from ticket_remediation.connectors.servicenow.base import SnowTicket
from ticket_remediation.db.repository import LinkRepository
from ticket_remediation.ingest.pipeline import IngestPipeline


def _ticket(sys_id: str, number: str, short_description: str = "Reflected XSS in /search") -> SnowTicket:
    return SnowTicket(
        sys_id=sys_id,
        number=number,
        short_description=short_description,
        description="desc",
        severity="High",
        cvss_score=7.2,
        vuln_type="Reflected Cross-Site Scripting (XSS)",
        cwe_id="CWE-79",
        affected_component="frontend",
        affected_url_or_file="/search",
        source_scanner="Snyk",
        discovered_at="2026-08-01T00:00:00+00:00",
        priority="2 - High",
    )


class FakeServiceNowClient:
    def __init__(
        self,
        tickets_by_table: dict[str, list[SnowTicket]] | list[SnowTicket],
        fail_for: set[str] | None = None,
    ):
        if isinstance(tickets_by_table, list):
            tickets_by_table = {"x_avit_findings": tickets_by_table}
        self._tickets_by_table = tickets_by_table
        self._fail_for = fail_for or set()

    def fetch_tickets(self, table: str, since: datetime | None = None) -> list[SnowTicket]:
        if table in self._fail_for:
            raise RuntimeError("SNOW is down")
        return self._tickets_by_table.get(table, [])


class FakeJiraClient:
    def __init__(self, fail_for: set[str] | None = None):
        self.created: list[JiraIssuePayload] = []
        self._fail_for = fail_for or set()
        self._counter = 0

    def create_issue(self, payload: JiraIssuePayload) -> JiraIssueRef:
        if payload.summary in self._fail_for:
            raise RuntimeError("boom")
        self._counter += 1
        self.created.append(payload)
        key = f"AVREM-{self._counter}"
        return JiraIssueRef(key=key, url=f"https://example.atlassian.net/browse/{key}")

    def search_issues(self, jql: str):
        raise NotImplementedError

    def add_comment(self, key: str, body: str) -> None:
        raise NotImplementedError

    def transition_issue(self, key: str, transition_name: str) -> None:
        raise NotImplementedError


class FakeNotifier:
    def __init__(self):
        self.messages: list[NotificationMessage] = []

    def notify(self, message: NotificationMessage) -> None:
        self.messages.append(message)


def _rule(snow_table: str = "x_avit_findings", summary_template: str = "{short_description}") -> dict:
    return {
        "snow_table": snow_table,
        "jira": {
            "project_key": "AVREM",
            "issue_type": "Vulnerability",
            "component_field": "affected_component",
            "label_fields": ["severity"],
            "summary_template": summary_template,
            "description_template": "{description}",
        },
    }


def _mapping(*rules: dict) -> IngestMappingConfig:
    return IngestMappingConfig(rules=list(rules) or [_rule()])


def test_ingest_pipeline_creates_one_issue_per_new_ticket(db_conn):
    tickets = [_ticket("sys-1", "AVIT1"), _ticket("sys-2", "AVIT2")]
    snow = FakeServiceNowClient(tickets)
    jira = FakeJiraClient()
    links = LinkRepository(db_conn)

    result = IngestPipeline(snow, jira, _mapping(), links, FakeNotifier()).run()

    assert result.created == ["AVREM-1", "AVREM-2"]
    assert result.skipped == 0
    assert result.failed == []
    assert len(jira.created) == 2


def test_ingest_pipeline_is_idempotent_on_second_run(db_conn):
    tickets = [_ticket("sys-1", "AVIT1")]
    snow = FakeServiceNowClient(tickets)
    jira = FakeJiraClient()
    links = LinkRepository(db_conn)
    pipeline = IngestPipeline(snow, jira, _mapping(), links, FakeNotifier())

    first = pipeline.run()
    second = pipeline.run()

    assert first.created == ["AVREM-1"]
    assert second.created == []
    assert second.skipped == 1
    assert len(jira.created) == 1  # not created twice


def test_ingest_pipeline_one_failure_does_not_block_the_rest(db_conn):
    tickets = [
        _ticket("sys-1", "AVIT1", short_description="Reflected XSS in /search"),
        _ticket("sys-2", "AVIT2", short_description="Hardcoded API key in config.js"),
    ]
    snow = FakeServiceNowClient(tickets)
    jira = FakeJiraClient(fail_for={"Reflected XSS in /search"})
    links = LinkRepository(db_conn)
    notifier = FakeNotifier()

    result = IngestPipeline(snow, jira, _mapping(), links, notifier).run()

    assert result.failed == ["AVIT1"]
    assert result.created == ["AVREM-1"]  # the second ticket still gets created
    assert len(jira.created) == 1
    assert len(notifier.messages) == 1
    assert notifier.messages[0].level == "failure"


def test_ingest_pipeline_one_table_fetch_failure_does_not_block_other_tables(db_conn):
    tickets_by_table = {
        "x_avit_findings": [_ticket("sys-1", "AVIT1")],
        "x_avit_other": [_ticket("sys-2", "AVIT2", short_description="Hardcoded API key")],
    }
    snow = FakeServiceNowClient(tickets_by_table, fail_for={"x_avit_findings"})
    jira = FakeJiraClient()
    links = LinkRepository(db_conn)
    mapping = _mapping(_rule("x_avit_findings"), _rule("x_avit_other"))
    notifier = FakeNotifier()

    result = IngestPipeline(snow, jira, mapping, links, notifier).run()

    assert result.failed_tables == ["x_avit_findings"]
    assert result.created == ["AVREM-1"]
    assert len(jira.created) == 1
    assert len(notifier.messages) == 1
    assert notifier.messages[0].level == "failure"


def test_ingest_pipeline_bad_mapping_for_one_ticket_does_not_block_others(db_conn):
    tickets_by_table = {
        "x_avit_bad": [_ticket("sys-1", "AVIT1", short_description="Reflected XSS in /search")],
        "x_avit_good": [_ticket("sys-2", "AVIT2", short_description="Hardcoded API key in config.js")],
    }
    snow = FakeServiceNowClient(tickets_by_table)
    jira = FakeJiraClient()
    links = LinkRepository(db_conn)
    mapping = _mapping(
        _rule("x_avit_bad", summary_template="{missing_field}"),
        _rule("x_avit_good"),
    )

    result = IngestPipeline(snow, jira, mapping, links, FakeNotifier()).run()

    assert result.failed == ["AVIT1"]
    assert result.created == ["AVREM-1"]  # the ticket with a working mapping still succeeds
    assert len(jira.created) == 1
