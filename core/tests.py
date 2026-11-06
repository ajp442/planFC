from django.test import TestCase, override_settings
from django.urls import reverse


class PageTests(TestCase):
    def test_index_renders(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "planFC")

    def test_healthz_reports_database(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertIs(response.json()["database"], True)

    @override_settings(APP_VERSION="1.2.3", GIT_COMMIT="0123456789abcdef")
    def test_healthz_reports_the_running_release(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.json()["version"], "1.2.3")
        self.assertEqual(response.json()["commit"], "0123456789abcdef")

    @override_settings(APP_VERSION="1.2.3", GIT_COMMIT="0123456789abcdef")
    def test_index_shows_version_and_short_commit(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Version 1.2.3 (0123456)")

    @override_settings(APP_VERSION="dev", GIT_COMMIT="")
    def test_local_build_shows_dev_without_a_commit(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Version dev</p>", html=False)


class ProgressiveWebAppTests(TestCase):
    def test_service_worker_is_served_from_the_root(self):
        """Scope is the whole point: a worker served from /static/ could only
        control /static/*, so the app would never be installable."""
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/javascript")

    def test_manifest_is_valid_json_with_required_fields(self):
        response = self.client.get("/manifest.webmanifest")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/manifest+json")

        manifest = response.json()
        self.assertEqual(manifest["start_url"], "/")
        self.assertEqual(manifest["display"], "standalone")

        # Chrome will not offer installation without both of these sizes.
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)

    def test_index_links_the_manifest_and_apple_touch_icon(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, 'rel="manifest"')
        # iOS reads this instead of the manifest icons when adding to home screen.
        self.assertContains(response, 'rel="apple-touch-icon"')


class EnvironmentTests(TestCase):
    """Dev and production must look different once installed, where the
    address bar that would tell them apart is gone."""

    @override_settings(ENVIRONMENT="production")
    def test_production_uses_the_standard_icons_and_name(self):
        manifest = self.client.get("/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], "planFC")
        self.assertTrue(all("/icons/dev/" not in icon["src"] for icon in manifest["icons"]))
        self.assertNotContains(self.client.get(reverse("index")), "Development")

    @override_settings(ENVIRONMENT="development")
    def test_development_uses_dev_icons_name_and_badge(self):
        manifest = self.client.get("/manifest.webmanifest").json()
        self.assertEqual(manifest["name"], "planFC Dev")
        self.assertEqual(manifest["short_name"], "planFC Dev")
        self.assertTrue(all("/icons/dev/" in icon["src"] for icon in manifest["icons"]))

        page = self.client.get(reverse("index"))
        self.assertContains(page, '<p class="badge">Development</p>', html=True)
        self.assertContains(page, '<meta name="apple-mobile-web-app-title" content="planFC Dev">', html=True)
        self.assertContains(page, "/static/icons/dev/icon_180")

        # The service worker pre-caches the icon the page actually shows.
        self.assertContains(self.client.get("/sw.js"), "/static/icons/dev/icon_192")
