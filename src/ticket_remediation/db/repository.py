import sqlite3
from datetime import UTC, datetime


def _now() -> str:
    return datetime.now(UTC).isoformat()


class LinkRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_jira_key(self, snow_table: str, snow_sys_id: str) -> str | None:
        row = self._conn.execute(
            "SELECT jira_key FROM snow_jira_links WHERE snow_table = ? AND snow_sys_id = ?",
            (snow_table, snow_sys_id),
        ).fetchone()
        return row["jira_key"] if row else None

    def record_link(self, snow_table: str, snow_sys_id: str, snow_number: str, jira_key: str) -> None:
        self._conn.execute(
            """
            INSERT INTO snow_jira_links (snow_table, snow_sys_id, snow_number, jira_key, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (snow_table, snow_sys_id) DO NOTHING
            """,
            (snow_table, snow_sys_id, snow_number, jira_key, _now()),
        )
        self._conn.commit()

    def list_links(self) -> list[sqlite3.Row]:
        return self._conn.execute("SELECT * FROM snow_jira_links ORDER BY created_at DESC").fetchall()


class RemediationRunRepository:
    def __init__(self, conn: sqlite3.Connection):
        self._conn = conn

    def get_run(self, jira_key: str) -> sqlite3.Row | None:
        return self._conn.execute("SELECT * FROM remediation_runs WHERE jira_key = ?", (jira_key,)).fetchone()

    def list_runs(self, status: str | None = None) -> list[sqlite3.Row]:
        if status is not None:
            return self._conn.execute(
                "SELECT * FROM remediation_runs WHERE status = ? ORDER BY last_attempt_at DESC",
                (status,),
            ).fetchall()
        return self._conn.execute(
            "SELECT * FROM remediation_runs ORDER BY last_attempt_at DESC"
        ).fetchall()

    def upsert_run(
        self,
        jira_key: str,
        status: str,
        repo_full_name: str | None = None,
        branch_name: str | None = None,
        pr_url: str | None = None,
        pr_number: int | None = None,
        error_message: str | None = None,
        stage: str | None = None,
    ) -> None:
        self._conn.execute(
            """
            INSERT INTO remediation_runs
                (jira_key, status, repo_full_name, branch_name, pr_url, pr_number,
                 last_attempt_at, error_message, failure_count, stage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (jira_key) DO UPDATE SET
                status = excluded.status,
                repo_full_name = COALESCE(excluded.repo_full_name, remediation_runs.repo_full_name),
                branch_name = COALESCE(excluded.branch_name, remediation_runs.branch_name),
                pr_url = COALESCE(excluded.pr_url, remediation_runs.pr_url),
                pr_number = COALESCE(excluded.pr_number, remediation_runs.pr_number),
                last_attempt_at = excluded.last_attempt_at,
                error_message = excluded.error_message,
                failure_count = CASE
                    WHEN excluded.status = 'failed' THEN remediation_runs.failure_count + 1
                    ELSE 0
                END,
                stage = excluded.stage
            """,
            (
                jira_key,
                status,
                repo_full_name,
                branch_name,
                pr_url,
                pr_number,
                _now(),
                error_message,
                1 if status == "failed" else 0,
                stage,
            ),
        )
        self._conn.commit()

    def is_already_delivered(self, jira_key: str) -> bool:
        run = self.get_run(jira_key)
        return run is not None and run["status"] in ("pr_open", "pr_merged")

    def is_permanently_failed(self, jira_key: str, max_failures: int) -> bool:
        run = self.get_run(jira_key)
        return run is not None and run["status"] == "failed" and run["failure_count"] >= max_failures

    def mark_ignored(self, jira_key: str, reason: str | None = None) -> None:
        self.upsert_run(jira_key, status="ignored", error_message=reason)

    def should_skip(self, jira_key: str, max_retries: int) -> bool:
        if self.is_already_delivered(jira_key):
            return True
        run = self.get_run(jira_key)
        # ignored: an operator decision (see mark_ignored). pr_closed: a human already closed
        # the PR without merging it — treated the same way, since re-opening a fresh PR for a
        # rejected fix should be a deliberate `--force` retry, not an automatic one.
        if run is not None and run["status"] in ("ignored", "pr_closed"):
            return True
        return self.is_permanently_failed(jira_key, max_retries)
