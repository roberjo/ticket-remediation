from ticket_remediation.config.mapping import load_repo_routing
from ticket_remediation.connectors.jira.base import JiraIssue
from ticket_remediation.remediate.repo_selector import select_repo


def _issue(components: list[str]) -> JiraIssue:
    return JiraIssue(
        key="AVREM-1",
        project_key="AVREM",
        summary="summary",
        description="description",
        status="Ready for Remediation",
        components=components,
        labels=[],
    )


def test_select_repo_matches_configured_component(fixtures_dir):
    routing = load_repo_routing(fixtures_dir / "repo_routing_valid.yaml")

    repo = select_repo(_issue(["frontend"]), routing)

    assert repo is not None
    assert repo.full_name == "demo-org/vulnerable-react-demo-app"


def test_select_repo_returns_none_when_no_component_matches(fixtures_dir):
    routing = load_repo_routing(fixtures_dir / "repo_routing_valid.yaml")

    assert select_repo(_issue(["some-unmapped-component"]), routing) is None
