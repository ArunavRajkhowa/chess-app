"""One outgoing mail path: SMTP with STARTTLS when SMTP_HOST is set, else the text goes to the log.
Brevo and Resend both offer an SMTP relay on their free plans; see .env.example."""
from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .settings import settings

LOGGER = logging.getLogger("chess.mail")


def send(to: str, subject: str, text: str) -> None:
    """Sends the mail, or logs its text (never the address) when no SMTP_HOST is configured."""
    if not settings.SMTP_HOST:
        LOGGER.warning("SMTP_HOST is empty: mail not sent. %s: %s", subject, text)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = settings.MAIL_FROM, to, subject
    msg.set_content(text)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=15) as smtp:
        smtp.starttls()
        if settings.SMTP_USER:
            smtp.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        smtp.send_message(msg)
    LOGGER.info("mail sent: %s", subject)
