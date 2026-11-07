from django.urls import reverse

from .models import ProfilePicture


def member(request):
    """The signed-in member's name and picture, for the header on every page.

    Only the picture's timestamp is read here, never its bytes: the header
    needs a URL, and the browser fetches the image itself.
    """
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return {}
    updated_at = (
        ProfilePicture.objects.filter(user=user).values_list("updated_at", flat=True).first()
    )
    return {
        "member_name": display_name(user),
        "member_initials": initials(user),
        "member_picture_url": picture_url(user.pk, updated_at) if updated_at else None,
    }


def display_name(user):
    return user.get_full_name() or user.email.split("@")[0] or user.get_username()


def initials(user):
    parts = [user.first_name, user.last_name] if user.first_name else [display_name(user)]
    return "".join(part[0] for part in parts if part).upper()[:2]


def picture_url(user_id, updated_at):
    # The timestamp makes the URL change with the picture, so it can be cached
    # for a long time without a member ever seeing their old one.
    return f"{reverse('profile_picture', args=[user_id])}?v={int(updated_at.timestamp())}"
