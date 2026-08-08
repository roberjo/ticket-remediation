from datetime import datetime

import httpx

from .base import SnowTicket


class ServiceNowRestClient:
    """httpx-based client against the ServiceNow Table API
    (https://developer.servicenow.com/dev.do#!/reference/api/.../rest/c_TableAPI).
    """

    def __init__(self, instance_url: str, api_token: str, timeout: float = 30.0):
        self._base_url = instance_url.rstrip("/")
        self._client = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_token}", "Accept": "application/json"},
            timeout=timeout,
        )

    def fetch_tickets(self, table: str, since: datetime | None = None) -> list[SnowTicket]:
        params: dict[str, str] = {}
        if since is not None:
            params["sysparm_query"] = f"discovered_at>={since.isoformat()}"
        response = self._client.get(f"/api/now/table/{table}", params=params)
        response.raise_for_status()
        rows = response.json()["result"]
        return [SnowTicket.model_validate(row) for row in rows]

    def close(self) -> None:
        self._client.close()
