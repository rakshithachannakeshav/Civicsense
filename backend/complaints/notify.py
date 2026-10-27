"""Send the reminders and escalations that the follow-up graph decides on.

The graph (agents.py) only decides and returns "events". This module turns
events into emails. A failure to send never breaks the follow-up check: the
event is already in the complaint's history.
"""
import json
import logging
from functools import lru_cache

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)

SUBJECTS = {
    "reminder": "Reminder",
    "escalation": "Escalated",
    "critical": "CRITICAL",
    "closed": "Resolved",
}


@lru_cache(maxsize=None)
def load_directory(path=None):
    path = path or settings.DIRECTORY_FILE
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        logger.warning("Directory file %s not found; using the fallback address.", path)
        return {}


def recipient_for(level, department, desk):
    """Email address of whoever holds the complaint at this level."""
    directory = load_directory()
    dept = directory.get("departments", {}).get(department, {})
    if level == 0:
        address = dept.get("desks", {}).get(desk)
    elif level == 1:
        address = dept.get("head")
    else:
        address = directory.get("commissioner")
    return address or settings.NOTIFY_FALLBACK_EMAIL


def build_message(complaint, event):
    subject = f"[CivicSense] {SUBJECTS.get(event['kind'], 'Update')}: {complaint.ref}"
    if event["kind"] == "closed":
        body = (
            f"Your report {complaint.ref} has been marked as resolved.\n\n"
            f"Problem: {complaint.category.replace('_', ' ')} at "
            f"{complaint.location or 'the location you gave'}\n"
            f"Handled by: {complaint.department}, {complaint.desk}\n"
        )
    else:
        body = (
            f"{event['message']}\n\n"
            f"Reference: {complaint.ref}\n"
            f"Problem: {complaint.category.replace('_', ' ')} "
            f"(severity: {complaint.severity})\n"
            f"Location: {complaint.location or 'not given'}\n"
            f"Department: {complaint.department}, {complaint.desk}\n\n"
            f"Details: {complaint.text}\n"
        )
    return subject, body


def notify_events(complaint, events):
    """Email each event. Returns the number of emails sent."""
    sent = 0
    for event in events:
        if event["kind"] == "closed":
            # Tell the citizen who filed it, if we have an address
            to = complaint.owner.email if complaint.owner and complaint.owner.email else None
        else:
            to = recipient_for(event["level"], complaint.department, complaint.desk)
        if not to:
            continue
        subject, body = build_message(complaint, event)
        try:
            send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, [to], fail_silently=False)
            sent += 1
        except Exception:
            logger.exception("Could not send %s email for %s", event["kind"], complaint.ref)
    return sent
