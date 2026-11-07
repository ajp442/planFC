from django.contrib import admin

from .models import ProfilePicture, PushSubscription


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
