# Production image for `ingest run` / `remediate run` / `remediate sync-pr-status` — the same
# CLIs described in docs/architecture/07-deployment-view.md, just packaged instead of run from a
# checkout. Not used by local dev (uv run ... against the mock servers) or CI (see
# .github/workflows/ci.yml) — those don't need a container.

FROM python:3.12-slim AS base

# git is a runtime dependency, not a build one: connectors/github/git_ops.py shells out to the
# real `git` binary for clone/branch/commit/push (see ADR — git_ops.py resolves it to an
# absolute path at import time; this is what that path resolves to inside the image).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.5 /uv /uvx /bin/

WORKDIR /app

# Dependencies first, in their own layer, so an app-code change doesn't invalidate the
# (comparatively slow) dependency-install layer on every rebuild.
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-install-project

COPY src/ src/
COPY mock_servers/ mock_servers/
COPY config/ config/
COPY README.md ./
RUN uv sync --locked

ENV PATH="/app/.venv/bin:${PATH}"

# data/state.db and work/<repo> must outlive a single invocation — see Deployment View
# (docs/architecture/07-deployment-view.md) for why. Mount both as volumes at `docker run`;
# these mkdirs just give the mount points sane default ownership/permissions if you don't.
RUN mkdir -p /app/data /app/work

# No ENTRYPOINT default command: `ingest` and `remediate` are two independent CLIs, and which
# one a given container invocation runs (plus its subcommand — run / status / sync-pr-status /
# ...) is the caller's decision, not this image's. See deploy/ for worked examples.
ENTRYPOINT ["python", "-m"]
CMD ["ticket_remediation.remediate", "run"]
