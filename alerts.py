"""Safe alert creation and optional email delivery adapters.

No SMS, calls, or emergency-service messages are sent by this project. SMTP
email is explicitly opt-in and is intended only for demonstration contacts.
"""

import os
import smtplib
from email.message import EmailMessage
from typing import Any

import database as db


def build_alert_message(
    event_id: int,
    timestamp: str,
    severity: str,
    location: str,
    snapshot_filename: str,
    incident_details: str = "",
) -> str:
    """Create the human-readable dashboard/email alert text."""
    return (
        f"{incident_details or 'Possible incident — manual review required.'} "
        f"Event #{event_id}. Video time: {timestamp}. "
        f"Location/source: {location}. Severity: {severity}. "
        f"Snapshot: {snapshot_filename}. This is an unverified warning; review the video manually."
    )


def email_is_enabled() -> bool:
    return os.getenv("ENABLE_DEMO_EMAIL", "false").lower() == "true"


def send_optional_email(recipient: str, subject: str, body: str) -> tuple[bool, str]:
    """Send opt-in SMTP email; returns errors instead of raising into the app."""
    if not email_is_enabled():
        return False, "Demo email is disabled (set ENABLE_DEMO_EMAIL=true to enable it)."
    host = os.getenv("SMTP_HOST")
    sender = os.getenv("SMTP_FROM")
    if not host or not sender:
        return False, "SMTP_HOST and SMTP_FROM must be configured for demo email."
    try:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = sender
        message["To"] = recipient
        message.set_content(body)
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "587")), timeout=15) as client:
            if os.getenv("SMTP_USE_TLS", "true").lower() == "true":
                client.starttls()
            username, password = os.getenv("SMTP_USERNAME"), os.getenv("SMTP_PASSWORD")
            if username and password:
                client.login(username, password)
            client.send_message(message)
        return True, "SMTP email accepted for delivery."
    except Exception as error:
        return False, f"Email delivery failed: {error}"


def generate_alert(
    event_id: int,
    timestamp: str,
    severity: str,
    location: str,
    snapshot_filename: str,
    incident_details: str = "",
    allow_external_delivery: bool = False,
) -> dict[str, Any]:
    """Persist a dashboard warning; external email requires explicit opt-in."""
    message = build_alert_message(
        event_id, timestamp, severity, location, snapshot_filename, incident_details
    )
    dashboard_alert_id = db.create_alert(event_id, None, "dashboard", "sent", message)
    db.log_notification_attempt(dashboard_alert_id, None, "delivered", "dashboard", "Displayed in dashboard")
    email_results = []
    contacts = db.get_active_email_contacts() if allow_external_delivery else []
    for contact in contacts:
        alert_id = db.create_alert(event_id, contact["emergency_contact_id"], "email", "pending", message)
        success, result = send_optional_email(contact["email"], f"AccidentGuard Event #{event_id}", message)
        status = "sent" if success else "failed"
        db.update_alert_status(alert_id, status)
        db.log_notification_attempt(alert_id, contact["emergency_contact_id"], status, "smtp", result)
        email_results.append({"contact": contact["contact_name"], "status": status, "message": result})
    return {"alert_id": dashboard_alert_id, "message": message, "email_results": email_results}
