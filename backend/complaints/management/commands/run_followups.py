from django.core.management.base import BaseCommand

from complaints.followup import check
from complaints.models import Complaint


class Command(BaseCommand):
    help = "Run one follow-up check over all open complaints."

    def add_arguments(self, parser):
        parser.add_argument(
            "--add-hours", type=int, default=0,
            help="Pretend this many extra hours have passed (for testing).",
        )

    def handle(self, *args, **options):
        add = options["add_hours"]
        complaints = list(Complaint.objects.filter(
            status=Complaint.Status.ROUTED,
            fu_status__in=["open", "resolved"],
        ))
        for c in complaints:
            before = len(c.fu_history)
            check(c, add_hours=add)
            for line in c.fu_history[before:]:
                self.stdout.write(f"{c.ref}: {line}")
        self.stdout.write(self.style.SUCCESS(f"Checked {len(complaints)} complaint(s)."))