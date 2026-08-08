from pathlib import Path

import yaml
from pydantic import BaseModel


class IngestJiraMapping(BaseModel):
    project_key: str
    issue_type: str
    component_field: str
    label_fields: list[str]
    summary_template: str
    description_template: str


class IngestMappingRule(BaseModel):
    snow_table: str
    jira: IngestJiraMapping


class IngestMappingConfig(BaseModel):
    rules: list[IngestMappingRule]

    def rule_for_table(self, table: str) -> IngestMappingRule | None:
        for rule in self.rules:
            if rule.snow_table == table:
                return rule
        return None


class RepoRouteMatch(BaseModel):
    project_key: str
    components: list[str]


class RepoRouteTarget(BaseModel):
    owner: str
    name: str
    default_branch: str = "main"

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"


class RepoRoute(BaseModel):
    match: RepoRouteMatch
    repo: RepoRouteTarget


class RepoRoutingConfig(BaseModel):
    routes: list[RepoRoute]

    def route_for(self, project_key: str, component: str) -> RepoRoute | None:
        for route in self.routes:
            if route.match.project_key != project_key:
                continue
            if component in route.match.components:
                return route
        return None


def load_ingest_mapping(path: Path) -> IngestMappingConfig:
    raw = yaml.safe_load(path.read_text())
    return IngestMappingConfig.model_validate(raw)


def load_repo_routing(path: Path) -> RepoRoutingConfig:
    raw = yaml.safe_load(path.read_text())
    return RepoRoutingConfig.model_validate(raw)
