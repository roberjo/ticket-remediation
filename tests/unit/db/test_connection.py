import sqlite3

from ticket_remediation.db.connection import get_connection


def test_get_connection_backfills_new_columns_on_a_pre_existing_db(tmp_path):
    db_path = tmp_path / "state.db"
    old_conn = sqlite3.connect(str(db_path))
    old_conn.execute(
        """
        CREATE TABLE remediation_runs (
            jira_key        TEXT PRIMARY KEY,
            status           TEXT NOT NULL,
            repo_full_name   TEXT,
            branch_name      TEXT,
            pr_url           TEXT,
            pr_number        INTEGER,
            last_attempt_at  TEXT NOT NULL,
            error_message    TEXT
        )
        """
    )
    old_conn.execute(
        "INSERT INTO remediation_runs (jira_key, status, last_attempt_at) VALUES ('AVREM-1', 'failed', 'now')"
    )
    old_conn.commit()
    old_conn.close()

    conn = get_connection(db_path)
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(remediation_runs)").fetchall()}
    assert "failure_count" in columns
    assert "stage" in columns

    row = conn.execute(
        "SELECT failure_count, stage FROM remediation_runs WHERE jira_key = 'AVREM-1'"
    ).fetchone()
    assert row["failure_count"] == 0
    assert row["stage"] is None

    # Calling get_connection again against the already-migrated DB must not raise.
    get_connection(db_path)
