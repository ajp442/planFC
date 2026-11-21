"""What a member's account holds beyond Django's User and allauth's email
addresses: a profile picture and the devices that receive push notifications.

The name lives on User itself (first_name, last_name), where Google and Apple
sign-in already put it.
"""

from django.conf import settings
from django.db import models


class ProfilePicture(models.Model):
    """A member's picture, kept in Postgres rather than on disk.

    Each is a re-encoded 256 px JPEG of roughly 15-30 KB, so even 500 members
    add only a few megabytes to the database. In exchange, the scheduled
    pg_dump that PLAN.md requires backs pictures up along with everything
    else, and there is no media volume to mount, serve or forget to back up.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="profile_picture",
    )
    jpeg = models.BinaryField(editable=False)
    # Part of the picture's URL, so a browser that cached the old picture
    # fetches the new one as soon as it changes.
    updated_at = models.DateTimeField(auto_now=True, editable=False)

    def __str__(self):
        return f"Picture of {self.user}"


class PushSubscription(models.Model):
    """One browser or installed app that has agreed to receive notifications.

    A member has one per device. The endpoint is a URL at the browser vendor's
    push service (Google, Mozilla, Apple, Microsoft), and the two keys encrypt
    each message so that only that browser can read it.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="push_subscriptions",
    )
    endpoint = models.URLField(max_length=2048, unique=True)
    p256dh = models.CharField(max_length=255)
    auth = models.CharField(max_length=255)
    # Shown on the profile page and in the admin, so a member can tell their
    # phone from their laptop.
    user_agent = models.CharField(max_length=512, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    def __str__(self):
        return f"{self.user} on {self.device_name}"

    @property
    def device_name(self):
        agent = self.user_agent
        for marker, name in (
            ("iPhone", "iPhone"),
            ("iPad", "iPad"),
            ("Android", "Android"),
            ("Macintosh", "Mac"),
            ("Windows", "Windows"),
            ("Linux", "Linux"),
        ):
            if marker in agent:
                return name
        return "Unknown device"


class AdminAction(models.Model):
    """One thing an admin did to a member's account: who, to whom, what, when.

    Rows are only ever added, never edited (PLAN.md: manual changes carry a
    timestamp nobody can alter). The labels copy each person's name and email
    at the time, so the record still reads properly after either account is
    deleted and its foreign key has gone null.
    """

    class Action(models.TextChoices):
        INVITED = "invited", "Added and invited"
        INVITE_RESENT = "invite_resent", "Invitation sent again"
        MADE_ADMIN = "made_admin", "Made an admin"
        REMOVED_ADMIN = "removed_admin", "Admin role removed"
        # Only ever from the command line (`manage.py superuser`).
        MADE_SUPERUSER = "made_superuser", "Made a superuser"
        REMOVED_SUPERUSER = "removed_superuser", "Superuser role removed"
        DEACTIVATED = "deactivated", "Deactivated"
        REACTIVATED = "reactivated", "Reactivated"
        EMAIL_CONFIRMED = "email_confirmed", "Email marked as confirmed"
        NAME_CHANGED = "name_changed", "Name changed"
        PICTURE_REMOVED = "picture_removed", "Profile picture removed"
        DELETED = "deleted", "Account deleted"

    # Null for changes made on the command line (`make_admin`, `superuser`),
    # and after the admin's own account is deleted.
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="admin_actions_taken",
    )
    actor_label = models.CharField(max_length=320)
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        on_delete=models.SET_NULL,
        related_name="admin_actions_received",
    )
    target_label = models.CharField(max_length=320)
    action = models.CharField(max_length=32, choices=Action.choices)
    # Free text for the few actions that need it, e.g. the old name.
    detail = models.CharField(max_length=320, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, editable=False)

    class Meta:
        ordering = ["-created_at", "-pk"]

    def __str__(self):
        return f"{self.actor_label}: {self.get_action_display()}: {self.target_label}"
