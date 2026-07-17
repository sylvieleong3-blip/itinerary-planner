"""Email notifications for trip events (optional SMTP)."""

import logging
import os
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.models import UserTrip

logger = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(os.getenv("SMTP_HOST") and os.getenv("SMTP_FROM"))


def _send_email(to: str, subject: str, body: str) -> None:
    if not _smtp_configured():
        logger.info("Trip notification (no SMTP): to=%s subject=%s\n%s", to, subject, body)
        return

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = os.environ["SMTP_FROM"]
    msg["To"] = to
    msg.set_content(body)

    host = os.environ["SMTP_HOST"]
    port = int(os.getenv("SMTP_PORT", "587"))
    user = os.getenv("SMTP_USER")
    password = os.getenv("SMTP_PASSWORD")

    with smtplib.SMTP(host, port, timeout=15) as server:
        server.starttls()
        if user and password:
            server.login(user, password)
        server.send_message(msg)


def notify_trip_members(
    db: Session,
    trip,
    *,
    subject: str,
    body: str,
    app_url: str = "",
) -> None:
    """Email all logged-in users linked to this trip."""
    links = db.query(UserTrip).filter(UserTrip.trip_id == trip.id).all()
    emails_sent: set[str] = set()
    plan_url = f"{app_url}/t/{trip.share_code}/plan" if app_url else f"/t/{trip.share_code}/plan"
    full_body = f"{body}\n\nView plan: {plan_url}"

    for link in links:
        email = link.user.email
        if email in emails_sent:
            continue
        try:
            _send_email(email, f"[{trip.name}] {subject}", full_body)
            emails_sent.add(email)
        except Exception:
            logger.exception("Failed to send trip notification to %s", email)
