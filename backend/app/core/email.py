"""
EmailSender interface and implementations (D-17).

Provider-agnostic interface so we can swap from Mailpit → SES/SendGrid later
purely via EMAIL_PROVIDER env var.

Dev:     SMTP to Mailpit container (smtp_host=mailpit, smtp_port=1025)
Console: Logs the email body — useful when docker-compose is not running
Test:    InMemoryEmailSender — captured for test assertions
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Protocol

import structlog

from app.core.config import AppEnv, get_settings

logger = structlog.get_logger(__name__)
settings = get_settings()


class EmailSender(Protocol):
    async def send(
        self,
        to: str,
        subject: str,
        html_body: str,
        text_body: str,
    ) -> None: ...


class SmtpEmailSender:
    """Sends via SMTP — works with Mailpit in dev and real providers in prod."""

    async def send(self, to: str, subject: str, html_body: str, text_body: str) -> None:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{settings.email_from_name} <{settings.email_from_address}>"
        msg["To"] = to
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=5) as server:
                server.sendmail(settings.email_from_address, [to], msg.as_string())
            logger.info("email_sent", to_masked=to[:3] + "***", subject=subject)
        except Exception as exc:
            logger.error("email_send_failed", subject=subject, error=str(exc))


class ConsoleEmailSender:
    """Logs email to console — fallback for local dev without Mailpit."""

    async def send(self, to: str, subject: str, html_body: str, text_body: str) -> None:
        # Bodies contain one-time links (verification / reset tokens), so they are only
        # logged in development; elsewhere only the subject is recorded.
        if settings.app_env == AppEnv.development:
            logger.info("console_email", to=to, subject=subject, body=text_body[:500])
        else:
            logger.info("console_email", to_masked=to[:3] + "***", subject=subject)


class InMemoryEmailSender:
    """Captures emails for test assertions. Never used in production."""

    def __init__(self) -> None:
        self.sent: list[dict[str, str]] = []

    async def send(self, to: str, subject: str, html_body: str, text_body: str) -> None:
        self.sent.append({"to": to, "subject": subject, "html": html_body, "text": text_body})


def get_email_sender() -> EmailSender:
    provider = settings.email_provider.lower()
    if provider in ("mailpit", "smtp"):
        return SmtpEmailSender()
    return ConsoleEmailSender()
