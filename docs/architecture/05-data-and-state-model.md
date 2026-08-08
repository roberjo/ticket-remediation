# 5. Data & State Model

## 5.1 Entity-relationship diagram (SQLite state)

`data/state.db` holds exactly two tables, both created via `CREATE TABLE IF NOT EXISTS` (no
migration tool — see [ADR-3](02-solution-strategy.md#adr-3-stateidempotency-lives-in-one-local-sqlite-file)).
They are not foreign-keyed to each other; the join between them is logical (`jira_key`), not
enforced by the schema, because a `snow_jira_links` row is written by `ingest` and a
`remediation_runs` row by `remediate` — two independent processes that never share a transaction.

```mermaid
erDiagram
    SNOW_JIRA_LINKS {
        text snow_table PK
        text snow_sys_id PK
        text snow_number
        text jira_key
        text created_at
    }
    REMEDIATION_RUNS {
        text jira_key PK
        text status
        text repo_full_name
        text branch_name
        text pr_url
        integer pr_number
        text last_attempt_at
        text error_message
    }
    SNOW_JIRA_LINKS ||--o| REMEDIATION_RUNS : "jira_key (logical, not FK-enforced)"
```

| Table | Written by | Read by | Purpose |
|---|---|---|---|
| `snow_jira_links` | `IngestPipeline` | `IngestPipeline` | "Has this exact SNOW ticket already become a Jira issue?" — primary key is the natural key `(snow_table, snow_sys_id)`, so a second `INSERT` for the same ticket is a no-op (`ON CONFLICT DO NOTHING`). |
| `remediation_runs` | `RemediatePipeline` | `RemediatePipeline` | "Does this Jira issue already have a delivered PR?" plus a progress trail (`branch_created` → `pr_open`) so a crashed mid-run is inspectable via the `sqlite3` CLI. |

## 5.2 Domain model — the transformation chain

Data flows through a chain of pydantic models, each owned by the connector whose boundary it
crosses. Nothing is a raw `dict` at a pipeline boundary — every hop is a typed, validated model.

```mermaid
classDiagram
    class SnowTicket {
        ServiceNow domain
    }
    class JiraIssuePayload {
        input to Jira.create_issue
    }
    class JiraIssueRef {
        output of Jira.create_issue
    }
    class JiraIssue {
        output of Jira.search_issues
    }
    class RemediationRequest {
        input to LLMProvider
    }
    class RemediationResponse {
        output of LLMProvider
    }
    class FileEdit
    class PullRequestRef {
        output of GitHub.create_pull_request
    }
    class NotificationMessage {
        input to Notifier
    }

    SnowTicket ..> JiraIssuePayload : ingest/mapper.py\nto_jira_payload()
    JiraIssuePayload ..> JiraIssueRef : JiraClient.create_issue()
    JiraIssue ..> RemediationRequest : RemediatePipeline\n(issue.summary/description)
    RemediationRequest ..> RemediationResponse : LLMProvider.generate_remediation()
    RemediationResponse "1" *-- "many" FileEdit
    RemediationResponse ..> PullRequestRef : GitHubClient.create_pull_request()
    PullRequestRef ..> NotificationMessage : RemediatePipeline\n(pr.url, pr.number)
```

Note what's conspicuously absent from this chain: there is no `SnowTicket` field that flows
directly into `RemediationRequest`. The link is entirely through Jira — `ingest` creates the Jira
issue and stops; `remediate` starts from the Jira issue and has no knowledge of the original SNOW
ticket beyond what made it into the issue's `summary`/`description`. This is intentional: the two
pipelines are independently runnable and independently testable (see
[Solution Strategy](02-solution-strategy.md)), and Jira is the single source of truth once a
finding has been triaged.

## 5.3 State machine — `remediation_runs.status`

```mermaid
stateDiagram-v2
    [*] --> NoRecord : no row for this jira_key
    NoRecord --> branch_created : clone_or_update + create_branch succeed
    branch_created --> pr_open : PR created successfully
    branch_created --> failed : exception anywhere before the PR is created
    failed --> branch_created : next cron tick retries from scratch
    pr_open --> pr_merged : not implemented in v1 — reserved for a future poller
    pr_open --> [*] : is_already_delivered() = True, future runs skip
    pr_merged --> [*] : is_already_delivered() = True, future runs skip

    note right of pr_open
        Once status="pr_open" is written, add_comment
        and notify() failures are caught locally and
        logged — they no longer overwrite this status
        back to "failed". This was a real bug, fixed
        after this diagram surfaced the inconsistency
        it would otherwise describe.
    end note

    note right of pr_merged
        No code path currently sets this. A PR being
        merged on GitHub is not detected by anything in
        v1 — is_already_delivered() checks for it only
        so that a future webhook or polling check can
        set it without any other code changing.
    end note
```

`is_already_delivered()` (`db/repository.py`) is the single idempotency gate `RemediatePipeline`
checks before doing any work — it returns `True` for `pr_open` or `pr_merged`, `False` for
everything else (including `NoRecord`, `branch_created`, and `failed`), which is exactly why a
`failed` run is retried on the next tick rather than stuck.
