import json
from unittest.mock import MagicMock, patch

import httpx
import respx

from ticket_remediation.connectors.notify.base import NotificationMessage
from ticket_remediation.connectors.notify.composite import CompositeNotifier
from ticket_remediation.connectors.notify.email_notifier import EmailNotifier
from ticket_remediation.connectors.notify.slack import SlackNotifier
from ticket_remediation.connectors.notify.teams import TeamsNotifier


def _message() -> NotificationMessage:
    return NotificationMessage(
        title="Remediation PR opened for AVREM-1",
        body="Reflected XSS in /search",
        pr_url="https://github.com/org/repo/pull/1",
        jira_key="AVREM-1",
    )


@respx.mock
def test_teams_notifier_posts_message_card():
    route = respx.post("https://teams.example.com/webhook").mock(return_value=httpx.Response(200))

    TeamsNotifier("https://teams.example.com/webhook").notify(_message())

    body = json.loads(route.calls[0].request.content)
    assert body["title"] == "Remediation PR opened for AVREM-1"
    assert "https://github.com/org/repo/pull/1" in body["text"]


@respx.mock
def test_slack_notifier_posts_text_payload():
    route = respx.post("https://hooks.slack.com/services/x").mock(return_value=httpx.Response(200))

    SlackNotifier("https://hooks.slack.com/services/x").notify(_message())

    body = json.loads(route.calls[0].request.content)
    assert "Remediation PR opened for AVREM-1" in body["text"]
    assert "https://github.com/org/repo/pull/1" in body["text"]


@patch("ticket_remediation.connectors.notify.email_notifier.smtplib.SMTP")
def test_email_notifier_sends_expected_message(mock_smtp_cls):
    mock_smtp = MagicMock()
    mock_smtp_cls.return_value.__enter__.return_value = mock_smtp

    EmailNotifier(
        smtp_host="smtp.example.com",
        smtp_port=587,
        smtp_user="user",
        smtp_password="pass",
        from_addr="bot@example.com",
        to_addr="team@example.com",
    ).notify(_message())

    mock_smtp.login.assert_called_once_with("user", "pass")
    sent_msg = mock_smtp.send_message.call_args.args[0]
    assert sent_msg["To"] == "team@example.com"
    assert sent_msg["Subject"] == "Remediation PR opened for AVREM-1"


def test_composite_notifier_continues_after_one_channel_fails():
    class FailingNotifier:
        def notify(self, message):
            raise RuntimeError("channel down")

    class RecordingNotifier:
        def __init__(self):
            self.received = []

        def notify(self, message):
            self.received.append(message)

    recorder = RecordingNotifier()
    CompositeNotifier([FailingNotifier(), recorder]).notify(_message())

    assert len(recorder.received) == 1
