import logging
import smtplib
from email.message import EmailMessage

from app.core.config import settings

logger = logging.getLogger(__name__)


def send_email(to: str, subject: str, body: str) -> None:
    """Sends a plain-text email via SMTP. If SMTP_HOST isn't configured (e.g. local
    dev), logs the email instead of sending — lets OTP signup/verify work end-to-end
    without real mail credentials."""
    if not settings.SMTP_HOST:
        logger.info("mailer: SMTP not configured, logging email instead — to=%s subject=%s body=%s", to, subject, body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.SMTP_FROM_EMAIL
    msg["To"] = to
    msg.set_content(body)

    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(msg)
    logger.info("mailer: sent email to=%s subject=%s", to, subject)
