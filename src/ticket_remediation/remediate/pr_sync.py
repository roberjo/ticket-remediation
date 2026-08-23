import logging
from dataclasses import dataclass, field

from ticket_remediation.connectors.github.base import GitHubClient
from ticket_remediation.db.repository import RemediationRunRepository

logger = logging.getLogger(__name__)


@dataclass
class PrSyncResult:
    merged: list[str] = field(default_factory=list)
    closed: list[str] = field(default_factory=list)
    checked: int = 0
    errors: list[str] = field(default_factory=list)


class PrStatusSyncer:
    """Polls GitHub for every remediation_runs row still in status="pr_open" and updates it to
    pr_merged or pr_closed once the PR resolves. remediation_runs.status = pr_merged has been
    reserved in the state machine since v1 but nothing set it until this — see
    docs/architecture/05-data-and-state-model.md."""

    def __init__(self, github_client: GitHubClient, runs: RemediationRunRepository):
        self._github = github_client
        self._runs = runs

    def sync(self) -> PrSyncResult:
        result = PrSyncResult()
        for run in self._runs.list_runs(status="pr_open"):
            if run["repo_full_name"] is None or run["pr_number"] is None:
                continue
            result.checked += 1
            try:
                pr = self._github.get_pull_request(run["repo_full_name"], run["pr_number"])
            except Exception:
                logger.exception("Failed to check PR status for %s", run["jira_key"])
                result.errors.append(run["jira_key"])
                continue

            if pr.merged:
                self._runs.upsert_run(run["jira_key"], status="pr_merged")
                result.merged.append(run["jira_key"])
            elif pr.state == "closed":
                self._runs.upsert_run(run["jira_key"], status="pr_closed")
                result.closed.append(run["jira_key"])
        return result
