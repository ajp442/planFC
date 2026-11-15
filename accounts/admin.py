"""Django's /admin/ is the operator's database tool, behind its own username
login. Admins manage members inside the app instead (member_views.py)."""

from django.contrib import admin

from .models import AdminAction, ProfilePicture, PushSubscription


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
