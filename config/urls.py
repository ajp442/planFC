from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    # allauth: sign in and up, sign out, email confirmation, password reset
    # and change, email addresses, Google and Apple.
    path("accounts/", include("allauth.urls")),
    # Ours: profile, picture, account deletion, push subscriptions.
    path("", include("accounts.urls")),
    path("", views.index, name="index"),
    path("healthz", views.healthz, name="healthz"),
    # What the service worker shows offline in place of a page it may not
    # cache (anything a signed-in member sees). Pre-cached at install.
    path("offline/", TemplateView.as_view(template_name="core/offline.html"), name="offline"),
    # Served from the site root, not /static/. A service worker's default scope
    # is the directory it is served from, so /static/sw.js could only control
    # /static/* and the PWA would never install.
    path(
        "sw.js",
        TemplateView.as_view(
            template_name="pwa/sw.js",
            content_type="application/javascript",
        ),
        name="service_worker",
    ),
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="pwa/manifest.webmanifest",
            content_type="application/manifest+json",
        ),
        name="manifest",
    ),
]
