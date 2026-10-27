from django.utils import timezone

from agents import followup_app
from .notify import notify_events


def check(complaint, add_hours=0):
    """Run one follow-up check for a complaint, save the outcome and notify.

    The graph's clock is hours since the complaint was created.
    add_hours pretends extra time has passed (for testing).
    """
    elapsed = (timezone.now() - complaint.created_at).total_seconds() / 3600
    state = {
        "id": complaint.ref,
        "department": complaint.department,
        "desk": complaint.desk,
        "status": complaint.fu_status,
        "level": complaint.fu_level,
        "window": complaint.fu_window,
        "due_hour": complaint.fu_due_hour,
        "reminded": complaint.fu_reminded,
        "history": list(complaint.fu_history),
        "now": int(elapsed + add_hours),
    }
    result = followup_app.invoke(state)

    complaint.fu_status = result["status"]
    complaint.fu_level = result["level"]
    complaint.fu_window = result["window"]
    complaint.fu_due_hour = result["due_hour"]
    complaint.fu_reminded = result["reminded"]
    complaint.fu_history = result["history"]
    complaint.save(update_fields=[
        "fu_status", "fu_level", "fu_window",
        "fu_due_hour", "fu_reminded", "fu_history",
    ])

    # Save first, then send: a mail failure must not lose the state change,
    # and an event is only ever emitted once because the state has moved on.
    notify_events(complaint, result.get("events", []))
    return result
