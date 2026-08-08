# 8. Cross-Cutting Concerns, Risks & Glossary

## Security

- **The only approval gate is GitHub PR review** ([ADR-10](02-solution-strategy.md#adr-10-github-pr-review-is-the-only-approval-gate)).
  No path in this system pushes directly to a protected branch or auto-merges anything.
- **LLM output is treated as untrusted input where it touches the filesystem.** File paths in
  both the read loop (`context_builder.make_file_reader`) and the apply step
  (`RemediatePipeline._apply_edits`) are resolved and checked against the repo's working
  directory before any read or write; anything that would escape it is rejected. This matters
  specifically because those paths originate from a model response, not from the pipeline's own
  logic.
- **Credentials live only in `.env`**, which is git-ignored (`.env` and `.env.*`, with only the
  `.example` templates explicitly un-ignored — see the repo's `.gitignore`). Nothing in source
  control has ever contained a real credential (verified by scanning tracked files and git
  history before either repo went public).
- **If a credential is ever exposed**, rotating it at the source (GitHub token settings, the
  Jira/ServiceNow admin console, the LLM provider's console) is required — removing it from a
  later commit does not remove it from git history.
- **The demo target repo is intentionally vulnerable.** `vulnerable-react-demo-app` exists to
  give the LLM real flaws to fix; its patterns (public S3 bucket, wildcard IAM policy,
  `dangerouslySetInnerHTML`, etc.) are documented in its own README specifically as anti-patterns,
  not reference implementations, and its Terraform is never `apply`'d — only read and edited.
- **No dependency-vulnerability scanning is configured yet** (Dependabot, `pip-audit`, or
  equivalent) — see [Risks](#risks--known-limitations).

## Testing strategy

Three tiers, from fastest/most-isolated to slowest/most-realistic:

1. **Connector unit tests** — each REST client tested with `respx`-mocked HTTP against fixture
   JSON (`tests/unit/connectors/test_*_rest.py`); `git_ops.py` tested both via mocked-`subprocess`
   argv assertions *and* a real local-bare-repo integration test (the mocked version alone missed
   a real path-construction bug — see [Risks](#risks--known-limitations)); LLM providers tested
   against mocked SDK clients scripting a tool-use sequence.
2. **Pipeline orchestration tests** (highest value) — `IngestPipeline`/`RemediatePipeline` tested
   against hand-written fakes satisfying each `Protocol`, not mocks. These assert the properties
   that actually matter: a second run creates nothing new, one item's failure doesn't block the
   rest, and an already-delivered issue is skipped without touching git or the LLM.
3. **Live end-to-end verification** — periodically run for real against the local mocks (SNOW,
   Jira) plus real GitHub and a real free-tier LLM, proving the full ingest → Jira → LLM →
   branch → PR → notify chain actually works, not just that each piece is individually correct.
   This is how three real bugs were found (see below) that no unit test caught.

The default `pytest` run hits no network and needs no credentials — see
[Deployment View](07-deployment-view.md) for how the live-verification tier is run.

## Error-handling philosophy

**Fail loudly, log, mark the run `failed`, let the next scheduled tick retry.** There is
deliberately no retry/backoff framework, no circuit breaker, no dead-letter queue — see
[Risks](#risks--known-limitations) for the trade-off. The one refinement this project's own live
testing forced: a failure *after* the PR already exists (Jira comment, notification) must not be
treated the same as a failure *before* it — see the state-machine notes in
[Data & State Model](05-data-and-state-model.md#53-state-machine--remediation_runsstatus) for why
conflating the two broke idempotency in practice, not just in theory.

## Bugs found via live testing (and what they taught the design)

Three real defects were found only by actually running the system end-to-end against real
GitHub and a real LLM — none were caught by the mocked-subprocess or fixture-based unit tests
that existed at the time:

| Bug | Root cause | What it changed |
|---|---|---|
| Fresh clone landed at `work/work/<repo>` | `clone_or_update` passed a `work_dir`-prefixed destination path while also `cwd`-ing into `work_dir` | Added a real local-bare-repo regression test for `clone_or_update` itself, not just a hand-rolled clone that bypassed it |
| `create_branch` crashed if the branch already existed | Used `git checkout -b` (fails on an existing branch) instead of `-B` (create-or-reset) | Switched to `-B`; added a test that calls `create_branch` twice for the same name |
| A successful `pr_open` status could be silently overwritten to `failed` | `add_comment`/`notify` failures, happening *after* the PR was created, were caught by the same outer `except` that also handles pre-PR failures | Comment/notify failures are now caught and logged individually, never undoing a real `pr_open` |

This is the practical argument for the live-verification testing tier above: structural
correctness (types, Protocols, mocked argv) doesn't catch "the path resolves to the wrong place"
or "success got reclassified as failure by an unrelated later step" — only running the real thing
does.

## Risks & known limitations

Explicitly out of scope for the current version, listed here as risks rather than silently
omitted:

| Risk / limitation | Why it's accepted for now |
|---|---|
| **Single-writer SQLite** doesn't support multiple concurrent pipeline instances against the same `data/state.db` | v1 has one scheduled instance of each pipeline; horizontal scaling was never a goal |
| **No PR-merge detection** — `remediation_runs.status` never reaches `pr_merged` in practice | The state model reserves the value, but nothing polls GitHub or receives a webhook to set it; a merged PR is simply left `pr_open` forever, which is harmless (still correctly treated as "already delivered") but not fully accurate |
| **No retry/backoff framework** | A failed run is retried wholesale on the next cron tick; there's no exponential backoff or max-attempt cap, so a persistently-broken route (e.g. a missing repo-routing rule) will fail identically on every tick until fixed |
| **No dependency-vulnerability scanning** on this project's own dependencies | Not yet configured; worth adding (Dependabot / `pip-audit`) before running against production systems |
| **No webhook trigger** | Findings/issues are only picked up on the next poll, not instantly — an explicit trade for zero-infrastructure local development (ADR-2) |
| **No human-approval gate on LLM output** | Explicit product decision, not an oversight — PR review is the gate (ADR-10) |
| **No multi-tenant configuration** | One `.env`, one set of routing rules, per deployment |

## Glossary

| Term | Meaning |
|---|---|
| **AVIT** | Application-Vulnerability finding sourced from ServiceNow — this project's org-specific term for the SNOW ticket type that `ingest` consumes |
| **AVREM** | "Application Vulnerability Remediation" — the Jira project/board `remediate` polls |
| **SNOW** | Shorthand for ServiceNow |
| **CWE** | Common Weakness Enumeration — the vulnerability-class identifier attached to each finding (e.g. `CWE-79` for XSS) |
| **CVSS** | Common Vulnerability Scoring System — the 0–10 severity score attached to each finding |
| **JQL** | Jira Query Language — used by `remediate` to search for issues in a given status |
| **Protocol** | Python's structural-typing interface (`typing.Protocol`) — this project's mechanism for defining a connector's contract without inheritance |
| **Idempotency** | The property that re-running a pipeline produces no duplicate side effects — enforced here via the SQLite link/run tables |
| **`infra-config`** | The Jira component denoting Terraform/cloud-infrastructure findings, as opposed to `frontend`/`backend-api`/`auth` for application code |
| **Demo-relevant** | A tag on a mock ServiceNow catalog entry (`vuln_catalog.py`) meaning it corresponds to a vulnerability actually seeded in the demo target repo, so it can be exercised end-to-end |
