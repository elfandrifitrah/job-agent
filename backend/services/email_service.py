"""
Email notification service — sends emails via Gmail SMTP using App Passwords.

Uses the existing gmail_email and gmail_app_password settings from config.
Supports HTML-formatted emails with plain-text fallback.
"""

from __future__ import annotations

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from backend.config import settings

logger = logging.getLogger(__name__)


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    from_name: str = "Job Agent",
) -> bool:
    """Send an email via Gmail SMTP using an App Password.

    Args:
        to_email: Recipient email address.
        subject: Email subject line.
        html_body: HTML content for the email.
        text_body: Optional plain-text fallback (auto-generated if omitted).
        from_name: Display name for the sender.

    Returns:
        True if the email was sent successfully, False otherwise.
    """
    if not settings.gmail_email or not settings.gmail_app_password:
        logger.warning("Gmail not configured — set GMAIL_EMAIL and GMAIL_APP_PASSWORD in .env")
        return False

    if not to_email:
        logger.warning("No recipient email provided — skipping send")
        return False

    # Auto-generate plain-text if not provided (strip HTML tags)
    if not text_body:
        import re
        text_body = re.sub(r"<[^>]+>", "", html_body)
        text_body = re.sub(r"\s+", " ", text_body).strip()

    try:
        msg = MIMEMultipart("alternative")
        msg["From"] = f"{from_name} <{settings.gmail_email}>"
        msg["To"] = to_email
        msg["Subject"] = subject

        # Attach plain-text and HTML versions
        msg.attach(MIMEText(text_body, "plain"))
        msg.attach(MIMEText(html_body, "html"))

        # Connect to Gmail SMTP and send
        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=30) as server:
            server.login(settings.gmail_email, settings.gmail_app_password)
            server.send_message(msg)

        logger.info("Email sent to %s: '%s'", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "Gmail SMTP auth failed for %s. "
            "Use an App Password (not your regular password). "
            "Generate one at https://myaccount.google.com/apppasswords",
            settings.gmail_email,
        )
        return False
    except smtplib.SMTPException as e:
        logger.error("SMTP error sending to %s: %s", to_email, e)
        return False
    except Exception as e:
        logger.error("Failed to send email to %s: %s", to_email, e)
        return False
