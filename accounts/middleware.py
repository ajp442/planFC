from django.utils.cache import patch_cache_control


class PrivatePagesMiddleware:
    """Mark every page a signed-in member sees as `Cache-Control: no-store`.

    The service worker caches pages for offline use, and its cache belongs to
    the browser, not to whoever is signed in. Without this, one member's
    balance could be shown offline to the next person on the same phone. The
    worker skips any response marked no-store (core/templates/pwa/sw.js), and
    so do browsers' own HTTP caches.

    Account pages are marked too even when nobody is signed in, since their
    URLs carry one-time keys (email confirmation, password reset).

    A view that sets its own Cache-Control (a profile picture, say) keeps it.
    """

    PRIVATE_PREFIXES = ("/accounts/", "/profile/", "/push/", "/admin/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if response.has_header("Cache-Control"):
            return response
        user = getattr(request, "user", None)
        if (user is not None and user.is_authenticated) or request.path.startswith(self.PRIVATE_PREFIXES):
            patch_cache_control(response, private=True, no_store=True)
        return response
