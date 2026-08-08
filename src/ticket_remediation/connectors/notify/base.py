from typing import Protocol

from pydantic import BaseModel


class NotificationMessage(BaseModel):
    title: str
    body: str
    pr_url: str
    jira_key: str


class Notifier(Protocol):
    def notify(self, message: NotificationMessage) -> None: ...
