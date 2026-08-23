# Contributing

This is currently a personal/portfolio project without a formal governance process, but issues
and PRs are welcome. This document is the process the README's "run the checks before submitting"
line was pointing at.

## Setup

```bash
git clone https://github.com/roberjo/ticket-remediation.git
cd ticket-remediation
uv sync --extra mocks --group dev
uv run pre-commit install   # optional but recommended — scans staged changes for secrets
```

See the README's [Quickstart](README.md#quickstart-zero-budget--local-mock-mode) for running the
pipelines themselves against the local mocks.

## Before opening a PR

```bash
uv run ruff check .
uv run mypy src
uv run pytest                    # fast, no network
uv run pytest -m contract        # spins up the mock servers, hits them over real HTTP
uv run pytest --cov=ticket_remediation --cov-report=term-missing   # optional, CI checks this too
```

All of the above run in CI ([`.github/workflows/ci.yml`](.github/workflows/ci.yml)) on every push
and PR; running them locally first just means you find out sooner.

## Conventions this codebase already follows

- **Connectors are `typing.Protocol`s**, not base classes — see
  [ADR-1](docs/architecture/02-solution-strategy.md#adr-1-connectors-are-typingprotocols-not-base-classes).
  A new connector implementation needs no inheritance, just structural compatibility.
- **Pipeline tests use hand-written fakes**, not mocks — see
  `tests/unit/ingest/test_ingest_pipeline.py` or `tests/unit/remediate/test_remediate_pipeline.py`
  for the pattern before adding a new one.
- **Mapping/routing rules are YAML, not code** — broadening scope (a new source table, a new
  target repo, a new component) is usually a `config/*.yaml` edit, not a Python change.
- **Comments explain *why*, not *what*.** Well-named code speaks for itself; a comment earns its
  place only when it captures a non-obvious constraint or a bug a reader would otherwise repeat.
- Significant design decisions get an ADR entry in
  [`docs/architecture/02-solution-strategy.md`](docs/architecture/02-solution-strategy.md) —
  decision / context / consequence, so a future reader can judge whether the reasoning still
  holds before changing it.

## Reporting a bug or requesting a feature

Use the issue templates — they ask for the specific details that make a report actionable
(repro steps, which pipeline, expected vs. actual). Security issues: see
[Security](README.md#security) in the README rather than opening a public issue.

## Commit messages

Explain *why* a change was made, not just what changed — the diff already shows the what.
