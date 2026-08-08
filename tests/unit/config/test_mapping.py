import pydantic
import pytest

from ticket_remediation.config.mapping import load_ingest_mapping, load_repo_routing


def test_load_ingest_mapping_valid(fixtures_dir):
    config = load_ingest_mapping(fixtures_dir / "ingest_mapping_valid.yaml")
    rule = config.rule_for_table("x_avit_findings")
    assert rule is not None
    assert rule.jira.project_key == "AVREM"
    assert rule.jira.component_field == "affected_component"
    assert config.rule_for_table("does_not_exist") is None


def test_load_ingest_mapping_invalid_raises(fixtures_dir):
    with pytest.raises(pydantic.ValidationError):
        load_ingest_mapping(fixtures_dir / "ingest_mapping_invalid.yaml")


def test_load_repo_routing_valid(fixtures_dir):
    config = load_repo_routing(fixtures_dir / "repo_routing_valid.yaml")
    route = config.route_for("AVREM", "frontend")
    assert route is not None
    assert route.repo.full_name == "demo-org/vulnerable-react-demo-app"
    assert config.route_for("AVREM", "some-other-component") is None
    assert config.route_for("OTHER-PROJECT", "frontend") is None
