import json

import httpx
import pytest
import respx

from ticket_remediation.connectors.servicenow.rest import ServiceNowRestClient


@respx.mock
def test_fetch_tickets_parses_result_rows(fixtures_dir):
    payload = json.loads((fixtures_dir / "snow_incident_sample.json").read_text())
    route = respx.get("http://snow.example.com/api/now/table/x_avit_findings").mock(
        return_value=httpx.Response(200, json=payload)
    )

    client = ServiceNowRestClient("http://snow.example.com", "fake-token")
    tickets = client.fetch_tickets("x_avit_findings")

    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer fake-token"
    assert len(tickets) == 1
    assert tickets[0].number == "AVIT0000001"
    assert tickets[0].affected_component == "frontend"


@respx.mock
def test_fetch_tickets_raises_on_http_error():
    respx.get("http://snow.example.com/api/now/table/x_avit_findings").mock(return_value=httpx.Response(500))

    client = ServiceNowRestClient("http://snow.example.com", "fake-token")
    with pytest.raises(httpx.HTTPStatusError):
        client.fetch_tickets("x_avit_findings")
