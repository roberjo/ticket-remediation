CREATE TABLE IF NOT EXISTS snow_jira_links (
    snow_table   TEXT NOT NULL,
    snow_sys_id  TEXT NOT NULL,
    snow_number  TEXT,
    jira_key     TEXT NOT NULL,
    created_at   TEXT NOT NULL,
    PRIMARY KEY (snow_table, snow_sys_id)
);

CREATE TABLE IF NOT EXISTS remediation_runs (
    jira_key        TEXT PRIMARY KEY,
    status           TEXT NOT NULL,   -- branch_created | pr_open | pr_merged | failed
    repo_full_name   TEXT,
    branch_name      TEXT,
    pr_url           TEXT,
    pr_number        INTEGER,
    last_attempt_at  TEXT NOT NULL,
    error_message    TEXT
);
