# 4. Runtime View

## 4.1 Ingest: SNOW ticket → Jira issue

```mermaid
sequenceDiagram
    actor Cron
    participant CLI as ingest __main__
    participant Pipe as IngestPipeline
    participant SNOW as ServiceNowClient
    participant LinkRepo as LinkRepository
    participant Mapper as mapper.to_jira_payload
    participant Jira as JiraClient

    Cron->>CLI: python -m ticket_remediation.ingest run
    CLI->>Pipe: run(dry_run)
    loop for each rule in ingest_mapping.yaml
        Pipe->>SNOW: fetch_tickets(rule.snow_table)
        SNOW-->>Pipe: list[SnowTicket]
        loop for each ticket
            Pipe->>LinkRepo: get_jira_key(table, sys_id)
            alt already linked
                LinkRepo-->>Pipe: existing jira_key
                Pipe->>Pipe: skipped += 1
            else new ticket
                LinkRepo-->>Pipe: None
                Pipe->>Mapper: to_jira_payload(ticket, rule)
                Mapper-->>Pipe: JiraIssuePayload
                Pipe->>Jira: create_issue(payload)
                alt Jira create fails
                    Jira--xPipe: raises
                    Pipe->>Pipe: failed.append(ticket.number)
                else success
                    Jira-->>Pipe: JiraIssueRef(key, url)
                    Pipe->>LinkRepo: record_link(table, sys_id, number, key)
                    Pipe->>Pipe: created.append(key)
                end
            end
        end
    end
    Pipe-->>CLI: IngestResult(created, skipped, failed)
    CLI-->>Cron: exit 0, or exit 1 if any failed
```

The per-ticket link check is what makes re-running safe: a second run against the same SNOW data
produces `skipped` for every ticket that was already turned into a Jira issue, and creates
nothing new.

## 4.2 Remediate: happy path (Jira issue → PR)

```mermaid
sequenceDiagram
    actor Cron
    participant CLI as remediate __main__
    participant Pipe as RemediatePipeline
    participant Jira as JiraClient
    participant Runs as RemediationRunRepository
    participant Sel as repo_selector
    participant Git as git_ops
    participant Ctx as context_builder
    participant LLM as LLMProvider
    participant GH as GitHubClient
    participant Notify as Notifier

    Cron->>CLI: python -m ticket_remediation.remediate run
    CLI->>Pipe: run(jql_status, project_key)
    Pipe->>Jira: search_issues(jql)
    Jira-->>Pipe: list[JiraIssue]

    loop for each issue
        Pipe->>Runs: is_already_delivered(issue.key)
        Runs-->>Pipe: False
        Pipe->>Sel: select_repo(issue, routing)
        Sel-->>Pipe: RepoRouteTarget

        Pipe->>Git: clone_or_update(repo, token, default_branch, work_dir)
        Git-->>Pipe: repo_path
        Pipe->>Git: create_branch(repo_path, branch, default_branch)
        Pipe->>Runs: upsert_run(key, status="branch_created")

        Pipe->>Ctx: build_file_tree(repo_path)
        Ctx-->>Pipe: file_tree
        Pipe->>Ctx: make_file_reader(repo_path)
        Ctx-->>Pipe: file_reader callback

        Pipe->>LLM: generate_remediation(request, file_reader)
        activate LLM
        loop model's own tool-use turns (see 4.3)
            LLM->>Ctx: file_reader(path) [via callback, bounded]
            Ctx-->>LLM: file contents
        end
        LLM-->>Pipe: RemediationResponse(edits, commit_message)
        deactivate LLM

        Pipe->>Pipe: _apply_edits() — path-escape guard, write files
        Pipe->>Git: commit_all(repo_path, message)
        Pipe->>Git: push_branch(repo_path, branch)

        Pipe->>GH: create_pull_request(repo, head, base, title, body)
        GH-->>Pipe: PullRequestRef(number, url)
        Pipe->>Runs: upsert_run(key, status="pr_open", pr_url)
        Pipe->>Jira: add_comment(key, "PR opened: <url>")
        Pipe->>Notify: notify(NotificationMessage)
        Notify--)Notify: fan out to Teams/Slack/Email (4.4)

        Pipe->>Pipe: opened_prs.append(issue.key)
    end
    Pipe-->>CLI: RemediateResult
    CLI-->>Cron: exit 0, or exit 1 if any failed
```

## 4.3 LLM provider's internal tool-use loop

The step drawn as one box above ("generate_remediation") is itself a multi-turn loop — shown here
for the Anthropic provider; the Gemini provider is the same shape using its `interactions` API
(`previous_interaction_id` instead of a resent message list).

```mermaid
sequenceDiagram
    participant Pipe as RemediatePipeline
    participant Prov as AnthropicRemediationProvider
    participant API as Anthropic API
    participant Reader as file_reader (bounded)

    Pipe->>Prov: generate_remediation(request, file_reader)
    Prov->>API: messages.create(system, tools=[read_file, submit_remediation], messages)
    API-->>Prov: tool_use: read_file(path)
    Prov->>Reader: file_reader(path)
    alt path escapes repo, or read cap (MAX_FILE_READS) exceeded
        Reader--xProv: raises / returns "Error: ..." text
    else ok
        Reader-->>Prov: file contents (truncated to MAX_FILE_BYTES)
    end
    Prov->>API: messages.create(... tool_result appended to messages)
    Note over Prov,API: repeats for as many read_file calls<br/>as the model makes, up to the cap
    API-->>Prov: tool_use: submit_remediation(summary, commit_message, edits)
    Prov-->>Pipe: RemediationResponse
```

A read past `MAX_FILE_READS` doesn't raise back to the pipeline — it's fed to the model as an
error string ("max file-read limit reached, submit now"), nudging it to finish rather than
crashing the run. If the model ends its turn without ever calling `submit_remediation`, *that*
does raise (`ValueError`), which the pipeline catches and records as `status="failed"`.

## 4.4 Notification fan-out

```mermaid
sequenceDiagram
    participant Pipe as RemediatePipeline
    participant Comp as CompositeNotifier
    participant Teams as TeamsNotifier
    participant Slack as SlackNotifier
    participant Email as EmailNotifier

    Pipe->>Comp: notify(message)
    Note over Comp: only channels with a configured<br/>endpoint were included at construction
    Comp->>Teams: notify(message)
    alt Teams webhook fails
        Teams--xComp: raises
        Comp->>Comp: log exception, continue
    end
    Comp->>Slack: notify(message)
    Comp->>Email: notify(message)
    Note over Comp: one channel's failure never<br/>suppresses the others
```

## 4.5 Idempotent skip and failure paths

```mermaid
sequenceDiagram
    actor Cron
    participant Pipe as RemediatePipeline
    participant Runs as RemediationRunRepository

    Cron->>Pipe: run(...) [second invocation, same issue]
    Pipe->>Runs: is_already_delivered(issue.key)
    Runs-->>Pipe: True (status in pr_open, pr_merged)
    Pipe->>Pipe: skipped += 1
    Note over Pipe: no clone, no LLM call, no PR — cheap and safe to re-run
```

```mermaid
sequenceDiagram
    participant Pipe as RemediatePipeline
    participant Runs as RemediationRunRepository

    Note over Pipe: any exception during _remediate_one<br/>(clone, LLM call, apply, push, PR create...)
    Pipe->>Runs: upsert_run(key, status="failed", error_message=str(exc))
    Pipe->>Pipe: failed.append(issue.key), continue to next issue
    Note over Pipe: no retry/backoff framework by design (ADR, see Risks) —<br/>the next scheduled cron tick retries naturally
```
