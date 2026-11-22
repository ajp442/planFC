"""Roles and member management: who is an admin, what state an account is
in, invitations, and the record of what admins did.

There are three roles. Everyone with an account is a member, and an admin is a
member with Django's `is_staff` flag. Using the stock flag means no custom
user model and no extra table, and `createsuperuser` accounts count as admins
without further setup. A superuser (`is_superuser`) is an admin who can also
open Django's /admin/ (admin_site.py). That role is set only on the command
line (`manage.py superuser`), and admins can't touch a superuser's account
in the app (is_protected). docs/ADMIN_GUIDE.md describes the roles for the
people who hold them.
"""

import logging
from functools import wraps

from allauth.account.adapter import get_adapter
from allauth.account.models import EmailAddress
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .context_processors import display_name
from .models import AdminAction, UnconfirmedAccount
from .signals import unconfirmed_account_linked

logger = logging.getLogger(__name__)

COMMAND_LINE = "Command line"


# --- Roles -------------------------------------------------------------------

def is_admin(user):
    """Superusers count too, so the account `createsuperuser` makes can manage
    members. A deactivated admin has no powers until reactivated."""
    return bool(
        user is not None
        and user.is_authenticated
        and user.is_active
        and (user.is_staff or user.is_superuser)
    )


def admin_required(view):
    """Signed-out visitors go to sign-in; signed-in members who aren't admins
    get a 403, since signing in again wouldn't help them."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_admin(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def is_active_superuser(user):
    """Who may change the club's money (payments/): record payments and edit
    them. Admins may only look.

    Unlike Database admin (admin_site.py), it asks for no recent two-factor
    code: payments are entered often, from a phone, and the role itself can
    only be given on the server's command line, so no admin, or stolen
    admin session, can grant it."""
    return bool(user is not None and user.is_authenticated and user.is_active and user.is_superuser)


def superuser_required(view):
    """Like admin_required, but only an active superuser gets through."""

    @wraps(view)
    @login_required
    def wrapper(request, *args, **kwargs):
        if not is_active_superuser(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper


def is_only_admin(user):
    if not is_admin(user):
        return False
    others = get_user_model().objects.filter(
        Q(is_staff=True) | Q(is_superuser=True), is_active=True
    ).exclude(pk=user.pk)
    return not others.exists()


def is_protected(user):
    """A superuser's role, access and account can only be changed on the
    command line, so no admin, or stolen admin session, can demote, lock
    out or delete the people who hold the database."""
    return user.is_superuser


SUPERUSER_MESSAGE = (
    "{name} is a superuser. Superusers can only be changed on the server's "
    "command line (manage.py superuser)."
)


def set_admin(user, make_admin):
    if is_protected(user):
        # A superuser is always an admin; `manage.py superuser --remove` first.
        raise ValueError("Can't change a superuser's admin role.")
    user.is_staff = make_admin
    user.save(update_fields=["is_staff"])


# --- Account state -----------------------------------------------------------

DEACTIVATED = "deactivated"
# Made while recording a payment from someone who hasn't signed up.
UNCONFIRMED_ACCOUNT = "unconfirmed_account"
INVITED = "invited"
UNCONFIRMED = "unconfirmed"
ACTIVE = "active"

STATUS_LABELS = {
    DEACTIVATED: "Deactivated",
    UNCONFIRMED_ACCOUNT: "Unconfirmed",
    INVITED: "Invited",
    UNCONFIRMED: "Email not confirmed",
    ACTIVE: "Active",
}


def is_unconfirmed_account(user):
    return UnconfirmedAccount.objects.filter(user=user).exists()


def is_invite_pending(user):
    """Added by an admin and not yet set up: no password, never signed in.
    An unconfirmed account looks the same, but has no address to invite."""
    return bool(user.email) and user.last_login is None and not user.has_usable_password()


def status(user, has_confirmed_email, unconfirmed_account=False):
    if not user.is_active:
        return DEACTIVATED
    if unconfirmed_account:
        return UNCONFIRMED_ACCOUNT
    if is_invite_pending(user):
        return INVITED
    if not has_confirmed_email:
        return UNCONFIRMED
    return ACTIVE


def has_confirmed_email(user):
    return EmailAddress.objects.filter(user=user, verified=True).exists()


def email_in_use(email):
    return (
        get_user_model().objects.filter(email__iexact=email).exists()
        or EmailAddress.objects.filter(email__iexact=email).exists()
    )


def confirm_email(user):
    """Mark the member's address confirmed without the emailed link, for when
    the email never arrives. Returns False if there is no address to confirm."""
    if not user.email:
        return False
    address, _ = EmailAddress.objects.get_or_create(user=user, email=user.email.lower())
    address.verified = True
    address.primary = address.primary or not EmailAddress.objects.filter(user=user, primary=True).exists()
    address.save(update_fields=["verified", "primary"])
    return True


# --- The record --------------------------------------------------------------

def label(user):
    name = user.get_full_name()
    if name and user.email:
        return f"{name} <{user.email}>"
    return name or user.email or user.get_username()


def record(actor, target, action, detail=""):
    """`actor` is None for changes made from the command line."""
    return AdminAction.objects.create(
        actor=actor,
        actor_label=label(actor) if actor else COMMAND_LINE,
        target=target,
        target_label=label(target),
        action=action,
        detail=detail[:320],
    )


# --- Invitations -------------------------------------------------------------

class InviteTokenGenerator(PasswordResetTokenGenerator):
    """Signs invitation links the way Django signs password-reset links.

    The token covers the member's password and last sign-in, so a link stops
    working the moment it has been used, and it expires after
    PASSWORD_RESET_TIMEOUT (three days). Its own salt keeps an invitation
    from being replayed as a password reset, or the reverse.
    """

    key_salt = "accounts.members.InviteTokenGenerator"


invite_tokens = InviteTokenGenerator()


def invite_valid_days():
    return settings.PASSWORD_RESET_TIMEOUT // (60 * 60 * 24)


def invite_path(user):
    return reverse("accept_invite", kwargs={
        "uidb64": urlsafe_base64_encode(force_bytes(user.pk)),
        "token": invite_tokens.make_token(user),
    })


def user_from_invite(uidb64, token):
    """The invited member, or None if the link is forged, used or expired."""
    User = get_user_model()
    try:
        user = User.objects.get(pk=urlsafe_base64_decode(uidb64).decode())
    except (TypeError, ValueError, OverflowError, UnicodeDecodeError, User.DoesNotExist):
        return None
    if not user.is_active or not invite_tokens.check_token(user, token):
        return None
    return user


@transaction.atomic
def create_invited_member(request, *, email, first_name, last_name, make_admin):
    """An account with no password. The invitation link lets its owner choose
    one, and following it is what confirms the address."""
    adapter = get_adapter(request)
    user = adapter.new_user(request)
    user.email = email
    user.first_name = first_name
    user.last_name = last_name
    user.is_staff = make_admin
    user.set_unusable_password()
    # allauth's way of making up the username nobody ever sees.
    adapter.populate_username(request, user)
    user.save()
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=False)
    record(request.user, user, AdminAction.Action.INVITED)
    if make_admin:
        record(request.user, user, AdminAction.Action.MADE_ADMIN)
    return user


def send_invite(request, user):
    """Returns whether the email was handed to the mail server. A failure
    must not undo the account: the admin can send the invitation again."""
    try:
        get_adapter(request).send_mail("accounts/email/invite", user.email, {
            "member": user,
            "inviter_name": display_name(request.user),
            "invite_url": request.build_absolute_uri(invite_path(user)),
            "valid_days": invite_valid_days(),
        })
    except Exception:
        logger.exception("Could not send the invitation to user %s", user.pk)
        return False
    return True


# --- Unconfirmed accounts ------------------------------------------------------

def split_name(name):
    """"Bob the Guest" -> ("Bob", "the Guest"): the first word is the first name."""
    first, _, last = " ".join(name.split()).partition(" ")
    return first[:150], last[:150]


@transaction.atomic
def create_unconfirmed_member(request, name):
    """An account for someone who hasn't signed up, so what they pay can be
    recorded against a member and found later. No email, no password: nobody
    can sign in to it. link() hands it over once they have a real account."""
    adapter = get_adapter(request)
    user = adapter.new_user(request)
    user.first_name, user.last_name = split_name(name)
    user.email = ""
    user.set_unusable_password()
    adapter.populate_username(request, user)
    user.save()
    UnconfirmedAccount.objects.create(
        user=user, created_by=request.user, created_by_label=label(request.user),
    )
    record(request.user, user, AdminAction.Action.ADDED_UNCONFIRMED)
    return user


def can_link(unconfirmed, account):
    """Why `unconfirmed` can't be linked into `account`, or None if it can."""
    if not is_unconfirmed_account(unconfirmed):
        return "Only an unconfirmed account can be linked into another."
    if account.pk == unconfirmed.pk:
        return "An account can't be linked into itself."
    if is_unconfirmed_account(account):
        return "Link it into a real account: one that someone signs in to."
    return None


@transaction.atomic
def link(actor, unconfirmed, account):
    """Hands everything recorded against an unconfirmed account to the
    person's real one, then deletes the unconfirmed account.

    Each app moves its own records (signals.unconfirmed_account_linked), in
    this same transaction, so either everything moves or nothing does.
    Returns what was moved, as short descriptions."""
    problem = can_link(unconfirmed, account)
    if problem:
        raise ValueError(problem)
    responses = unconfirmed_account_linked.send(
        sender=UnconfirmedAccount, actor=actor, unconfirmed=unconfirmed, account=account,
    )
    moved = [text for _, text in responses if text]
    detail = f"From “{label(unconfirmed)}”" + (f": {', '.join(moved)} moved" if moved else "")
    record(actor, account, AdminAction.Action.LINKED, detail=detail)
    unconfirmed.delete()
    return moved
