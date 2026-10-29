from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import connection
from django.utils import timezone

from agents import new_record, process_complaint
from complaints.followup import check
from complaints.models import Complaint

DEMO_PASSWORD = "demo1234"

# (owner, text, location, scenario)
# Scenarios set up the follow-up state so the queue shows every stage:
#   fresh       just filed, open
#   open:N      filed N hours ago, still open
#   reminder    close to its deadline, reminder sent
#   escalated   missed the desk deadline, now with the department head
#   critical    missed every deadline, flagged critical
#   resolved:N  filed N hours ago, fixed by an official and closed
SAMPLES = [
    ("priya", "Huge pothole near the school gate, very dangerous for kids on bikes",
     "80 Feet Road, Indiranagar, Bengaluru", "open:3"),
    ("arjun", "Dangerous pothole outside the school, two bikes slipped this morning",
     "Outside the school gate, 80 Feet Road, Indiranagar", "fresh"),
    ("priya", "Garbage has not been collected for four days and the bin is overflowing",
     "5th Cross, Jayanagar 4th Block, Bengaluru", "reminder"),
    ("arjun", "Street light has not been working for a week, the road is completely dark at night",
     "27th Main, HSR Layout Sector 2, Bengaluru", "escalated"),
    ("meera", "Burst water pipe, water flooding the road since early morning",
     "1st Block, Koramangala, Bengaluru", "resolved:3"),
    ("meera", "Construction debris and waste dumped on the footpath, people walk on the road",
     "ITPL Main Road, Whitefield, Bengaluru", "critical"),
    ("priya", "Low water pressure, no supply to our house in the mornings",
     "12th Cross, Malleshwaram, Bengaluru", "open:5"),
    ("arjun", "Street lamp flickering all night outside the bus stop",
     "Bannerghatta Road, BTM Layout, Bengaluru", "open:2"),
    ("meera", "something is wrong here", "", "fresh"),
    ("kiran", "Deep crater in the middle of the road after the rains, it nearly caused an accident",
     "Outer Ring Road, near Marathahalli bridge, Bengaluru", "open:10"),
    ("kiran", "Garbage bins overflowing next to the vegetable market, stray dogs spreading the waste",
     "KR Market, Chickpet, Bengaluru", "escalated"),
    ("priya", "Water pipe leaking at the junction, the road is always wet and slippery",
     "Hebbal flyover service road, Bengaluru", "reminder"),
    ("arjun", "Three street lights out in a row on the main road, people are afraid to walk at night",
     "Sarjapur Road, Bellandur, Bengaluru", "open:20"),
    ("meera", "Pothole filled with water right outside the metro station exit",
     "Yeshwanthpur metro station, Bengaluru", "resolved:30"),
    ("kiran", "Rubbish not picked up for a week, the smell is unbearable",
     "3rd Main, Rajajinagar, Bengaluru", "resolved:50"),
    ("meera", "Pipe leaking at the Hebbal junction, water all over the service road",
     "Hebbal flyover service road, Bengaluru", "fresh"),
    ("arjun", "Broken footpath slabs along the road, a senior citizen tripped and fell",
     "Church Street, MG Road, Bengaluru", "open:8"),
    ("kiran", "Street lamp pole bent and hanging over the road after the storm, dangerous",
     "100 Feet Road, Domlur, Bengaluru", "escalated"),
    ("priya", "Dead animal and waste lying on the roadside for two days",
     "Banashankari 2nd Stage, Bengaluru", "reminder"),
    ("kiran", "Problem near my house, please check", "Vijayanagar, Bengaluru", "fresh"),
]


class Command(BaseCommand):
    help = ("Fill the database with demo users and complaints at different "
            "follow-up stages. Runs the real triage pipeline.")

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true",
                            help="Delete all existing complaints first.")

    def user(self, username, official=False):
        User = get_user_model()
        user, created = User.objects.get_or_create(
            username=username, defaults={"email": f"{username}@example.com"})
        if created:
            user.set_password(DEMO_PASSWORD)
            user.save()
        if official:
            group, _ = Group.objects.get_or_create(name=settings.OFFICIALS_GROUP)
            user.groups.add(group)
        return user

    def file(self, owner, text, location):
        """Same steps as ComplaintViewSet.perform_create."""
        c = Complaint.objects.create(owner=owner, text=text, location=location)
        c.ref = f"C-{c.pk}"
        known = [
            {"ref": k.ref, "category": k.category,
             "desc_vec": k.desc_vec, "loc_vec": k.loc_vec}
            for k in Complaint.objects.filter(
                status=Complaint.Status.ROUTED, desc_vec__isnull=False)
        ]
        try:
            result = process_complaint(text, location, known=known, complaint_id=c.ref)
        except Exception:
            c.delete()      # do not keep a half-processed complaint
            raise

        c.category = result.get("category", "")
        c.severity = result.get("severity", "")
        c.reason = result.get("reason", "")
        if result.get("duplicate_of"):
            c.status = Complaint.Status.DUPLICATE
            c.duplicate_of = result["duplicate_of"]
            c.note = result.get("note", "")
        elif result.get("letter"):
            c.status = Complaint.Status.ROUTED
            for field in ("department", "desk", "sla_hours", "rule",
                          "letter", "desc_vec", "loc_vec"):
                setattr(c, field, result[field])
            rec = new_record(c.ref, c.department, c.desk, c.sla_hours)
            c.fu_status = rec["status"]
            c.fu_level = rec["level"]
            c.fu_window = rec["window"]
            c.fu_due_hour = rec["due_hour"]
            c.fu_reminded = rec["reminded"]
            c.fu_history = rec["history"]
        else:
            c.status = Complaint.Status.NEEDS_DETAILS
            c.department = result.get("department", "Pending")
            c.note = result.get("note", "")
        c.save()
        return c

    def age(self, c, scenario):
        """Backdate the complaint and replay the follow-up checks it would have had."""
        sla = c.sla_hours
        name, _, hours = scenario.partition(":")
        # Hours at which the scheduler "ran", ending at the complaint's age
        steps = {
            "open": [int(hours or 0)],
            "reminder": [int(sla * 0.85)],
            "escalated": [int(sla * 0.85), sla + 1, sla + 4],
            "critical": [int(sla * 0.85), sla + 1, sla + 10, sla + 14, sla + 26],
            "resolved": [int(hours or 3)],
        }[name]
        age = steps[-1]
        Complaint.objects.filter(pk=c.pk).update(
            created_at=timezone.now() - timedelta(hours=age))
        c.refresh_from_db()
        for hour in steps:
            check(c, add_hours=hour - age)
        if name == "resolved":
            c.fu_status = "resolved"
            c.save(update_fields=["fu_status"])
            check(c)

    def handle(self, *args, **options):
        if options["reset"]:
            n, _ = Complaint.objects.all().delete()
            if connection.vendor == "sqlite":   # restart numbering at C-1
                with connection.cursor() as cursor:
                    cursor.execute("DELETE FROM sqlite_sequence WHERE name = %s",
                                   [Complaint._meta.db_table])
            self.stdout.write(f"Deleted {n} existing complaint row(s).")

        self.user("officer", official=True)
        users = {name: self.user(name) for name in ("priya", "arjun", "meera", "kiran")}

        for owner, text, location, scenario in SAMPLES:
            if Complaint.objects.filter(owner=users[owner], text=text).exclude(ref="").exists():
                self.stdout.write(f"skip   already seeded: {text[:40]}")
                continue
            c = self.file(users[owner], text, location)
            if c.status == Complaint.Status.ROUTED and scenario != "fresh":
                self.age(c, scenario)
                c.refresh_from_db()
            self.stdout.write(
                f"{c.ref:6} {c.status:13} {c.fu_status or '-':9} "
                f"{c.category or '-':12} {c.desk or c.duplicate_of or '-'}")

        self.stdout.write(self.style.SUCCESS(
            f"Done. Log in as officer / priya / arjun / meera / kiran "
            f"(password {DEMO_PASSWORD} for users created now)."))
