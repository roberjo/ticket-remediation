import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

from ticket_remediation.config.mapping import RepoRouteTarget, RepoRoutingConfig
from ticket_remediation.connectors.github import git_ops
from ticket_remediation.connectors.github.base import GitHubClient
from ticket_remediation.connectors.jira.base import JiraClient, JiraIssue
from ticket_remediation.connectors.llm.base import (
    FileEdit,
    LLMProvider,
    RemediationRequest,
    RemediationResponse,
)
from ticket_remediation.connectors.notify.base import NotificationMessage, Notifier
from ticket_remediation.db.repository import RemediationRunRepository

from .context_builder import build_file_tree, make_file_reader
from .repo_selector import select_repo

logger = logging.getLogger(__name__)

MAX_EDIT_FILES = 20
MAX_EDIT_TOTAL_BYTES = 500_000


def _slugify(text: str, max_len: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug[:max_len].rstrip("-")


def _branch_name(jira_key: str, summary: str) -> str:
    return f"remediate/{jira_key}-{_slugify(summary)}"


@dataclass
class RemediateResult:
    opened_prs: list[str] = field(default_factory=list)
    skipped: int = 0
    failed: list[str] = field(default_factory=list)
    batch_error: str | None = None


class RemediatePipeline:
    def __init__(
        self,
        jira_client: JiraClient,
        github_client: GitHubClient,
        llm_provider: LLMProvider,
        notifier: Notifier,
        routing: RepoRoutingConfig,
        runs: RemediationRunRepository,
        github_token: str,
        jira_base_url: str,
        work_dir: Path,
    ):
        self._jira = jira_client
        self._github = github_client
        self._llm = llm_provider
        self._notifier = notifier
        self._routing = routing
        self._runs = runs
        self._github_token = github_token
        self._jira_base_url = jira_base_url.rstrip("/")
        self._work_dir = work_dir

    def run(self, jql_status: str, project_key: str, dry_run: bool = False) -> RemediateResult:
        result = RemediateResult()
        jql = f'project = {project_key} AND status = "{jql_status}"'
        try:
            issues = self._jira.search_issues(jql)
        except Exception as exc:
            logger.exception("Failed to search Jira issues with jql=%s", jql)
            result.batch_error = str(exc)
            return result

        for issue in issues:
            if self._runs.is_already_delivered(issue.key):
                result.skipped += 1
                continue

            repo_target = select_repo(issue, self._routing)
            if repo_target is None:
                logger.warning(
                    "No repo route configured for %s (project=%s components=%s)",
                    issue.key,
                    issue.project_key,
                    issue.components,
                )
                result.failed.append(issue.key)
                continue

            try:
                self._remediate_one(issue, repo_target, dry_run)
                result.opened_prs.append(issue.key)
            except Exception as exc:
                logger.exception("Remediation failed for %s", issue.key)
                self._runs.upsert_run(issue.key, status="failed", error_message=str(exc))
                result.failed.append(issue.key)

        return result

    def _remediate_one(self, issue: JiraIssue, repo_target: RepoRouteTarget, dry_run: bool) -> None:
        default_branch = repo_target.default_branch or self._github.get_default_branch(repo_target.full_name)
        repo_path = git_ops.clone_or_update(
            repo_target.full_name, self._github_token, default_branch, self._work_dir
        )

        branch = _branch_name(issue.key, issue.summary)
        git_ops.create_branch(repo_path, branch, default_branch)
        self._runs.upsert_run(
            issue.key,
            status="branch_created",
            repo_full_name=repo_target.full_name,
            branch_name=branch,
        )

        file_tree = build_file_tree(repo_path)
        file_reader = make_file_reader(repo_path)
        request = RemediationRequest(
            jira_key=issue.key,
            summary=issue.summary,
            description=issue.description,
            file_tree=file_tree,
        )
        remediation = self._llm.generate_remediation(request, file_reader)

        changed_files = self._apply_edits(repo_path, remediation.edits)

        if dry_run:
            logger.info("[dry-run] %s would change: %s", issue.key, changed_files)
            return

        commit_message = (
            f"{issue.key}: {remediation.commit_message}\n\nJira: {self._jira_base_url}/browse/{issue.key}"
        )
        git_ops.commit_all(repo_path, commit_message)
        git_ops.push_branch(repo_path, branch)

        pr = self._github.create_pull_request(
            repo_target.full_name,
            head=branch,
            base=default_branch,
            title=f"[{issue.key}] {issue.summary}",
            body=self._pr_body(issue, remediation, changed_files),
        )
        # The PR now exists, so this run has already succeeded — record that before
        # doing anything else. A failure in the comment or notification steps below
        # must not overwrite status back to "failed": that would make the next run
        # think no PR exists yet and collide with the one that's already open.
        self._runs.upsert_run(issue.key, status="pr_open", pr_url=pr.url, pr_number=pr.number)

        try:
            self._jira.add_comment(issue.key, f"Automated remediation PR opened: {pr.url}")
        except Exception:
            logger.exception("Failed to comment on %s (PR %s was still opened)", issue.key, pr.url)

        try:
            self._notifier.notify(
                NotificationMessage(
                    title=f"Remediation PR opened for {issue.key}",
                    body=f"{issue.summary}\n\nChanged files: {', '.join(changed_files)}",
                    pr_url=pr.url,
                    jira_key=issue.key,
                )
            )
        except Exception:
            logger.exception("Failed to notify for %s (PR %s was still opened)", issue.key, pr.url)

    def _apply_edits(self, repo_path: Path, edits: list[FileEdit]) -> list[str]:
        if len(edits) > MAX_EDIT_FILES:
            raise ValueError(f"LLM returned {len(edits)} file edits, exceeding the limit of {MAX_EDIT_FILES}")
        total_bytes = sum(len(edit.content or "") for edit in edits)
        if total_bytes > MAX_EDIT_TOTAL_BYTES:
            raise ValueError(
                f"LLM edits total {total_bytes} bytes, exceeding the limit of {MAX_EDIT_TOTAL_BYTES}"
            )

        repo_root = repo_path.resolve()
        changed = []
        for edit in edits:
            target = (repo_root / edit.path).resolve()
            if target != repo_root and repo_root not in target.parents:
                raise ValueError(f"Refusing to write outside repo working directory: {edit.path}")
            if edit.action == "delete":
                target.unlink(missing_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(edit.content or "")
            changed.append(edit.path)
        return changed

    def _pr_body(self, issue: JiraIssue, remediation: RemediationResponse, changed_files: list[str]) -> str:
        changed_list = "\n".join(f"- {path}" for path in changed_files)
        return (
            f"Jira: {self._jira_base_url}/browse/{issue.key}\n\n"
            f"## Original ticket\n{issue.description}\n\n"
            f"## Remediation summary\n{remediation.summary}\n\n"
            f"## Changed files\n{changed_list}\n\n"
            "_This PR was opened automatically by the ticket-remediation pipeline._"
        )
