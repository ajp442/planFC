from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"


class SuperuserAdminConfig(admin_apps.AdminConfig):
    """Listed in INSTALLED_APPS in place of django.contrib.admin, so that
    admin.site, and everything registered on it, is the superusers-only site
    in admin_site.py. It lives here, not there, because INSTALLED_APPS is
    read before any model can be imported."""

    default = False
    default_site = "accounts.admin_site.SuperuserAdminSite"
