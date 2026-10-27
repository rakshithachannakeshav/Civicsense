from django.contrib.auth import get_user_model
from django.core import mail
from django.test import TestCase, override_settings

from complaints import notify
from complaints.models import Complaint


def make_complaint(**kwargs):
    defaults = dict(
        text="Deep pothole near the school", location="5th Cross, Jayanagar",
        ref="C-1", status=Complaint.Status.ROUTED, category="road_damage",
        severity="high", department="Roads Dept", desk="Ward Engineer",
        sla_hours=24, fu_status="open", fu_window=24, fu_due_hour=24,
    )
    defaults.update(kwargs)
    return Complaint.objects.create(**defaults)


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   PASSWORD_HASHERS=["django.contrib.auth.hashers.MD5PasswordHasher"])
class NotifyTests(TestCase):
    def test_recipient_by_level(self):
        self.assertEqual(notify.recipient_for(0, "Roads Dept", "Ward Engineer"),
                         "ward.engineer@example.com")
        self.assertEqual(notify.recipient_for(1, "Roads Dept", "Ward Engineer"),
                         "head.roads@example.com")
        self.assertEqual(notify.recipient_for(2, "Roads Dept", "Ward Engineer"),
                         "commissioner@example.com")

    def test_unknown_department_falls_back(self):
        self.assertEqual(notify.recipient_for(0, "Nowhere Dept", "Nobody"),
                         "civicsense-alerts@example.com")

    def test_reminder_email_goes_to_the_desk(self):
        c = make_complaint()
        sent = notify.notify_events(c, [
            {"kind": "reminder", "level": 0, "to": "Ward Engineer (Roads Dept)",
             "message": "Reminder sent to Ward Engineer (Roads Dept). Due at hour 24."}])
        self.assertEqual(sent, 1)
        self.assertEqual(mail.outbox[0].to, ["ward.engineer@example.com"])
        self.assertIn("C-1", mail.outbox[0].subject)
        self.assertIn("Reminder", mail.outbox[0].subject)

    def test_closed_email_goes_to_the_citizen(self):
        user = get_user_model().objects.create_user("asha", "asha@example.org", "pw-12345-xyz")
        c = make_complaint(owner=user)
        notify.notify_events(c, [{"kind": "closed", "level": 0, "to": "x", "message": "Resolved."}])
        self.assertEqual(mail.outbox[0].to, ["asha@example.org"])

    def test_closed_without_citizen_email_sends_nothing(self):
        c = make_complaint()
        sent = notify.notify_events(c, [{"kind": "closed", "level": 0, "to": "x", "message": "Resolved."}])
        self.assertEqual(sent, 0)
        self.assertEqual(mail.outbox, [])

    @override_settings(EMAIL_BACKEND="complaints.tests.test_notify.BrokenBackend")
    def test_mail_failure_does_not_raise(self):
        c = make_complaint()
        with self.assertLogs("complaints.notify", level="ERROR"):
            sent = notify.notify_events(c, [
                {"kind": "escalation", "level": 1, "to": "Head", "message": "Escalated."}])
        self.assertEqual(sent, 0)


from django.core.mail.backends.base import BaseEmailBackend  # noqa: E402


class BrokenBackend(BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionError("SMTP server is down")
