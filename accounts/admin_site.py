"""Django's /admin/, for superusers only.

Django's own site lets in anyone with the staff flag, which in this app is
every admin (members.py). Here staff alone gets the login page, so the
database editor is reachable only by the accounts the server's command line
made superusers (`manage.py superuser`).
"""

from django.contrib.admin import AdminSite
from django.contrib.admin.apps import AdminConfig


class SuperuserAdminSite(AdminSite):
    def has_permission(self, request):
        user = request.user
        return user.is_active and user.is_superuser


class SuperuserAdminConfig(AdminConfig):
    """Listed in INSTALLED_APPS in place of django.contrib.admin, so that
    admin.site, and everything registered on it, is the site above."""

    default_site = "accounts.admin_site.SuperuserAdminSite"
