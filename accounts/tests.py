import base64
import json
import os
import re
from io import BytesIO, StringIO
from unittest import mock

from allauth.account.models import EmailAddress
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from py_vapid import Vapid01
from pywebpush import WebPushException

from config.settings import _social_providers

from . import push
from .models import ProfilePicture, PushSubscription

User = get_user_model()

PASSWORD = "correct-horse-battery-staple"
FCM_ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc123"


def make_member(email="sam@example.com", first_name="Sam", last_name="Keeper", verified=True):
    """A member who signed up and confirmed their address, as allauth would
    leave them."""
    user = User.objects.create_user(
        username=email.split("@")[0], email=email, password=PASSWORD,
        first_name=first_name, last_name=last_name,
    )
    EmailAddress.objects.create(user=user, email=email, primary=True, verified=verified)
    return user


def image_upload(name="photo.jpg", fmt="JPEG", size=(800, 600), color="red", exif=None):
    out = BytesIO()
    image = Image.new("RGB", size, color)
    kwargs = {"exif": exif} if exif is not None else {}
    image.save(out, format=fmt, **kwargs)
    return SimpleUploadedFile(name, out.getvalue(), content_type=f"image/{fmt.lower()}")


def b64url(data):
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


class SignupTests(TestCase):
    def signup(self, **overrides):
        data = {
            "first_name": "Alex",
            "last_name": "Morgan",
            "email": "alex@example.com",
            "password1": PASSWORD,
            "password2": PASSWORD,
        }
        data.update(overrides)
        return self.client.post(reverse("account_signup"), data)

    def test_signup_page_asks_for_name_email_and_password(self):
        response = self.client.get(reverse("account_signup"))
        for field in ("first_name", "last_name", "email", "password1", "password2"):
            self.assertContains(response, f'name="{field}"')

    def test_signup_stores_the_name_and_sends_a_confirmation_email(self):
        response = self.signup()
        user = User.objects.get(email="alex@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Alex", "Morgan"))

        # Not signed in until the address is confirmed.
        self.assertRedirects(response, reverse("account_email_verification_sent"))
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alex@example.com"])

    def test_following_the_confirmation_link_verifies_and_signs_in(self):
        self.signup()
        link = re.search(r"https?://testserver(/accounts/confirm-email/\S+)", mail.outbox[0].body).group(1)
        self.client.post(link)

        self.assertTrue(EmailAddress.objects.get(email="alex@example.com").verified)
        self.assertEqual(int(self.client.session["_auth_user_id"]), User.objects.get(email="alex@example.com").pk)

    def test_first_name_is_required(self):
        response = self.signup(first_name="")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(email="alex@example.com").exists())

    def test_an_email_address_can_only_have_one_account(self):
        make_member(email="alex@example.com")
        self.signup()
        self.assertEqual(User.objects.filter(email__iexact="alex@example.com").count(), 1)

    def test_an_invalid_email_address_is_refused(self):
        response = self.signup(email="not-an-email")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.count(), 0)


class LoginTests(TestCase):
    def login(self, email="sam@example.com", password=PASSWORD):
        return self.client.post(reverse("account_login"), {"login": email, "password": password})

    def test_a_confirmed_member_signs_in_with_email_and_password(self):
        user = make_member()
        response = self.login()
        self.assertRedirects(response, reverse("index"))
        self.assertEqual(int(self.client.session["_auth_user_id"]), user.pk)

    def test_an_unconfirmed_address_cannot_sign_in(self):
        make_member(verified=False)
        self.login()
        self.assertNotIn("_auth_user_id", self.client.session)
        # allauth sends a fresh confirmation link instead.
        self.assertEqual(len(mail.outbox), 1)

    def test_a_wrong_password_is_refused(self):
        make_member()
        self.login(password="wrong")
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_session_outlives_the_browser_and_lasts_months(self):
        """An installed app must not ask for a password on every launch: the
        cookie is persistent (has a Max-Age) and lasts 180 days."""
        make_member()
        response = self.login()
        cookie = response.cookies["sessionid"]
        self.assertEqual(int(cookie["max-age"]), 180 * 24 * 60 * 60)
        self.assertFalse(self.client.session.get_expire_at_browser_close())

    def test_each_visit_extends_the_session(self):
        make_member()
        self.login()
        response = self.client.get(reverse("index"))
        # Re-sent on every response, so 180 days counts from the last visit.
        self.assertIn("sessionid", response.cookies)
        self.assertEqual(int(response.cookies["sessionid"]["max-age"]), 180 * 24 * 60 * 60)

    def test_sign_out(self):
        make_member()
        self.login()
        self.client.post(reverse("account_logout"))
        self.assertNotIn("_auth_user_id", self.client.session)


class SocialProviderTests(TestCase):
    def test_no_provider_buttons_without_credentials(self):
        response = self.client.get(reverse("account_login"))
        self.assertNotContains(response, "Continue with")

    @override_settings(SOCIALACCOUNT_PROVIDERS={
        "google": {"APPS": [{"client_id": "id", "secret": "secret"}]},
    })
    def test_google_button_appears_once_configured(self):
        response = self.client.get(reverse("account_login"))
        self.assertContains(response, "Continue with Google")
        self.assertNotContains(response, "Continue with Apple")

    def test_providers_are_configured_from_the_environment(self):
        env = {
            "GOOGLE_CLIENT_ID": "g-id", "GOOGLE_CLIENT_SECRET": "g-secret",
            "APPLE_CLIENT_ID": "com.example.planfc", "APPLE_TEAM_ID": "TEAM",
            "APPLE_KEY_ID": "KEY",
            "APPLE_PRIVATE_KEY": "-----BEGIN PRIVATE KEY-----\\nabc\\n-----END PRIVATE KEY-----",
        }
        with mock.patch.dict(os.environ, env):
            providers = _social_providers()
        self.assertEqual(providers["google"]["APPS"][0]["client_id"], "g-id")
        apple = providers["apple"]["APPS"][0]
        self.assertEqual((apple["client_id"], apple["secret"], apple["key"]), ("com.example.planfc", "KEY", "TEAM"))
        # A one-line .env value comes back as the multi-line PEM Apple issued.
        self.assertEqual(apple["settings"]["certificate_key"].count("\n"), 2)

    def test_no_providers_without_the_environment(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(_social_providers(), {})


class ProfileTests(TestCase):
    def setUp(self):
        self.user = make_member()
        self.client.force_login(self.user)

    def post_profile(self, **data):
        data.setdefault("first_name", "Sam")
        data.setdefault("last_name", "Keeper")
        return self.client.post(reverse("profile"), data)

    def test_profile_needs_sign_in(self):
        self.client.logout()
        response = self.client.get(reverse("profile"))
        self.assertRedirects(response, f"{reverse('account_login')}?next={reverse('profile')}")

    def test_member_changes_their_name(self):
        response = self.post_profile(first_name="Samantha", last_name="Kerr")
        self.assertRedirects(response, reverse("profile"))
        self.user.refresh_from_db()
        self.assertEqual(self.user.get_full_name(), "Samantha Kerr")

    def test_header_shows_name_and_initials(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "Sam Keeper")
        self.assertContains(response, ">SK</span>")

    def test_uploaded_picture_is_squared_shrunk_and_stripped_of_location(self):
        exif = Image.Exif()
        exif[0x010F] = "PhoneMaker"  # Make
        exif[0x8825] = {2: (51.0, 30.0, 0.0)}  # GPSInfo: latitude
        self.post_profile(picture=image_upload(size=(1200, 800), exif=exif))

        stored = Image.open(BytesIO(bytes(ProfilePicture.objects.get(user=self.user).jpeg)))
        self.assertEqual(stored.format, "JPEG")
        self.assertEqual(stored.size, (256, 256))
        self.assertEqual(dict(stored.getexif()), {})

    def test_sideways_phone_photo_is_turned_upright(self):
        # Top half red, bottom half blue, stored rotated with an EXIF note
        # (orientation 6) saying "turn me 90 degrees clockwise".
        upright = Image.new("RGB", (400, 400), "blue")
        upright.paste(Image.new("RGB", (400, 200), "red"), (0, 0))
        sideways = upright.rotate(90, expand=True)  # what the camera wrote
        exif = Image.Exif()
        exif[0x0112] = 6
        out = BytesIO()
        sideways.save(out, format="JPEG", exif=exif)
        self.post_profile(picture=SimpleUploadedFile("p.jpg", out.getvalue(), content_type="image/jpeg"))

        stored = Image.open(BytesIO(bytes(ProfilePicture.objects.get(user=self.user).jpeg))).convert("RGB")
        top, bottom = stored.getpixel((128, 20)), stored.getpixel((128, 236))
        self.assertGreater(top[0], 200)     # red on top
        self.assertGreater(bottom[2], 200)  # blue below

    def test_transparent_png_gets_a_white_background(self):
        out = BytesIO()
        Image.new("RGBA", (300, 300), (0, 0, 0, 0)).save(out, format="PNG")
        self.post_profile(picture=SimpleUploadedFile("p.png", out.getvalue(), content_type="image/png"))
        stored = Image.open(BytesIO(bytes(ProfilePicture.objects.get(user=self.user).jpeg)))
        self.assertGreater(min(stored.convert("RGB").getpixel((10, 10))), 240)

    def test_a_file_that_is_not_an_image_is_refused(self):
        page = SimpleUploadedFile("evil.jpg", b"<html><script>alert(1)</script></html>", content_type="image/jpeg")
        response = self.post_profile(picture=page)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "an image we can read")
        self.assertFalse(ProfilePicture.objects.exists())

    def test_svg_is_refused(self):
        svg = SimpleUploadedFile("a.svg", b'<svg xmlns="http://www.w3.org/2000/svg"><script>x</script></svg>',
                                 content_type="image/svg+xml")
        self.post_profile(picture=svg)
        self.assertFalse(ProfilePicture.objects.exists())

    @override_settings(PROFILE_PICTURE_MAX_UPLOAD_BYTES=1000)
    def test_an_oversized_file_is_refused_before_decoding(self):
        with mock.patch("accounts.forms.make_profile_jpeg") as decode:
            response = self.post_profile(picture=image_upload(size=(2000, 2000)))
        decode.assert_not_called()
        self.assertContains(response, "over 10 MB")

    def test_a_decompression_bomb_is_refused(self):
        # Small on disk, but it declares a canvas of 100 megapixels.
        out = BytesIO()
        Image.new("1", (10_000, 10_000)).save(out, format="PNG")
        self.post_profile(picture=SimpleUploadedFile("bomb.png", out.getvalue(), content_type="image/png"))
        self.assertFalse(ProfilePicture.objects.exists())

    def test_picture_is_served_to_members_only(self):
        self.post_profile(picture=image_upload())
        url = reverse("profile_picture", args=[self.user.pk])

        response = self.client.get(url)
        self.assertEqual(response["Content-Type"], "image/jpeg")
        self.assertIn("private", response["Cache-Control"])
        self.assertNotIn("no-store", response["Cache-Control"])

        self.client.logout()
        self.assertEqual(self.client.get(url).status_code, 302)

    def test_header_links_the_picture_with_a_version(self):
        self.post_profile(picture=image_upload())
        response = self.client.get(reverse("index"))
        self.assertRegex(response.content.decode(), rf'src="/profile/picture/{self.user.pk}/\?v=\d+"')

    def test_member_removes_their_picture(self):
        self.post_profile(picture=image_upload())
        self.post_profile(remove_picture="on")
        self.assertFalse(ProfilePicture.objects.exists())


class DeleteAccountTests(TestCase):
    def setUp(self):
        self.user = make_member()

    def sign_in_with_password(self):
        self.client.post(reverse("account_login"), {"login": "sam@example.com", "password": PASSWORD})
        # allauth counts only an explicit re-entry of the password, not the
        # original sign-in, however recent.
        self.client.post(reverse("account_reauthenticate"), {"password": PASSWORD})

    def test_needs_the_password_again_even_when_signed_in(self):
        self.client.post(reverse("account_login"), {"login": "sam@example.com", "password": PASSWORD})
        response = self.client.get(reverse("delete_account"))
        self.assertRedirects(response, f"{reverse('account_reauthenticate')}?next={reverse('delete_account')}",
                             fetch_redirect_response=False)

        response = self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_wrong_password_does_not_unlock_deletion(self):
        self.client.force_login(self.user)
        self.client.post(reverse("account_reauthenticate"), {"password": "wrong"})
        self.client.post(reverse("delete_account"))
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_deletes_everything_and_signs_out(self):
        self.sign_in_with_password()
        ProfilePicture.objects.create(user=self.user, jpeg=b"x")
        PushSubscription.objects.create(user=self.user, endpoint=FCM_ENDPOINT, p256dh="k", auth="a")

        confirm = self.client.get(reverse("delete_account"))
        self.assertContains(confirm, "can't be undone")
        response = self.client.post(reverse("delete_account"))

        self.assertRedirects(response, reverse("index"))
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertFalse(EmailAddress.objects.exists())
        self.assertFalse(ProfilePicture.objects.exists())
        self.assertFalse(PushSubscription.objects.exists())
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_the_address_can_sign_up_again_afterwards(self):
        self.sign_in_with_password()
        self.client.post(reverse("delete_account"))
        self.client.post(reverse("account_signup"), {
            "first_name": "Sam", "email": "sam@example.com", "password1": PASSWORD, "password2": PASSWORD,
        })
        self.assertTrue(User.objects.filter(email="sam@example.com").exists())


class PrivatePageCachingTests(TestCase):
    """The service worker stores pages for offline use unless they say
    no-store. Anything a signed-in member sees must say it."""

    def test_signed_in_pages_are_no_store(self):
        self.client.force_login(make_member())
        for url in (reverse("index"), reverse("profile")):
            self.assertIn("no-store", self.client.get(url)["Cache-Control"], url)

    def test_public_home_page_stays_cacheable(self):
        response = self.client.get(reverse("index"))
        self.assertFalse(response.has_header("Cache-Control"))

    def test_account_pages_are_no_store_even_signed_out(self):
        response = self.client.get(reverse("account_login"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_worker_skips_no_store_responses_and_has_an_offline_page(self):
        worker = self.client.get("/sw.js").content.decode()
        self.assertIn("no-store", worker)
        self.assertIn('const OFFLINE_URL = "/offline/"', worker)
        self.assertEqual(self.client.get(reverse("offline")).status_code, 200)


TEST_VAPID = ec.generate_private_key(ec.SECP256R1())


@override_settings(
    VAPID_PRIVATE_KEY=b64url(TEST_VAPID.private_numbers().private_value.to_bytes(32, "big")),
    VAPID_PUBLIC_KEY=b64url(TEST_VAPID.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
    VAPID_SUBJECT="mailto:admin@example.com",
)
class PushTests(TestCase):
    def setUp(self):
        self.user = make_member()
        self.client.force_login(self.user)

    def subscribe(self, endpoint=FCM_ENDPOINT, **kwargs):
        body = {"endpoint": endpoint, "keys": {"p256dh": "key", "auth": "secret"}}
        return self.client.post(reverse("push_subscribe"), json.dumps(body),
                                content_type="application/json", **kwargs)

    def test_profile_offers_notifications(self):
        response = self.client.get(reverse("profile"))
        self.assertContains(response, 'id="push_toggle"')
        self.assertContains(response, settings.VAPID_PUBLIC_KEY)

    @override_settings(VAPID_PUBLIC_KEY="", VAPID_PRIVATE_KEY="")
    def test_profile_says_so_when_push_is_not_configured(self):
        self.assertContains(self.client.get(reverse("profile")), "aren't set up on this server")
        self.assertEqual(self.subscribe().status_code, 503)

    def test_subscribing_stores_the_device(self):
        response = self.subscribe(HTTP_USER_AGENT="Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)")
        self.assertEqual(response.status_code, 201)
        subscription = PushSubscription.objects.get()
        self.assertEqual((subscription.user, subscription.endpoint), (self.user, FCM_ENDPOINT))
        self.assertEqual(subscription.device_name, "iPhone")

    def test_subscribing_twice_from_one_device_keeps_one_row(self):
        self.subscribe()
        self.subscribe()
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_a_device_handed_to_another_member_moves_to_them(self):
        self.subscribe()
        other = make_member(email="jo@example.com")
        self.client.force_login(other)
        self.subscribe()
        self.assertEqual(PushSubscription.objects.get().user, other)

    def test_only_real_push_services_are_accepted(self):
        """Otherwise a member could make the server POST to internal hosts."""
        for endpoint in ("http://db:5432/", "https://169.254.169.254/latest/meta-data",
                         "http://fcm.googleapis.com/fcm/send/x", "https://fcm.googleapis.com.evil.example/x",
                         "https://evilfcm.googleapis.com.example/"):
            self.assertEqual(self.subscribe(endpoint=endpoint).status_code, 400, endpoint)
        for endpoint in (FCM_ENDPOINT, "https://web.push.apple.com/QGx", "https://updates.push.services.mozilla.com/wpush/v2/x",
                         "https://wns2-by3p.notify.windows.com/w/?token=x"):
            self.assertTrue(push.is_allowed_endpoint(endpoint), endpoint)

    def test_subscribing_needs_sign_in_and_csrf(self):
        self.client.logout()
        self.assertEqual(self.subscribe().status_code, 302)
        csrf_client = self.client_class(enforce_csrf_checks=True)
        csrf_client.force_login(self.user)
        body = json.dumps({"endpoint": FCM_ENDPOINT, "keys": {"p256dh": "k", "auth": "a"}})
        response = csrf_client.post(reverse("push_subscribe"), body, content_type="application/json")
        self.assertEqual(response.status_code, 403)

    def test_unsubscribing_forgets_the_device_even_after_sign_out(self):
        self.subscribe()
        self.client.logout()
        response = self.client.post(reverse("push_unsubscribe"), json.dumps({"endpoint": FCM_ENDPOINT}),
                                    content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(PushSubscription.objects.exists())

    def test_send_encrypts_and_signs_for_the_push_service(self):
        """A real pywebpush call with only the HTTP POST replaced: proves the
        key format generate_vapid_keys prints is one pywebpush can sign with."""
        browser_key = ec.generate_private_key(ec.SECP256R1())
        PushSubscription.objects.create(
            user=self.user, endpoint=FCM_ENDPOINT,
            p256dh=b64url(browser_key.public_key().public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)),
            auth=b64url(os.urandom(16)),
        )
        with mock.patch("pywebpush.requests.post") as post:
            post.return_value = mock.Mock(status_code=201, text="")
            self.assertEqual(push.send_to_user(self.user, "Game on", "Thursday 8pm"), 1)

        url = post.call_args.args[0]
        headers = post.call_args.kwargs["headers"]
        self.assertEqual(url, FCM_ENDPOINT)
        self.assertTrue(headers["Authorization"].startswith("vapid t="))
        self.assertEqual(headers["content-encoding"], "aes128gcm")
        # Encrypted: the text is not in the body.
        self.assertNotIn(b"Game on", post.call_args.kwargs["data"])

    def test_a_gone_device_is_forgotten(self):
        PushSubscription.objects.create(user=self.user, endpoint=FCM_ENDPOINT, p256dh="k", auth="a")
        gone = WebPushException("Gone", response=mock.Mock(status_code=410))
        with mock.patch("accounts.push.webpush", side_effect=gone):
            self.assertEqual(push.send_to_user(self.user, "t", "b"), 0)
        self.assertFalse(PushSubscription.objects.exists())

    def test_a_temporary_failure_keeps_the_device(self):
        PushSubscription.objects.create(user=self.user, endpoint=FCM_ENDPOINT, p256dh="k", auth="a")
        busy = WebPushException("Busy", response=mock.Mock(status_code=503))
        with mock.patch("accounts.push.webpush", side_effect=busy):
            push.send_to_user(self.user, "t", "b")
        self.assertTrue(PushSubscription.objects.exists())

    def test_test_notification_button(self):
        PushSubscription.objects.create(user=self.user, endpoint=FCM_ENDPOINT, p256dh="k", auth="a")
        with mock.patch("accounts.push.webpush") as webpush:
            response = self.client.post(reverse("push_test"), follow=True)
        payload = json.loads(webpush.call_args.kwargs["data"])
        self.assertEqual(payload["url"], "/profile/")
        self.assertContains(response, "Test notification sent to 1 device.")

    def test_worker_shows_notifications_and_opens_our_pages(self):
        worker = self.client.get("/sw.js").content.decode()
        self.assertIn('addEventListener("push"', worker)
        self.assertIn('addEventListener("notificationclick"', worker)


class GenerateVapidKeysTests(TestCase):
    def test_prints_a_matching_pair_pywebpush_can_load(self):
        out = StringIO()
        call_command("generate_vapid_keys", stdout=out, stderr=StringIO())
        lines = dict(line.split("=", 1) for line in out.getvalue().split())

        vapid = Vapid01.from_string(lines["VAPID_PRIVATE_KEY"])
        public = vapid.public_key.public_bytes(
            serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
        self.assertEqual(b64url(public), lines["VAPID_PUBLIC_KEY"])
