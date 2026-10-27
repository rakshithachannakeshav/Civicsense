import time

from django.core.management.base import BaseCommand
from django.db import OperationalError, ProgrammingError

from complaints.followup import check
from complaints.models import Complaint


class Command(BaseCommand):
    help = (
        "Run follow-up checks over all open complaints. "
        "Once by default; with --loop, forever, every --interval seconds."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--add-hours", type=int, default=0,
            help="Pretend this many extra hours have passed (for testing).",
        )
        parser.add_argument(
            "--loop", action="store_true",
            help="Keep running: this is how the scheduler container works.",
        )
        parser.add_argument(
            "--interval", type=int, default=300,
            help="Seconds between checks with --loop (default 300).",
        )

    def run_once(self, add_hours):
        complaints = list(Complaint.objects.filter(
            status=Complaint.Status.ROUTED,
            fu_status__in=["open", "resolved"],
        ))
        for c in complaints:
            before = len(c.fu_history)
            check(c, add_hours=add_hours)
            for line in c.fu_history[before:]:
                self.stdout.write(f"{c.ref}: {line}")
        self.stdout.write(self.style.SUCCESS(f"Checked {len(complaints)} complaint(s)."))
        return len(complaints)

    def handle(self, *args, **options):
        if not options["loop"]:
            self.run_once(options["add_hours"])
            return

        self.stdout.write(f"Scheduler started: checking every {options['interval']} s.")
        while True:
            try:
                self.run_once(options["add_hours"])
            except (OperationalError, ProgrammingError) as exc:
                # Most likely the database is not migrated yet (the backend
                # container runs migrate on start) or briefly locked. Retry.
                self.stderr.write(f"Database not ready, will retry: {exc}")
            except Exception as exc:  # one bad complaint must not stop the scheduler
                self.stderr.write(f"Follow-up check failed, will retry: {exc!r}")
            self.stdout.flush()
            time.sleep(options["interval"])
