import json

from allauth.account.decorators import reauthentication_required
from allauth.socialaccount.adapter import get_adapter as get_social_adapter
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from . import push
from .forms import ProfileForm
from .models import ProfilePicture, PushSubscription


@login_required
def profile(request):
    user = request.user
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES)
        if form.is_valid():
            user.first_name = form.cleaned_data["first_name"]
            user.last_name = form.cleaned_data["last_name"]
            user.save(update_fields=["first_name", "last_name"])
            if form.cleaned_data["picture"]:
                ProfilePicture.objects.update_or_create(
                    user=user, defaults={"jpeg": form.cleaned_data["picture"]}
                )
            elif form.cleaned_data["remove_picture"]:
                ProfilePicture.objects.filter(user=user).delete()
            messages.success(request, "Profile saved.")
            # Redirect after POST, so a reload doesn't resubmit the form.
            return redirect("profile")
    else:
        form = ProfileForm(initial={"first_name": user.first_name, "last_name": user.last_name})

    return render(request, "accounts/profile.html", {
        "form": form,
        "has_picture": ProfilePicture.objects.filter(user=user).exists(),
        "push_enabled": push.is_enabled(),
        # Read by static/js/profile.js.
        "push_config": {
            "vapidPublicKey": settings.VAPID_PUBLIC_KEY,
            "subscribeUrl": reverse("push_subscribe"),
            "unsubscribeUrl": reverse("push_unsubscribe"),
        },
        "push_devices": user.push_subscriptions.order_by("created_at"),
        "has_social_providers": bool(get_social_adapter().list_providers(request)),
    })


@login_required
def profile_picture(request, user_id):
    """Any member may see any member's picture; strangers may not."""
    picture = get_object_or_404(ProfilePicture, user_id=user_id)
    response = HttpResponse(bytes(picture.jpeg), content_type="image/jpeg")
    # private: never stored by a shared cache such as a proxy. The URL
    # carries the picture's timestamp, so a changed picture gets a new URL
    # and the old one can be cached for as long as the browser likes.
    response["Cache-Control"] = "private, max-age=31536000, immutable"
    # The bytes are always our own re-encoded JPEG, but say so anyway.
    response["X-Content-Type-Options"] = "nosniff"
    return response


# Deleting is permanent, so it needs a fresh password (or Google/Apple
# sign-in), not just a session that may have been signed in for months on a
# phone someone else has picked up.
@reauthentication_required
def delete_account(request):
    if request.method == "POST":
        user = request.user
        # Sign out first: once the row is gone, the session would point at
        # nothing.
        logout(request)
        # Cascades to email addresses, Google/Apple links, the picture and
        # push subscriptions. Once there is a ledger, its rows must not
        # cascade: see docs/ACCOUNTS.md.
        user.delete()
        messages.success(request, "Your account has been deleted.")
        return redirect("index")
    return render(request, "accounts/delete_account.html")


def _json_body(request):
    try:
        return json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None


@login_required
@require_POST
def push_subscribe(request):
    """Store the subscription the browser handed to static/js/profile.js."""
    if not push.is_enabled():
        return JsonResponse({"error": "Push notifications are not configured."}, status=503)
    data = _json_body(request)
    try:
        endpoint = data["endpoint"]
        p256dh = data["keys"]["p256dh"]
        auth = data["keys"]["auth"]
    except (TypeError, KeyError):
        return HttpResponseBadRequest("Expected a PushSubscription as JSON.")
    if not (isinstance(endpoint, str) and push.is_allowed_endpoint(endpoint)):
        return HttpResponseBadRequest("Unknown push service.")

    # Keyed on the endpoint: a phone passed to another member moves to that
    # member rather than notifying both.
    PushSubscription.objects.update_or_create(
        endpoint=endpoint,
        defaults={
            "user": request.user,
            "p256dh": str(p256dh)[:255],
            "auth": str(auth)[:255],
            "user_agent": request.headers.get("User-Agent", "")[:512],
        },
    )
    return JsonResponse({"ok": True}, status=201)


@require_POST
def push_unsubscribe(request):
    """Forget one device. Sent when a member turns notifications off, and
    when they sign out, so the next person on that phone doesn't receive
    their notifications.

    It needs no session, because sign-out may already have ended it. Knowing
    the endpoint is the credential: it is a long random URL that only that
    browser has ever seen.
    """
    data = _json_body(request)
    endpoint = data.get("endpoint") if isinstance(data, dict) else None
    if not isinstance(endpoint, str):
        return HttpResponseBadRequest("Expected {endpoint: ...} as JSON.")
    PushSubscription.objects.filter(endpoint=endpoint).delete()
    return JsonResponse({"ok": True})


@login_required
@require_POST
def push_test(request):
    sent = push.send_to_user(
        request.user,
        title="planFC",
        body="Notifications are working on this device.",
        url="/profile/",
    )
    if sent:
        messages.success(request, f"Test notification sent to {sent} device{'s' if sent != 1 else ''}.")
    else:
        messages.error(request, "No device accepted the notification. Turn notifications on first.")
    return redirect("profile")
