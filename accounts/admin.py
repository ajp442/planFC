"""Django's /admin/ is the operator's database tool, for superusers only
(admin_site.py). Admins manage members inside the app instead
(member_views.py)."""

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from . import members
from .models import AdminAction, ProfilePicture, PushSubscription

User = get_user_model()


admin.site.unregister(User)


@admin.register(User)
class PlanUserAdmin(UserAdmin):
    """Django's user editor, minus the superuser role, which is set only on
    the command line (`manage.py superuser`). A superuser can't use this
    page to make another, nor demote, deactivate or delete one."""

    list_display = ("email", "first_name", "last_name", "is_staff", "is_superuser", "is_active")

    def get_readonly_fields(self, request, obj=None):
        fields = ["is_superuser", "groups", "user_permissions"]
        if obj is not None and members.is_protected(obj):
            fields += ["is_staff", "is_active"]
        return fields

    def has_delete_permission(self, request, obj=None):
        if obj is not None and members.is_protected(obj):
            return False
        return super().has_delete_permission(request, obj)

    def get_actions(self, request):
        # Bulk "Delete selected" checks no single object, so it could take a
        # superuser with it. Members are deleted one at a time.
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions


@admin.register(ProfilePicture)
class ProfilePictureAdmin(admin.ModelAdmin):
    list_display = ("user", "updated_at")
    search_fields = ("user__email", "user__first_name", "user__last_name")
    # Removing an offensive picture is the only edit an admin needs.
    readonly_fields = ("user", "updated_at")

    def has_add_permission(self, request):
        return False


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ("user", "device_name", "created_at")
    search_fields = ("user__email",)
    readonly_fields = ("user", "endpoint", "p256dh", "auth", "user_agent", "created_at")

    def has_add_permission(self, request):
        return False


@admin.register(AdminAction)
class AdminActionAdmin(admin.ModelAdmin):
    """Read-only: the point of the record is that nobody rewrites it."""

    list_display = ("created_at", "actor_label", "action", "target_label", "detail")
    list_filter = ("action",)
    search_fields = ("actor_label", "target_label")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
