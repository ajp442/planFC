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
        parser.add_argument(
            "--superuser", action="store_true",
            help="Also let them edit the database directly in Django's /admin/, "
                 "which adds a Database admin item to their Admin menu.",
        )

    def handle(self, *args, email, remove, superuser, **options):
        if remove and superuser:
            raise CommandError("--remove already takes away everything; don't combine it with --superuser.")
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

        members.set_admin(user, not remove)
        if superuser:
            user.is_superuser = True
            user.save(update_fields=["is_superuser"])
        members.record(
            None, user,
            AdminAction.Action.REMOVED_ADMIN if remove else AdminAction.Action.MADE_ADMIN,
            detail="With database access (/admin/)" if superuser else "",
        )
        if remove:
            self.stdout.write(f"{members.label(user)} is no longer an admin.")
        else:
            self.stdout.write(
                f"{members.label(user)} is now an admin"
                + (", with database access at /admin/." if superuser else ".")
            )
            if not user.is_active:
                self.stderr.write("Their account is deactivated, so they can't sign in until it is reactivated.")
