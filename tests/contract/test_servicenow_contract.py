"""Contract tests: ServiceNowRestClient against the real servicenow_mock FastAPI app,
started in-process and hit over real HTTP (see conftest.py). These exist to catch
"the request/response shape doesn't actually match" bugs that a respx-mocked fixture
(tests/unit/connectors/test_servicenow_rest.py) can't — respx only ever confirms the
client matches the shape *we* wrote into the fixture, not the shape the server sends.
"""

from datetime import datetime

import httpx
import pytest

from ticket_remediation.connectors.servicenow.rest import ServiceNowRestClient

pytestmark = pytest.mark.contract


@pytest.fixture
def client(servicenow_mock_url):
    c = ServiceNowRestClient(servicenow_mock_url, "fake-token")
    yield c
    c.close()


def test_fetch_tickets_returns_generated_findings_shaped_as_snow_tickets(client, reset_servicenow_mock):
    tickets = client.fetch_tickets("x_avit_findings")

    assert len(tickets) == 8
    assert all(t.number.startswith("AVIT") for t in tickets)
    assert all(t.severity in {"Critical", "High", "Medium", "Low"} for t in tickets)
    assert all(t.affected_component for t in tickets)


def test_fetch_tickets_since_only_returns_rows_at_or_after_the_cutoff(
    servicenow_mock_url, client, reset_servicenow_mock
):
    httpx.post(
        f"{servicenow_mock_url}/_debug/seed",
        params={"table": "x_avit_findings", "count": 10, "seed": 7},
    ).raise_for_status()

    unfiltered = client.fetch_tickets("x_avit_findings")
    discovered_values = sorted(t.discovered_at for t in unfiltered)
    cutoff = datetime.fromisoformat(discovered_values[len(discovered_values) // 2])

    filtered = client.fetch_tickets("x_avit_findings", since=cutoff)

    assert filtered
    assert len(filtered) <= len(unfiltered)
    assert all(t.discovered_at >= cutoff.isoformat() for t in filtered)
