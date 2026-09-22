from django.test import TestCase
from django.urls import reverse


class PageTests(TestCase):
    def test_index_renders(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "planFC")

    def test_healthz_reports_database(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok", "database": True})


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
