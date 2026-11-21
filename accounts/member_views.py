"""The Members area: admins add and manage accounts here, inside the app,
instead of in Django's /admin/. The rules are in members.py; the guide for
the admins themselves is docs/ADMIN_GUIDE.md.
"""

from allauth.account.decorators import reauthentication_required
from allauth.account.models import EmailAddress
from allauth.socialaccount.models import SocialAccount
from django.contrib import messages
from django.contrib.auth import get_user_model, login
from django.contrib.auth.forms import SetPasswordForm
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from . import members
from .context_processors import display_name, initials, picture_url
from .forms import AddMemberForm, MemberNameForm
from .members import admin_required
from .models import AdminAction, ProfilePicture

User = get_user_model()
Action = AdminAction.Action

# The backend an invited member is signed in with after choosing a password:
# the same one that handles every other email sign-in.
EMAIL_BACKEND = "allauth.account.auth_backends.AuthenticationBackend"


def _row(user, confirmed_ids, picture_times):
    """What the list and the detail page show for one member."""
    state = members.status(user, user.pk in confirmed_ids)
    updated_at = picture_times.get(user.pk)
    return {
        "user": user,
        "name": display_name(user),
        "initials": initials(user),
        "picture_url": picture_url(user.pk, updated_at) if updated_at else None,
        "is_admin": user.is_staff or user.is_superuser,
        "is_superuser": user.is_superuser,
        "status": state,
        "status_label": members.STATUS_LABELS[state],
    }


def _rows(users):
    users = list(users)
    ids = [user.pk for user in users]
    confirmed_ids = set(
        EmailAddress.objects.filter(user_id__in=ids, verified=True).values_list("user_id", flat=True)
    )
    # Timestamps only: the list must not pull every picture's bytes.
    picture_times = dict(
        ProfilePicture.objects.filter(user_id__in=ids).values_list("user_id", "updated_at")
    )
    return [_row(user, confirmed_ids, picture_times) for user in users]


@admin_required
def member_list(request):
    query = request.GET.get("q", "").strip()
    # "Admins and roles" in the header menu: the same list, admins only.
    admins_only = request.GET.get("role") == "admin"
    users = User.objects.order_by("first_name", "last_name", "email")
    if admins_only:
        users = users.filter(Q(is_staff=True) | Q(is_superuser=True))
    if query:
        for word in query.split():
            users = users.filter(
                Q(first_name__icontains=word) | Q(last_name__icontains=word) | Q(email__icontains=word)
            )
    return render(request, "accounts/members/list.html", {
        "rows": _rows(users),
        "query": query,
        "admins_only": admins_only,
        "total": User.objects.count(),
    })


@admin_required
def member_add(request):
    form = AddMemberForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = members.create_invited_member(request, **form.cleaned_data)
        if members.send_invite(request, user):
            messages.success(request, f"{display_name(user)} was added, and an invitation was sent to {user.email}.")
        else:
            messages.error(
                request,
                f"{display_name(user)} was added, but the invitation email could not be sent. "
                "Try “Send the invitation again” below.",
            )
        return redirect("member_detail", user_id=user.pk)
    return render(request, "accounts/members/add.html", {
        "form": form,
        "valid_days": members.invite_valid_days(),
    })


@admin_required
def member_detail(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    if request.method == "POST":
        form = MemberNameForm(request.POST)
        if form.is_valid():
            old_name = member.get_full_name()
            member.first_name = form.cleaned_data["first_name"]
            member.last_name = form.cleaned_data["last_name"]
            if member.get_full_name() != old_name:
                member.save(update_fields=["first_name", "last_name"])
                members.record(request.user, member, Action.NAME_CHANGED, detail=f"Was “{old_name}”")
            messages.success(request, "Name saved.")
            return redirect("member_detail", user_id=member.pk)
    else:
        form = MemberNameForm(initial={"first_name": member.first_name, "last_name": member.last_name})

    row = _rows([member])[0]
    sign_in_methods = (["Password"] if member.has_usable_password() else []) + [
        account.provider.title() for account in SocialAccount.objects.filter(user=member)
    ]
    return render(request, "accounts/members/detail.html", {
        "member": member,
        "row": row,
        "form": form,
        "is_self": member.pk == request.user.pk,
        "sign_in_methods": sign_in_methods,
        "email_confirmed": members.has_confirmed_email(member),
        "history": AdminAction.objects.filter(target=member)[:20],
    })


# --- One-tap actions -----------------------------------------------------------
#
# Each takes the admin and the member, and returns (ok, message). All of them
# can be undone or repeated, so they need no confirmation page.

def _resend_invite(request, member):
    if not member.is_active or not members.is_invite_pending(member):
        return False, "They have already set up their account, so there is no invitation to send."
    if not members.send_invite(request, member):
        return False, "The invitation email could not be sent. Check the email settings and try again."
    members.record(request.user, member, Action.INVITE_RESENT)
    return True, f"A new invitation was sent to {member.email}."


def _confirm_email(request, member):
    if members.has_confirmed_email(member):
        return True, "Their email address was already confirmed."
    if not members.confirm_email(member):
        return False, "This account has no email address to confirm."
    members.record(request.user, member, Action.EMAIL_CONFIRMED, detail=member.email)
    return True, f"{member.email} is marked as confirmed. They can sign in now."


def _deactivate(request, member):
    if member.pk == request.user.pk:
        return False, "You can't deactivate your own account. Ask another admin."
    if members.is_protected(member):
        return False, members.SUPERUSER_MESSAGE.format(name=display_name(member))
    if member.is_active:
        member.is_active = False
        member.save(update_fields=["is_active"])
        members.record(request.user, member, Action.DEACTIVATED)
    return True, f"{display_name(member)} is deactivated and can no longer sign in."


def _reactivate(request, member):
    if not member.is_active:
        member.is_active = True
        member.save(update_fields=["is_active"])
        members.record(request.user, member, Action.REACTIVATED)
    return True, f"{display_name(member)} can sign in again."


def _remove_picture(request, member):
    deleted, _ = ProfilePicture.objects.filter(user=member).delete()
    if deleted:
        members.record(request.user, member, Action.PICTURE_REMOVED)
    return True, "Their profile picture was removed."


MEMBER_ACTIONS = {
    "resend-invite": _resend_invite,
    "confirm-email": _confirm_email,
    "deactivate": _deactivate,
    "reactivate": _reactivate,
    "remove-picture": _remove_picture,
}


@admin_required
@require_POST
def member_action(request, user_id, action):
    member = get_object_or_404(User, pk=user_id)
    ok, message = MEMBER_ACTIONS[action](request, member)
    (messages.success if ok else messages.error)(request, message)
    return redirect("member_detail", user_id=member.pk)


# --- Actions behind a confirmation page ----------------------------------------
#
# Granting admin powers and deleting an account are the two changes worth
# stopping for. Like deleting your own account, both need the password to
# have been re-entered in the last few minutes, so a phone left unlocked
# can't be used to hand out the role.

@admin_required
@reauthentication_required
def member_role(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    if member.pk == request.user.pk:
        messages.error(request, "You can't change your own role. Ask another admin.")
        return redirect("member_detail", user_id=member.pk)
    if members.is_protected(member):
        messages.error(request, members.SUPERUSER_MESSAGE.format(name=display_name(member)))
        return redirect("member_detail", user_id=member.pk)
    currently_admin = member.is_staff or member.is_superuser
    if request.method == "POST":
        members.set_admin(member, not currently_admin)
        if currently_admin:
            members.record(request.user, member, Action.REMOVED_ADMIN)
            messages.success(request, f"{display_name(member)} is no longer an admin.")
        else:
            members.record(request.user, member, Action.MADE_ADMIN)
            messages.success(request, f"{display_name(member)} is now an admin.")
        return redirect("member_detail", user_id=member.pk)
    return render(request, "accounts/members/role.html", {
        "member": member,
        "target_name": display_name(member),
        "currently_admin": currently_admin,
    })


@admin_required
@reauthentication_required
def member_delete(request, user_id):
    member = get_object_or_404(User, pk=user_id)
    if member.pk == request.user.pk:
        # One way to delete yourself, with its own safeguards.
        return redirect("delete_account")
    if members.is_protected(member):
        messages.error(request, members.SUPERUSER_MESSAGE.format(name=display_name(member)))
        return redirect("member_detail", user_id=member.pk)
    if request.method == "POST":
        name = display_name(member)
        # Recorded first: the label has to be read before the row is gone.
        members.record(request.user, member, Action.DELETED)
        member.delete()
        messages.success(request, f"{name}'s account has been deleted.")
        return redirect("member_list")
    return render(request, "accounts/members/delete.html", {
        "member": member,
        "target_name": display_name(member),
    })


@admin_required
def member_activity(request):
    return render(request, "accounts/members/activity.html", {
        "history": AdminAction.objects.all()[:200],
    })


# --- The invited member's side -------------------------------------------------

def accept_invite(request, uidb64, token):
    """Where the invitation email leads: choose a password, and you're in.

    Reaching this page with a valid link proves the address is theirs, the
    same proof a confirmation email gives, so the address is marked confirmed.
    """
    member = members.user_from_invite(uidb64, token)
    if member is None:
        return render(request, "accounts/members/invite_invalid.html", status=410)
    form = SetPasswordForm(member, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        members.confirm_email(member)
        # Replaces whoever was signed in on this device, if anyone.
        login(request, member, backend=EMAIL_BACKEND)
        messages.success(request, "Your account is ready. Welcome to planFC.")
        return redirect("index")
    return render(request, "accounts/members/invite.html", {
        "form": form,
        "invited_name": display_name(member),
        "invited_email": member.email,
    })
