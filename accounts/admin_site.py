"""Django's /admin/, for superusers using two-factor authentication.

Django's own site lets in anyone with the staff flag, which in this app is
every admin (members.py). Here it takes all three of:

- a superuser, a role set only on the command line (`manage.py superuser`);
- with an authenticator app set up (allauth.mfa);
- who entered one of its codes, or a recovery code, in the last
  SUPERUSER_2FA_MAX_AGE seconds.

Django's username-and-password login form can't ask for a code, so /admin/'s
login page is never shown. It sends each visitor to the step they are
missing instead: the app's sign-in, setting up the authenticator app, or
entering a code.
"""

import time
from urllib.parse import urlencode

from allauth.account.authentication import get_authentication_records
from allauth.mfa.models import Authenticator
from allauth.mfa.utils import is_mfa_enabled
from django.conf import settings
from django.contrib import messages
from django.contrib.admin import AdminSite
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme


def has_authenticator_app(user):
    return is_mfa_enabled(user, [Authenticator.Type.TOTP])


def used_2fa_recently(request):
    """Whether this session entered a code for this user recently. allauth
    keeps a record of each step of signing in (and of reauthenticating) in
    the session, with the time it happened."""
    oldest = time.time() - settings.SUPERUSER_2FA_MAX_AGE
    return any(
        record.get("method") == "mfa" and record.get("at", 0) >= oldest
        for record in get_authentication_records(request, request.user)
    )


def _with_next(url_name, next_url):
    return f"{reverse(url_name)}?{urlencode({'next': next_url})}"


class SuperuserAdminSite(AdminSite):
    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser and used_2fa_recently(request)

    def login(self, request, extra_context=None):
        next_url = request.GET.get("next", "")
        if not url_has_allowed_host_and_scheme(
            next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()
        ):
            next_url = reverse("admin:index")

        user = request.user
        if not user.is_authenticated:
            return redirect(_with_next("account_login", next_url))
        if not (user.is_active and user.is_superuser):
            # Signing in again wouldn't help them.
            return render(request, "accounts/superusers_only.html", status=403)
        if self.has_permission(request):
            return redirect(next_url)
        if not has_authenticator_app(user):
            messages.info(
                request,
                "Database admin needs two-factor authentication. Set up an "
                "authenticator app on your phone first, then open Database admin again.",
            )
            return redirect("mfa_activate_totp")
        return redirect(_with_next("mfa_reauthenticate", next_url))

