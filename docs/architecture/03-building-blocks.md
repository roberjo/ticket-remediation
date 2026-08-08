# 3. Building Block View

## 3.1 Level 2 — Containers

```mermaid
flowchart TB
    subgraph SYS["ticket-remediation"]
        direction LR
        IngestCLI["ingest CLI<br/>(typer, python -m ticket_remediation.ingest)"]
        RemediateCLI["remediate CLI<br/>(typer, python -m ticket_remediation.remediate)"]
        State[("SQLite<br/>data/state.db")]
        Config["Config files<br/>.env + config/*.yaml"]
        WorkDir["Scratch clones<br/>work/&lt;repo&gt;/"]
    end

    Mocks["Mock servers<br/>(dev-only)<br/>mock_servers/*"]

    IngestCLI --> State
    RemediateCLI --> State
    RemediateCLI --> WorkDir
    Config -.->|read at startup| IngestCLI
    Config -.->|read at startup| RemediateCLI
    Mocks -.->|stands in for<br/>ServiceNow + Jira<br/>in local dev| IngestCLI
    Mocks -.-> RemediateCLI

    style SYS fill:#1f6feb22,stroke:#1f6feb
    style Mocks fill:#8957e522,stroke:#8957e5
```

Both CLIs are independent OS processes with no shared runtime state beyond the SQLite file and
the YAML config — either can run without the other, and in production they're two separate cron
entries. `mock_servers/` is a development-only container: it's never imported by
`src/ticket_remediation/*` and has no presence in a real deployment.

## 3.2 Level 3 — Components (remediate pipeline)

```mermaid
flowchart TB
    CLI["__main__.py<br/>(typer entrypoint)"]
    Pipeline["RemediatePipeline<br/>(pipeline.py)"]
    Selector["repo_selector.py<br/>select_repo()"]
    CtxBuilder["context_builder.py<br/>build_file_tree() / make_file_reader()"]
    Runs["RemediationRunRepository<br/>(db/repository.py)"]

    JiraConn["JiraClient impl"]
    GitOps["git_ops.py<br/>(subprocess + git CLI)"]
    GhConn["GitHubClient impl"]
    LlmConn["LLMProvider impl"]
    NotifyConn["Notifier impl"]

    CLI --> Pipeline
    Pipeline --> Selector
    Pipeline --> CtxBuilder
    Pipeline --> Runs
    Pipeline --> JiraConn
    Pipeline --> GitOps
    Pipeline --> GhConn
    Pipeline --> LlmConn
    Pipeline --> NotifyConn
    CtxBuilder -.->|file_reader callback| LlmConn
```

`RemediatePipeline` is the only component that talks to every connector — it's the orchestrator,
not any individual connector. This mirrors `IngestPipeline`, which is the same shape one level
smaller (talks to `ServiceNowClient`, `JiraClient`, and `LinkRepository` only).

## 3.3 Module structure

```
src/ticket_remediation/
  logging_config.py           configure_logging()
  config/
    settings.py                 Settings (pydantic-settings, reads .env)
    mapping.py                  IngestMappingConfig / RepoRoutingConfig (+ YAML loaders)
  db/
    schema.sql                  CREATE TABLE IF NOT EXISTS x2
    connection.py                get_connection(path) -> sqlite3.Connection
    repository.py                LinkRepository, RemediationRunRepository
  connectors/
    servicenow/  base.py (Protocol) + rest.py (httpx impl)
    jira/        base.py (Protocol) + rest.py (httpx impl)
    github/      base.py (Protocol) + rest.py (PyGithub impl) + git_ops.py (local git, no Protocol)
    llm/         base.py (Protocol) + factory.py + limits.py + anthropic_provider.py + gemini_provider.py
    notify/      base.py (Protocol) + teams.py + slack.py + email_notifier.py + composite.py
  ingest/
    mapper.py                   SnowTicket -> JiraIssuePayload
    pipeline.py                  IngestPipeline
    __main__.py                   typer CLI
  remediate/
    repo_selector.py             JiraIssue -> RepoRouteTarget
    context_builder.py            file tree + bounded file_reader for the LLM
    pipeline.py                    RemediatePipeline
    __main__.py                     typer CLI

mock_servers/                  dev-only, never imported by src/
  common/state.py               RecordStore + /_debug/reset helper
  servicenow_mock/               vuln_catalog.py, generator.py, app.py (FastAPI)
  jira_mock/                      jql.py, app.py (FastAPI)
  run_all.py                      starts both mocks in one process
```

`git_ops.py` is deliberately **not** behind the `GitHubClient` Protocol — it's a set of plain
functions wrapping the `git` CLI via `subprocess`, kept separate from the PyGithub-backed remote
API client (`rest.py`) because they're genuinely different concerns (local filesystem git state
vs. remote GitHub API calls) with different failure modes and different testing strategies (argv
assertions + a real local-repo integration test, vs. mocked HTTP).

## 3.4 Connector interfaces (UML class diagrams)

Every connector follows the same shape: a `Protocol` (structural interface) plus one or more
concrete implementations, plus the pydantic models that cross the boundary.

### ServiceNow

```mermaid
classDiagram
    class ServiceNowClient {
        <<interface>>
        +fetch_tickets(table: str, since: datetime) list~SnowTicket~
    }
    class ServiceNowRestClient {
        +fetch_tickets(table, since) list~SnowTicket~
        +close()
    }
    class SnowTicket {
        +sys_id: str
        +number: str
        +short_description: str
        +description: str
        +severity: str
        +cvss_score: float
        +vuln_type: str
        +cwe_id: str
        +affected_component: str
        +affected_url_or_file: str
        +source_scanner: str
        +discovered_at: str
        +priority: str
    }
    ServiceNowClient <|.. ServiceNowRestClient : implements
    ServiceNowClient ..> SnowTicket : returns
```

Read-only by design (ADR in [Solution Strategy](02-solution-strategy.md)): idempotency is
tracked locally, not by writing back to ServiceNow.

### Jira

```mermaid
classDiagram
    class JiraClient {
        <<interface>>
        +create_issue(payload: JiraIssuePayload) JiraIssueRef
        +search_issues(jql: str) list~JiraIssue~
        +add_comment(key: str, body: str)
        +transition_issue(key: str, transition_name: str)
    }
    class JiraRestClient {
        +create_issue(payload) JiraIssueRef
        +search_issues(jql) list~JiraIssue~
        +add_comment(key, body)
        +transition_issue(key, transition_name)
        +close()
    }
    class JiraIssuePayload {
        +project_key: str
        +issue_type: str
        +summary: str
        +description: str
        +components: list~str~
        +labels: list~str~
    }
    class JiraIssueRef {
        +key: str
        +url: str
    }
    class JiraIssue {
        +key: str
        +project_key: str
        +summary: str
        +description: str
        +status: str
        +components: list~str~
        +labels: list~str~
    }
    JiraClient <|.. JiraRestClient : implements
    JiraClient ..> JiraIssuePayload : accepts
    JiraClient ..> JiraIssueRef : returns
    JiraClient ..> JiraIssue : returns
```

### GitHub

```mermaid
classDiagram
    class GitHubClient {
        <<interface>>
        +get_default_branch(repo_full_name: str) str
        +create_pull_request(repo_full_name, head, base, title, body) PullRequestRef
    }
    class GitHubRestClient {
        +get_default_branch(repo_full_name) str
        +create_pull_request(repo_full_name, head, base, title, body) PullRequestRef
    }
    class PullRequestRef {
        +number: int
        +url: str
    }
    GitHubClient <|.. GitHubRestClient : implements
    GitHubClient ..> PullRequestRef : returns

    class git_ops {
        <<module, not a Protocol>>
        +clone_or_update(repo_full_name, token, default_branch, work_dir) Path
        +create_branch(repo_path, branch_name, base_branch)
        +commit_all(repo_path, message)
        +push_branch(repo_path, branch_name)
    }
```

### LLM provider

```mermaid
classDiagram
    class LLMProvider {
        <<interface>>
        +generate_remediation(request: RemediationRequest, file_reader: FileReader) RemediationResponse
    }
    class AnthropicRemediationProvider {
        +generate_remediation(request, file_reader) RemediationResponse
    }
    class GeminiRemediationProvider {
        +generate_remediation(request, file_reader) RemediationResponse
    }
    class RemediationRequest {
        +jira_key: str
        +summary: str
        +description: str
        +acceptance_criteria: str?
        +file_tree: list~str~
    }
    class FileEdit {
        +path: str
        +action: "create"|"modify"|"delete"
        +content: str?
    }
    class RemediationResponse {
        +summary: str
        +commit_message: str
        +edits: list~FileEdit~
    }
    LLMProvider <|.. AnthropicRemediationProvider : implements
    LLMProvider <|.. GeminiRemediationProvider : implements
    LLMProvider ..> RemediationRequest : accepts
    LLMProvider ..> RemediationResponse : returns
    RemediationResponse *-- FileEdit
```

`FileReader` (referenced by the interface) is `Callable[[str], str]`, not a class — a plain
bounded callback built per-run by `context_builder.make_file_reader()`, so it isn't part of the
class hierarchy above. See [Runtime View](04-runtime-view.md) for how it's actually used inside
the provider's read loop.

### Notify

```mermaid
classDiagram
    class Notifier {
        <<interface>>
        +notify(message: NotificationMessage)
    }
    class TeamsNotifier {
        +notify(message)
    }
    class SlackNotifier {
        +notify(message)
    }
    class EmailNotifier {
        +notify(message)
    }
    class CompositeNotifier {
        -_notifiers: list~Notifier~
        +notify(message)
    }
    class NotificationMessage {
        +title: str
        +body: str
        +pr_url: str
        +jira_key: str
    }
    Notifier <|.. TeamsNotifier : implements
    Notifier <|.. SlackNotifier : implements
    Notifier <|.. EmailNotifier : implements
    Notifier <|.. CompositeNotifier : implements
    CompositeNotifier o-- Notifier : fans out to
    Notifier ..> NotificationMessage : accepts
```

`CompositeNotifier` both *implements* `Notifier` (so callers don't need to know how many channels
are configured) and *composes* a list of other `Notifier`s — a fan-out that only includes the
channels with a configured endpoint (`build_notifier()` in `composite.py`), and logs rather than
raises if one channel fails, so one bad webhook can't block the others.
