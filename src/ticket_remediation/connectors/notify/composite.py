import logging

from ticket_remediation.config.settings import Settings

from .base import NotificationMessage, Notifier
from .email_notifier import EmailNotifier
from .slack import SlackNotifier
from .teams import TeamsNotifier

logger = logging.getLogger(__name__)


class CompositeNotifier:
    """Fans a notification out to every configured channel. One channel's failure
    is logged but never suppresses the others."""

    def __init__(self, notifiers: list[Notifier]):
        self._notifiers = notifiers

    def notify(self, message: NotificationMessage) -> None:
        for notifier in self._notifiers:
            try:
                notifier.notify(message)
            except Exception:
                logger.exception("Notifier %s failed", type(notifier).__name__)


def build_notifier(settings: Settings) -> CompositeNotifier:
    """Only the channels with a configured endpoint are included."""
    notifiers: list[Notifier] = []
    if settings.teams_webhook_url:
        notifiers.append(TeamsNotifier(settings.teams_webhook_url))
    if settings.slack_webhook_url:
        notifiers.append(SlackNotifier(settings.slack_webhook_url))
    if settings.smtp_host and settings.notify_email_to:
        notifiers.append(
            EmailNotifier(
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_user=settings.smtp_user,
                smtp_password=settings.smtp_password,
                from_addr=settings.smtp_from_addr,
                to_addr=settings.notify_email_to,
            )
        )
    return CompositeNotifier(notifiers)
