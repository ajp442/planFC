"""Sending Web Push notifications to a member's devices.

The browser, not us, chooses where messages go: subscribing hands the page an
endpoint URL at its vendor's push service, which the page posts here. We then
POST each encrypted message to that URL, and the vendor wakes the device's
service worker (core/templates/pwa/sw.js), which shows the notification.
"""

import json
import logging
from urllib.parse import urlsplit

from django.conf import settings
from pywebpush import WebPushException, webpush
from requests import RequestException

from .models import PushSubscription

log = logging.getLogger(__name__)

# The server POSTs to whatever endpoint a member's browser reports, so an
# unchecked endpoint would let any member point our server at an internal
# address (the database, a cloud metadata service). Only the push services of
# the browsers we support are accepted, and only over HTTPS.
PUSH_SERVICE_HOSTS = (
    "fcm.googleapis.com",            # Chrome, Edge and other Chromium on Android and desktop
    "updates.push.services.mozilla.com",  # Firefox
    "push.services.mozilla.com",
    "web.push.apple.com",            # Safari on macOS, iOS and iPadOS
    "notify.windows.com",            # legacy Edge, as *.notify.windows.com
)

# How long a push service keeps trying to deliver to a device that is off.
# A day covers a phone that is switched off overnight.
TIME_TO_LIVE = 24 * 60 * 60


def is_enabled():
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def is_allowed_endpoint(endpoint):
    try:
        parts = urlsplit(endpoint)
    except ValueError:
        return False
    host = (parts.hostname or "").lower()
    return parts.scheme == "https" and any(
        host == allowed or host.endswith("." + allowed) for allowed in PUSH_SERVICE_HOSTS
    )


def send_to_user(user, title, body, url="/"):
    """Notify every device the member has subscribed. Returns how many push
    services accepted the message.

    A device that has uninstalled the app, or revoked permission, makes its
    push service answer 404 or 410; its subscription is deleted then, since
    nothing will ever be delivered to it again.
    """
    if not is_enabled():
        return 0

    payload = json.dumps({"title": title, "body": body, "url": url})
    delivered = 0
    for subscription in user.push_subscriptions.all():
        try:
            webpush(
                subscription_info={
                    "endpoint": subscription.endpoint,
                    "keys": {"p256dh": subscription.p256dh, "auth": subscription.auth},
                },
                data=payload,
                vapid_private_key=settings.VAPID_PRIVATE_KEY,
                vapid_claims={"sub": settings.VAPID_SUBJECT},
                ttl=TIME_TO_LIVE,
                timeout=10,
            )
            delivered += 1
        except WebPushException as error:
            status = getattr(error.response, "status_code", None)
            if status in (404, 410):
                subscription.delete()
            else:
                log.warning("Push to %s failed: %s", subscription, error)
        except RequestException as error:
            # The push service was unreachable. Keep the subscription; the
            # device itself may be fine.
            log.warning("Push to %s failed: %s", subscription, error)
    return delivered
