"""One-command local startup for both mock servers:

    uv run python -m mock_servers.run_all

ServiceNow mock on :8001, Jira mock on :8002 — matches .env.mock.example.
"""

import threading

import uvicorn

from mock_servers.jira_mock.app import app as jira_app
from mock_servers.servicenow_mock.app import app as servicenow_app


def _serve(app, port: int) -> None:
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="info")


def main() -> None:
    snow_thread = threading.Thread(target=_serve, args=(servicenow_app, 8001), daemon=True)
    snow_thread.start()
    print("ServiceNow AVIT mock running at http://127.0.0.1:8001")
    print("Jira AVREM mock running at http://127.0.0.1:8002")
    _serve(jira_app, 8002)


if __name__ == "__main__":
    main()
