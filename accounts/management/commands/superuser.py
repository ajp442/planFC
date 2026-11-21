"""The superuser role: the only accounts that can open Django's /admin/,
and only with two-factor authentication (admin_site.py).

Set only here, on the server's command line. Nothing in the app, /admin/
included, can grant or remove it, and admins can't change a superuser's
role, deactivate them or delete them (members.is_protected).
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Q

from allauth.mfa.models import Authenticator

from accounts import members
from accounts.models import AdminAction


class Command(BaseCommand):
    help = (
        "Make a member a superuser, by the email address they sign in with: an admin "
        "who can also edit the database directly in Django's /admin/. Superusers can "
        "only be made or removed with this command."
    )

    def add_arguments(self, parser):
        parser.add_argument("email", nargs="?")
        parser.add_argument(
            "--remove", action="store_true",
            help="Take the superuser role away. They stay an admin; use "
                 "`make_admin --remove` afterwards to take that away too.",
        )
        parser.add_argument(
            "--reset-2fa", action="store_true", dest="reset_2fa",
            help="Delete their authenticator app and recovery codes, for a lost phone. "
                 "They set up a new one the next time they open Database admin.",
        )
        parser.add_argument(
            "--list", action="store_true", dest="list_only", help="List the superusers and change nothing.",
        )

    def handle(self, *args, email, remove, reset_2fa, list_only, **options):
        User = get_user_model()
        if list_only:
            if email or remove or reset_2fa:
                raise CommandError("--list takes no email address and no other option.")
            superusers = User.objects.filter(is_superuser=True).order_by("email")
            for user in superusers:
                notes = [] if user.is_active else ["deactivated"]
                if not Authenticator.objects.filter(user=user, type=Authenticator.Type.TOTP).exists():
                    notes.append("no two-factor authentication yet")
                self.stdout.write(members.label(user) + (f" ({', '.join(notes)})" if notes else ""))
            if not superusers:
                self.stdout.write("There are no superusers.")
            return
        if not email:
            raise CommandError("Give the email address of the member, or --list.")

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

        if reset_2fa:
            if remove:
                raise CommandError("Use --reset-2fa on its own.")
            deleted, _ = Authenticator.objects.filter(user=user).delete()
            if not deleted:
                self.stdout.write(f"{members.label(user)} has no two-factor authentication; nothing changed.")
                return
            members.record(None, user, AdminAction.Action.TWO_FACTOR_RESET)
            self.stdout.write(
                f"{members.label(user)}'s authenticator app and recovery codes are deleted. "
                "They can sign in with their password alone, and set up a new app the "
                "next time they open Database admin."
            )
            return

        if remove:
            if not user.is_superuser:
                self.stdout.write(f"{members.label(user)} is not a superuser; nothing changed.")
                return
            user.is_superuser = False
            # A superuser is always an admin, and stays one.
            user.is_staff = True
            user.save(update_fields=["is_superuser", "is_staff"])
            members.record(None, user, AdminAction.Action.REMOVED_SUPERUSER)
            self.stdout.write(
                f"{members.label(user)} is no longer a superuser and can't open /admin/. "
                "They are still an admin."
            )
            return

        if user.is_superuser:
            self.stdout.write(f"{members.label(user)} is already a superuser; nothing changed.")
            return
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=["is_superuser", "is_staff"])
        members.record(None, user, AdminAction.Action.MADE_SUPERUSER)
        self.stdout.write(
            f"{members.label(user)} is now a superuser. The first time they open Database admin, "
            "they will be asked to set up an authenticator app."
        )
        if not user.is_active:
            self.stderr.write("Their account is deactivated, so they can't sign in until it is reactivated.")
