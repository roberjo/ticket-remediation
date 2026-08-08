import httpx

from .base import NotificationMessage


class SlackNotifier:
    def __init__(self, webhook_url: str, timeout: float = 15.0):
        self._webhook_url = webhook_url
        self._timeout = timeout

    def notify(self, message: NotificationMessage) -> None:
        payload = {"text": f"*{message.title}*\n{message.body}\n<{message.pr_url}|View PR>"}
        response = httpx.post(self._webhook_url, json=payload, timeout=self._timeout)
        response.raise_for_status()
