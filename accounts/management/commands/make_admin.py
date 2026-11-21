from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from accounts import members
from accounts.models import AdminAction


class Command(BaseCommand):
    help = (
        "Make an existing member an admin, by the email address they sign in with. "
        "Needed once, for the club's first admin; after that admins manage roles "
        "on the Members page. Also the way back in if no admin is left."
    )

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument(
            "--remove", action="store_true",
            help="Take the admin role away instead of granting it.",
        )

    def handle(self, *args, email, remove, **options):
        User = get_user_model()
        users = User.objects.filter(
            Q(email__iexact=email) | Q(emailaddress__email__iexact=email)
        ).distinct()
        if not users:
            raise CommandError(
                f"No account uses {email}. They have to sign up first (or be added on the Members page)."
            )
        if len(users) > 1:
            raise CommandError(f"{len(users)} accounts use {email}; fix that in /admin/ first.")
        user = users[0]
        if remove and user.is_superuser:
            # The superuser role is changed with its own command, so that
            # taking it away is always a deliberate step.
            raise CommandError(
                f"{members.label(user)} is a superuser. Run `manage.py superuser {email} --remove` first."
            )

        members.set_admin(user, not remove)
        members.record(
            None, user,
            AdminAction.Action.REMOVED_ADMIN if remove else AdminAction.Action.MADE_ADMIN,
        )
        if remove:
            self.stdout.write(f"{members.label(user)} is no longer an admin.")
        else:
            self.stdout.write(f"{members.label(user)} is now an admin.")
            if not user.is_active:
                self.stderr.write("Their account is deactivated, so they can't sign in until it is reactivated.")
