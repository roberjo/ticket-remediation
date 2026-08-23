"""Fixtures that spin up the real mock_servers FastAPI apps in-process (real HTTP,
real uvicorn, ephemeral port) so contract tests exercise the REST connectors against
the actual API shape the mocks expose — not a respx-mocked stand-in.

Requires the `mocks` extra (`uv sync --extra mocks --group dev`); skipped cleanly if
uvicorn/fastapi aren't installed, so the default `pytest` run never depends on them.
"""

import socket
import threading
import time
from collections.abc import Iterator

import httpx
import pytest

uvicorn = pytest.importorskip("uvicorn")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(app: object, port: int) -> "uvicorn.Server":
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started:
        if time.monotonic() > deadline:
            raise RuntimeError("mock server did not start within 10s")
        time.sleep(0.01)
    return server


@pytest.fixture(scope="session")
def servicenow_mock_url() -> Iterator[str]:
    from mock_servers.servicenow_mock.app import app

    port = _free_port()
    server = _start_server(app, port)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture(scope="session")
def jira_mock_url() -> Iterator[str]:
    from mock_servers.jira_mock.app import app

    port = _free_port()
    server = _start_server(app, port)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True


@pytest.fixture
def reset_servicenow_mock(servicenow_mock_url: str) -> None:
    httpx.post(f"{servicenow_mock_url}/_debug/reset").raise_for_status()


@pytest.fixture
def reset_jira_mock(jira_mock_url: str) -> None:
    httpx.post(f"{jira_mock_url}/_debug/reset").raise_for_status()
