from datetime import timedelta

from django.core import mail
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone

from complaints.followup import check
from complaints.models import Complaint

from .test_notify import make_complaint


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class FollowUpDatabaseTests(TestCase):
    def age(self, complaint, hours):
        Complaint.objects.filter(pk=complaint.pk).update(
            created_at=timezone.now() - timedelta(hours=hours))
        complaint.refresh_from_db()

    def test_overdue_complaint_escalates_saves_and_emails_once(self):
        c = make_complaint()
        self.age(c, 30)
        check(c)
        c.refresh_from_db()
        self.assertEqual(c.fu_level, 1)
        self.assertIn("Escalated to Head of Roads Dept", c.fu_history[-1])
        self.assertEqual([m.to for m in mail.outbox], [["head.roads@example.com"]])

        check(c)   # nothing new has happened: no second email, no new history
        self.assertEqual(len(mail.outbox), 1)

    def test_add_hours_moves_the_clock(self):
        c = make_complaint()
        check(c, add_hours=30)
        c.refresh_from_db()
        self.assertEqual(c.fu_level, 1)

    def test_management_command_checks_open_complaints(self):
        c = make_complaint()
        self.age(c, 30)
        call_command("run_followups", stdout=_Sink())
        c.refresh_from_db()
        self.assertEqual(c.fu_level, 1)

    def test_command_skips_duplicates_and_closed(self):
        dup = make_complaint(ref="C-2", status=Complaint.Status.DUPLICATE, fu_status="")
        closed = make_complaint(ref="C-3", fu_status="closed")
        self.age(dup, 100)
        self.age(closed, 100)
        call_command("run_followups", stdout=_Sink())
        dup.refresh_from_db()
        closed.refresh_from_db()
        self.assertEqual(dup.fu_level, 0)
        self.assertEqual(closed.fu_level, 0)
        self.assertEqual(mail.outbox, [])


class _Sink:
    def write(self, *_):
        pass

    def flush(self):
        pass
