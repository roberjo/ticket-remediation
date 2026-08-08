from ticket_remediation.config.mapping import IngestMappingRule
from ticket_remediation.connectors.jira.base import JiraIssuePayload
from ticket_remediation.connectors.servicenow.base import SnowTicket


def _as_label(value: str) -> str:
    return value.strip().replace(" ", "-")


def to_jira_payload(ticket: SnowTicket, rule: IngestMappingRule) -> JiraIssuePayload:
    fields = ticket.model_dump()
    component = fields[rule.jira.component_field]
    labels = [_as_label(str(fields[field_name])) for field_name in rule.jira.label_fields]
    return JiraIssuePayload(
        project_key=rule.jira.project_key,
        issue_type=rule.jira.issue_type,
        summary=rule.jira.summary_template.format(**fields),
        description=rule.jira.description_template.format(**fields),
        components=[component],
        labels=labels,
    )
