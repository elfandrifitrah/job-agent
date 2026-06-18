"""
API router for email notification settings and manual digest triggers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/notifications", tags=["notifications"])


# ─── Schemas ────────────────────────────────────────────────────────────────

class NotificationSettings(BaseModel):
    enabled: bool = False
    recipient_email: str = ""
    digest_time: str = "08:00"
    last_sent_at: str | None = None


class UpdateNotificationRequest(BaseModel):
    enabled: bool | None = None
    recipient_email: str | None = None
    digest_time: str | None = None


# ─── Endpoints ──────────────────────────────────────────────────────────────


@router.get("/settings", response_model=NotificationSettings)
async def get_settings():
    """Get current email notification settings."""
    from backend.tasks.email_digest import get_notification_settings
    return NotificationSettings(**get_notification_settings())


@router.put("/settings", response_model=NotificationSettings)
async def update_settings(req: UpdateNotificationRequest):
    """Update email notification settings."""
    from backend.tasks.email_digest import update_notification_settings

    kwargs = {}
    if req.enabled is not None:
        kwargs["enabled"] = req.enabled
    if req.recipient_email is not None:
        kwargs["recipient_email"] = req.recipient_email
    if req.digest_time is not None:
        kwargs["digest_time"] = req.digest_time

    updated = update_notification_settings(**kwargs)
    return NotificationSettings(**updated)


@router.post("/send-test")
async def send_test_email(
    email: str = Query("", description="Recipient email (defaults to configured)"),
):
    """Send a test email to verify Gmail SMTP configuration."""
    from backend.config import settings as app_settings
    from backend.services.email_service import send_email

    recipient = email or app_settings.gmail_email
    if not recipient:
        raise HTTPException(
            status_code=400,
            detail="No recipient email. Set GMAIL_EMAIL in .env or pass ?email= parameter.",
        )

    success = send_email(
        to_email=recipient,
        subject="🧪 Job Agent — Test Email",
        html_body="""
        <h2 style="color:#6366f1;">Test Email</h2>
        <p>Your Gmail SMTP configuration is working correctly!</p>
        <p>You will receive daily job digests at your configured time.</p>
        <hr>
        <p style="color:#94a3b8;font-size:12px;">Sent by Job Agent</p>
        """,
    )

    if not success:
        raise HTTPException(
            status_code=502,
            detail="Failed to send test email. Check GMAIL_EMAIL and GMAIL_APP_PASSWORD in .env",
        )

    return {"status": "ok", "message": f"Test email sent to {recipient}"}


@router.post("/send-digest")
async def trigger_digest():
    """Manually trigger a daily digest email (for testing)."""
    from backend.tasks.email_digest import send_daily_digest

    success = await send_daily_digest()

    if not success:
        from backend.tasks.email_digest import get_notification_settings
        settings = get_notification_settings()
        if not settings.get("enabled"):
            raise HTTPException(
                status_code=400,
                detail="Notifications are disabled. Enable them via PUT /api/notifications/settings first.",
            )
        raise HTTPException(
            status_code=502,
            detail="Failed to send digest. Check Gmail config and recipient email.",
        )

    return {"status": "ok", "message": "Daily digest sent successfully"}
