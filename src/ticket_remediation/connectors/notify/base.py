from typing import Literal, Protocol

from pydantic import BaseModel


class NotificationMessage(BaseModel):
    title: str
    body: str
    pr_url: str | None = None
    jira_key: str | None = None
    level: Literal["success", "failure"] = "success"


class Notifier(Protocol):
    def notify(self, message: NotificationMessage) -> None: ...
