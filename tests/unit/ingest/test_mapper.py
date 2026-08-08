import json

from ticket_remediation.config.mapping import load_ingest_mapping
from ticket_remediation.connectors.servicenow.base import SnowTicket
from ticket_remediation.ingest.mapper import to_jira_payload


def _load_ticket(fixtures_dir):
    raw = json.loads((fixtures_dir / "snow_incident_sample.json").read_text())["result"][0]
    return SnowTicket.model_validate(raw)


def test_to_jira_payload_applies_mapping_rule(fixtures_dir):
    mapping = load_ingest_mapping(fixtures_dir / "ingest_mapping_valid.yaml")
    rule = mapping.rule_for_table("x_avit_findings")
    ticket = _load_ticket(fixtures_dir)

    payload = to_jira_payload(ticket, rule)

    assert payload.project_key == "AVREM"
    assert payload.issue_type == "Vulnerability"
    assert payload.components == ["frontend"]
    assert payload.labels == ["High", "Reflected-Cross-Site-Scripting-(XSS)"]
    assert "Reflected Cross-Site Scripting (XSS)" in payload.summary
    assert "CWE: CWE-79" in payload.description
