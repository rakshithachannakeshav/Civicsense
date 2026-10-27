from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Create a department official (or make an existing user one)."

    def add_arguments(self, parser):
        parser.add_argument("username")
        parser.add_argument("password", nargs="?", default=None,
                            help="Required when creating a new user.")
        parser.add_argument("--email", default="")

    def handle(self, *args, **options):
        User = get_user_model()
        username = options["username"]
        user = User.objects.filter(username=username).first()
        if user is None:
            if not options["password"]:
                raise CommandError("Give a password to create a new user.")
            user = User.objects.create_user(
                username=username, password=options["password"], email=options["email"]
            )
            self.stdout.write(f"Created user {username}.")
        group, _ = Group.objects.get_or_create(name=settings.OFFICIALS_GROUP)
        user.groups.add(group)
        self.stdout.write(self.style.SUCCESS(f"{username} is now an official."))
