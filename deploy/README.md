# Deployment examples

Worked examples for the "any host that can run cron + Python" deployment described in
[`docs/architecture/07-deployment-view.md`](../docs/architecture/07-deployment-view.md). None of
these are required — pick whichever matches how you already run scheduled jobs.

## Option 1: bare checkout + cron

```bash
git clone https://github.com/roberjo/ticket-remediation.git /opt/ticket-remediation
cd /opt/ticket-remediation
uv sync --group dev          # not --extra mocks — the mock servers aren't needed here
cp .env.example .env         # fill in real credentials
```

Then install [`crontab.example`](crontab.example) (adjust `APP_DIR`/`LOG_DIR` first).

## Option 2: bare checkout + systemd timers

Same setup as above, then:

```bash
sudo useradd --system --home /opt/ticket-remediation ticket-remediation
sudo chown -R ticket-remediation:ticket-remediation /opt/ticket-remediation
sudo cp deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now \
    ticket-remediation-ingest.timer \
    ticket-remediation-remediate.timer \
    ticket-remediation-sync-pr-status.timer
```

Check a run with `systemctl status ticket-remediation-remediate.service` and
`journalctl -u ticket-remediation-remediate.service`.

## Option 3: Docker

Build once with the root [`Dockerfile`](../Dockerfile):

```bash
docker build -t ticket-remediation .
```

Each pipeline is a separate `docker run` — the image has no default long-running process, only a
default `CMD` (`remediate run`) you override per invocation:

```bash
docker run --rm --env-file .env \
    -v ticket-remediation-data:/app/data \
    -v ticket-remediation-work:/app/work \
    ticket-remediation ticket_remediation.ingest run

docker run --rm --env-file .env \
    -v ticket-remediation-data:/app/data \
    -v ticket-remediation-work:/app/work \
    ticket-remediation ticket_remediation.remediate run

docker run --rm --env-file .env \
    -v ticket-remediation-data:/app/data \
    ticket-remediation ticket_remediation.remediate sync-pr-status
```

`--env-file .env` works directly — pydantic-settings reads process environment variables
regardless of whether the `.env` file itself is present inside the container, so there's no need
to bake credentials into the image or mount the file. The two named volumes matter for the same
reason described in the Deployment View: `data/state.db` is the idempotency guarantee, and
`work/<repo>/` is reused across runs — losing either isn't catastrophic, but a fresh volume means
a fresh idempotency history and a fresh clone.

Wire the same three `docker run` lines into host cron (in place of the `uv run python -m ...`
lines in [`crontab.example`](crontab.example)), or into systemd services with
`ExecStart=/usr/bin/docker run ...` instead of the venv path.
