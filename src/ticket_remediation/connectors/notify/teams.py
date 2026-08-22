import httpx

from .base import NotificationMessage


class TeamsNotifier:
    def __init__(self, webhook_url: str, timeout: float = 15.0):
        self._webhook_url = webhook_url
        self._timeout = timeout

    def notify(self, message: NotificationMessage) -> None:
        pr_line = f"\n\n[View PR]({message.pr_url})" if message.pr_url else ""
        payload = {
            "@type": "MessageCard",
            "@context": "http://schema.org/extensions",
            "summary": message.title,
            "title": message.title,
            "text": f"{message.body}{pr_line}",
        }
        response = httpx.post(self._webhook_url, json=payload, timeout=self._timeout)
        response.raise_for_status()
