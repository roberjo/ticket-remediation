from ticket_remediation.config.mapping import RepoRouteTarget, RepoRoutingConfig
from ticket_remediation.connectors.jira.base import JiraIssue


def select_repo(issue: JiraIssue, routing: RepoRoutingConfig) -> RepoRouteTarget | None:
    for component in issue.components:
        route = routing.route_for(issue.project_key, component)
        if route is not None:
            return route.repo
    return None
