from datetime import datetime
from typing import Protocol

from pydantic import BaseModel


class SnowTicket(BaseModel):
    sys_id: str
    number: str
    short_description: str
    description: str
    severity: str
    cvss_score: float
    vuln_type: str
    cwe_id: str
    affected_component: str
    affected_url_or_file: str
    source_scanner: str
    discovered_at: str
    priority: str


class ServiceNowClient(Protocol):
    def fetch_tickets(self, table: str, since: datetime | None = None) -> list[SnowTicket]: ...
