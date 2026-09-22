from django.contrib import admin
from django.urls import path
from django.views.generic import TemplateView

from core import views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", views.index, name="index"),
    path("healthz", views.healthz, name="healthz"),
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
