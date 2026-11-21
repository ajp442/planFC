"""Recording payments: who may, what is kept, and what is refused.
docs/ADMIN_GUIDE.md describes the same behaviour for superusers."""

import json
from datetime import timedelta
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests import make_member
from accounts.tests_members import make_admin, make_superuser

from .models import Payment

URL = reverse("payments")


def entry(**overrides):
    data = {
        "payer_name": "Walk In",
        "member": "",
        "amount": "12.00",
        "paid_on": timezone.localdate().isoformat(),
        "method": "venmo",
        "note": "",
    }
    data.update(overrides)
    return data


class AccessTests(TestCase):
    def test_signed_out_visitors_go_to_sign_in(self):
        response = self.client.get(URL)
        self.assertRedirects(response, f"{reverse('account_login')}?next={URL}", fetch_redirect_response=False)

    def test_members_and_admins_are_refused(self):
        for user in (make_member(), make_admin()):
            self.client.force_login(user)
            self.assertEqual(self.client.get(URL).status_code, 403)
            self.assertEqual(self.client.post(URL, entry()).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_deactivated_superuser_is_refused(self):
        root = make_superuser()
        self.client.force_login(root)
        root.is_active = False
        root.save(update_fields=["is_active"])
        # A deactivated user's session no longer authenticates.
        self.assertNotEqual(self.client.get(URL).status_code, 200)

    def test_superuser_needs_no_two_factor_code(self):
        # Unlike Database admin: no authenticator app, no recent code.
        self.client.force_login(make_superuser())
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Record a payment")

    def test_page_is_never_cached(self):
        self.client.force_login(make_superuser())
        self.assertIn("no-store", self.client.get(URL)["Cache-Control"])


class MenuTests(TestCase):
    def test_only_superusers_see_payments_in_the_menu(self):
        self.client.force_login(make_admin())
        self.assertNotContains(self.client.get(reverse("index")), URL)
        self.client.force_login(make_superuser())
        self.assertContains(self.client.get(reverse("index")), f'href="{URL}"')


class RecordTests(TestCase):
    def setUp(self):
        self.root = make_superuser()
        self.member = make_member(email="ann@example.com", first_name="Ann", last_name="Smith")
        self.client.force_login(self.root)

    def test_date_defaults_to_today(self):
        response = self.client.get(URL)
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')

    def test_page_lists_every_member_for_suggestions(self):
        response = self.client.get(URL)
        script = response.content.decode().split('id="payment_members" type="application/json">')[1]
        members = json.loads(script.split("</script>")[0])
        self.assertIn({"id": self.member.pk, "name": "Ann Smith", "email": "ann@example.com", "active": True}, members)

    def test_records_a_payment_linked_to_a_member(self):
        response = self.client.post(URL, entry(
            payer_name="ann", member=str(self.member.pk), amount="24.50",
            method="zelle", note="  Two games  ",
        ))
        self.assertRedirects(response, URL)
        payment = Payment.objects.get()
        self.assertEqual(payment.member, self.member)
        # The account's name, not the fragment that was typed.
        self.assertEqual(payment.payer_name, "Ann Smith")
        self.assertEqual(payment.amount, Decimal("24.50"))
        self.assertEqual(payment.method, Payment.Method.ZELLE)
        self.assertEqual(payment.note, "Two games")
        self.assertEqual(payment.paid_on, timezone.localdate())
        self.assertEqual(payment.recorded_by, self.root)
        self.assertEqual(payment.recorded_by_label, "Root User <root@example.com>")
        self.assertIsNotNone(payment.created_at)

    def test_records_a_payment_from_someone_without_an_account(self):
        self.client.post(URL, entry(payer_name="  Bob   the  Guest ", method="cash"))
        payment = Payment.objects.get()
        self.assertIsNone(payment.member)
        self.assertEqual(payment.payer_name, "Bob the Guest")
        self.assertEqual(payment.method, "cash")

    def test_every_method_is_accepted(self):
        for method in ("paypal", "venmo", "zelle", "cash", "other"):
            self.client.post(URL, entry(method=method))
        self.assertEqual(Payment.objects.count(), 5)

    def test_an_earlier_date_is_kept(self):
        earlier = timezone.localdate() - timedelta(days=10)
        self.client.post(URL, entry(paid_on=earlier.isoformat()))
        self.assertEqual(Payment.objects.get().paid_on, earlier)

    def test_success_message_and_listing(self):
        response = self.client.post(URL, entry(payer_name="Bob Guest", amount="7"), follow=True)
        self.assertContains(response, "Recorded $7.00 from Bob Guest (Venmo,")
        self.assertContains(response, "No account")
        self.assertContains(response, "$7.00")

    def test_refuses_bad_entries(self):
        cases = {
            "no name": entry(payer_name="   "),
            "zero": entry(amount="0"),
            "negative": entry(amount="-5"),
            "fractions of a cent": entry(amount="1.005"),
            "not a number": entry(amount="ten"),
            "too large": entry(amount="1000000"),
            "future date": entry(paid_on=(timezone.localdate() + timedelta(days=1)).isoformat()),
            "no method": entry(method=""),
            "unknown method": entry(method="bitcoin"),
            "deleted account": entry(member="999999"),
            "member not a number": entry(member="abc"),
        }
        for name, data in cases.items():
            with self.subTest(name):
                response = self.client.post(URL, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertFalse(Payment.objects.exists())

    def test_the_database_refuses_a_non_positive_amount(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                payer_name="X", amount=Decimal("0"), paid_on=timezone.localdate(),
                method="cash", recorded_by_label="test",
            )

    def test_payment_outlives_the_members_account(self):
        self.client.post(URL, entry(member=str(self.member.pk)))
        self.member.delete()
        payment = Payment.objects.get()
        self.assertIsNone(payment.member)
        self.assertEqual(payment.payer_name, "Ann Smith")
