import smtplib
from email.message import EmailMessage

from .base import NotificationMessage


class EmailNotifier:
    def __init__(
        self,
        smtp_host: str,
        smtp_port: int,
        smtp_user: str,
        smtp_password: str,
        from_addr: str,
        to_addr: str,
        timeout: float = 15.0,
    ):
        self._smtp_host = smtp_host
        self._smtp_port = smtp_port
        self._smtp_user = smtp_user
        self._smtp_password = smtp_password
        self._from_addr = from_addr
        self._to_addr = to_addr
        self._timeout = timeout

    def notify(self, message: NotificationMessage) -> None:
        msg = EmailMessage()
        msg["Subject"] = message.title
        msg["From"] = self._from_addr
        msg["To"] = self._to_addr
        msg.set_content(f"{message.body}\n\nPR: {message.pr_url}")

        with smtplib.SMTP(self._smtp_host, self._smtp_port, timeout=self._timeout) as smtp:
            smtp.starttls()
            if self._smtp_user:
                smtp.login(self._smtp_user, self._smtp_password)
            smtp.send_message(msg)
