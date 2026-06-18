"""
Daily email digest for live Product Manager job listings.

Fetches the latest cached live jobs, builds an HTML email with
job listings and source breakdown, and sends it via Gmail SMTP.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional


logger = logging.getLogger(__name__)

# ─── Notification settings key (stored in JSON storage) ────────────────────

NOTIF_KEY = "notification_settings"


def _get_data() -> dict[str, Any]:
    """Get the live jobs data dict from JSON storage."""
    from backend.config import settings as app_settings
    from backend.database import storage as json_storage
    data = json_storage._data  # type: ignore[attr-defined]
    if NOTIF_KEY not in data:
        data[NOTIF_KEY] = {
            "enabled": False,
            "recipient_email": app_settings.gmail_email or "",
            "digest_time": "08:00",
            "last_sent_at": None,
        }
    return data


def _save_data() -> None:
    """Persist the notification settings."""
    from backend.database import storage as json_storage
    json_storage._save()  # type: ignore[attr-defined]


def get_notification_settings() -> dict[str, Any]:
    """Get current notification settings."""
    data = _get_data()
    return dict(data.get(NOTIF_KEY, {}))


def update_notification_settings(**kwargs) -> dict[str, Any]:
    """Update one or more notification settings. Returns updated settings."""
    data = _get_data()
    settings_dict = data[NOTIF_KEY]
    for key, value in kwargs.items():
        if key in settings_dict:
            settings_dict[key] = value
    _save_data()
    return dict(settings_dict)


# ─── Digest builder ────────────────────────────────────────────────────────

def build_digest_html(
    jobs: list[dict[str, Any]],
    sources: dict[str, int],
    role: str = "Product Manager",
) -> tuple[str, str]:
    """Build an HTML email body for the daily job digest.

    Returns (html_body, plain_text_body).
    """
    total = len(jobs)

    # Source summary
    source_lines = " | ".join(
        f"{name}: {count}" for name, count in sorted(sources.items())
    )

    # Job rows
    job_rows_html = ""
    job_rows_text = ""

    for i, job in enumerate(jobs[:30]):  # Cap at 30 for email
        title = job.get("title", "Unknown")
        company = job.get("company", "Unknown")
        url = job.get("url", "")
        location = job.get("location", "Remote")
        salary = job.get("salary_range") or "Not listed"
        seniority = job.get("seniority", "")
        source = job.get("source", "jobicy")
        posted = job.get("posted_date", "")

        # Truncate posted date for display
        if posted and len(posted) > 10:
            posted = posted[:10]

        job_rows_html += f"""
        <tr style="border-bottom:1px solid #e2e8f0;">
            <td style="padding:10px 12px;font-size:13px;">
                <a href="{url}" style="color:#6366f1;text-decoration:none;font-weight:600;">{_escape(title)}</a>
                <div style="color:#64748b;font-size:12px;margin-top:2px;">{_escape(company)}</div>
            </td>
            <td style="padding:10px 12px;font-size:12px;color:#64748b;">{_escape(location)}</td>
            <td style="padding:10px 12px;font-size:12px;color:#059669;">{_escape(salary)}</td>
            <td style="padding:10px 12px;font-size:12px;">
                <span style="background:#eef2ff;color:#4338ca;padding:2px 8px;border-radius:4px;font-size:11px;">{_escape(source)}</span>
            </td>
            <td style="padding:10px 12px;font-size:12px;color:#64748b;text-align:center;">
                <a href="{url}" style="display:inline-block;background:#6366f1;color:#fff;padding:4px 14px;border-radius:6px;text-decoration:none;font-size:12px;font-weight:500;">Apply</a>
            </td>
        </tr>"""

        job_rows_text += f"  - {title} @ {company} | {location} | Apply: {url}\n"

    # HTML email
    html = f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"></head>
<body style="margin:0;padding:0;background:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f1f5f9;">
<tr><td style="padding:24px 16px;">
    <table width="600" cellpadding="0" cellspacing="0" style="margin:0 auto;background:#ffffff;border-radius:12px;overflow:hidden;border:1px solid #e2e8f0;">
        <!-- Header -->
        <tr>
            <td style="padding:28px 32px;background:linear-gradient(135deg,#6366f1,#06b6d4);">
                <h1 style="margin:0;color:#fff;font-size:22px;font-weight:700;">📡 Daily Job Digest</h1>
                <p style="margin:6px 0 0;color:rgba(255,255,255,0.85);font-size:14px;">
                    {total} remote <strong>{_escape(role)}</strong> positions found
                </p>
            </td>
        </tr>
        <!-- Summary -->
        <tr>
            <td style="padding:20px 32px;background:#f8fafc;border-bottom:1px solid #e2e8f0;">
                <table width="100%">
                <tr>
                    <td style="font-size:13px;color:#475569;"><strong>📊 Sources:</strong> {source_lines}</td>
                    <td style="font-size:13px;color:#475569;text-align:right;">
                        <strong>📅</strong> {datetime.now(timezone.utc).strftime("%b %d, %Y")}
                    </td>
                </tr>
                </table>
            </td>
        </tr>
        <!-- Jobs Table -->
        <tr>
            <td style="padding:0 32px;">
                <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse;">
                    <thead>
                        <tr style="background:#f8fafc;">
                            <th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;text-align:left;">Job</th>
                            <th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;text-align:left;">Location</th>
                            <th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;text-align:left;">Salary</th>
                            <th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;text-align:left;">Source</th>
                            <th style="padding:12px;font-size:11px;text-transform:uppercase;letter-spacing:0.5px;color:#64748b;text-align:center;">Action</th>
                        </tr>
                    </thead>
                    <tbody>
                        {job_rows_html}
                    </tbody>
                </table>
            </td>
        </tr>
        <!-- Footer -->
        <tr>
            <td style="padding:24px 32px;background:#f8fafc;border-top:1px solid #e2e8f0;">
                <p style="margin:0;font-size:12px;color:#94a3b8;text-align:center;">
                    This is an automated daily digest from <strong>Job Agent</strong>.
                    <br>To unsubscribe, disable notifications in the dashboard.
                </p>
            </td>
        </tr>
    </table>
</td></tr>
</table>
</body>
</html>"""

    # Plain text fallback
    text = f"""DAILY JOB DIGEST — {datetime.now(timezone.utc).strftime("%b %d, %Y")}
{'=' * 60}
{total} remote {role} positions found
Sources: {source_lines}
{'=' * 60}

{job_rows_text}
{'=' * 60}
This is an automated daily digest from Job Agent.
To unsubscribe, disable notifications in the dashboard.
"""

    return html, text


# ─── Send digest ───────────────────────────────────────────────────────────

async def send_daily_digest() -> bool:
    """Build and send the daily email digest to the configured recipient.

    Returns True if sent successfully or if notifications are disabled.
    """
    from backend.api.live_jobs import _get_live_jobs_data

    settings = get_notification_settings()
    if not settings.get("enabled"):
        logger.info("Daily digest: notifications disabled — skipping")
        return True

    recipient = settings.get("recipient_email", "")
    if not recipient:
        logger.warning("Daily digest: no recipient email configured — skipping")
        return False

    # Fetch latest live jobs from cache
    data = _get_live_jobs_data()
    jobs = data.get("live_jobs", [])
    sources = data.get("live_jobs_sources", {})

    if not jobs:
        logger.info("Daily digest: no jobs to report — sending empty digest")

    # Build email
    role = "Product Manager"
    html_body, text_body = build_digest_html(jobs, sources, role=role)
    subject = f"📡 Daily Job Digest: {len(jobs)} remote {role} positions"

    # Send
    from backend.services.email_service import send_email

    success = send_email(
        to_email=recipient,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
    )

    if success:
        # Update last sent timestamp
        update_notification_settings(
            last_sent_at=datetime.now(timezone.utc).isoformat()
        )
        logger.info("Daily digest sent to %s (%d jobs)", recipient, len(jobs))
    else:
        logger.error("Failed to send daily digest to %s", recipient)

    return success


def _escape(text: str) -> str:
    """HTML-escape a string for safe email display."""
    if not text:
        return ""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )
