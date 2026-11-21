"""Recording payments: who may, what is kept, and what is refused.
docs/ADMIN_GUIDE.md describes the same behaviour for superusers."""

import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts.tests import make_member
from accounts.tests_members import make_admin, make_superuser

from .models import Payment, PaymentChange

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

    def test_members_are_refused(self):
        self.client.force_login(make_member())
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.get(reverse("payment_changes")).status_code, 403)
        self.assertEqual(self.client.post(URL, entry()).status_code, 403)
        self.assertFalse(Payment.objects.exists())

    def test_admins_can_look_but_not_record(self):
        self.client.force_login(make_admin())
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Record a payment")
        self.assertNotContains(response, 'id="payment_members"')
        self.assertEqual(self.client.post(URL, entry()).status_code, 403)
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(self.client.get(reverse("payment_changes")).status_code, 200)

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
    def test_members_see_no_payments_menu(self):
        self.client.force_login(make_member())
        self.assertNotContains(self.client.get(reverse("index")), 'id="payments_menu"')

    def test_admins_see_payments_but_not_recording(self):
        self.client.force_login(make_admin())
        response = self.client.get(reverse("index"))
        self.assertContains(response, "All payments")
        self.assertNotContains(response, "Record a payment")

    def test_superusers_see_recording(self):
        self.client.force_login(make_superuser())
        self.assertContains(self.client.get(reverse("index")), "Record a payment")


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


class HistoryTests(TestCase):
    """Superusers can change any detail of a payment; the history of what was
    recorded and changed, and when, can't be changed by anyone."""

    def setUp(self):
        self.root = make_superuser()
        self.ann = make_member(email="ann@example.com", first_name="Ann", last_name="Smith")
        self.client.force_login(self.root)
        self.client.post(URL, entry(payer_name="Walk In", amount="12", method="cash", note="first game"))
        self.payment = Payment.objects.get()
        self.detail = reverse("payment_detail", args=[self.payment.pk])

    def edit(self, **overrides):
        data = entry(
            payer_name=self.payment.payer_name, amount=str(self.payment.amount),
            paid_on=self.payment.paid_on.isoformat(), method=self.payment.method, note=self.payment.note,
        )
        data.update(overrides)
        return self.client.post(self.detail, data)

    def test_recording_writes_a_history_entry(self):
        change = PaymentChange.objects.get()
        self.assertEqual(change.payment_id, self.payment.pk)
        self.assertEqual(change.action, PaymentChange.Action.CREATED)
        self.assertEqual(change.actor, self.root)
        self.assertEqual(change.values["amount"], "$12.00")
        self.assertEqual(change.values["method"], "Cash")
        self.assertEqual(change.values["note"], "first game")

    def test_superuser_can_change_every_field(self):
        earlier = timezone.localdate() - timedelta(days=3)
        response = self.edit(
            payer_name="ann", member=str(self.ann.pk), amount="15.50",
            paid_on=earlier.isoformat(), method="paypal", note="two games", reason="Typo",
        )
        self.assertRedirects(response, self.detail)
        self.payment.refresh_from_db()
        self.assertEqual(
            (self.payment.member, self.payment.payer_name, self.payment.amount,
             self.payment.paid_on, self.payment.method, self.payment.note),
            (self.ann, "Ann Smith", Decimal("15.50"), earlier, "paypal", "two games"),
        )
        change = PaymentChange.objects.get(action=PaymentChange.Action.EDITED)
        self.assertEqual(change.reason, "Typo")
        self.assertEqual(change.values["amount"], ["$12.00", "$15.50"])
        self.assertEqual(change.values["payer_name"], ["Walk In", "Ann Smith"])
        self.assertEqual(change.values["member"], ["", "Ann Smith <ann@example.com>"])
        self.assertEqual(change.values["method"], ["Cash", "PayPal"])
        self.assertEqual(set(change.values), {"payer_name", "member", "amount", "paid_on", "method", "note"})
        # The original entry is untouched.
        created = PaymentChange.objects.get(action=PaymentChange.Action.CREATED)
        self.assertEqual(created.values["amount"], "$12.00")

    def test_recording_time_and_recorder_cant_be_edited(self):
        created_at = self.payment.created_at
        self.edit(amount="20", created_at="2000-01-01T00:00", recorded_by_label="Someone else")
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("20.00"))
        self.assertEqual(self.payment.created_at, created_at)
        self.assertEqual(self.payment.recorded_by_label, "Root User <root@example.com>")

    def test_saving_without_changes_records_nothing(self):
        self.edit()
        self.assertFalse(PaymentChange.objects.filter(action=PaymentChange.Action.EDITED).exists())

    def test_edit_is_validated_like_recording(self):
        response = self.edit(amount="-1")
        self.assertEqual(response.status_code, 200)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("12.00"))
        self.assertEqual(PaymentChange.objects.count(), 1)

    def test_admins_see_the_payment_and_its_history_but_cant_edit(self):
        self.client.force_login(make_admin())
        response = self.client.get(self.detail)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "History")
        self.assertNotContains(response, "Edit this payment")
        self.assertEqual(self.edit(amount="1").status_code, 403)
        self.payment.refresh_from_db()
        self.assertEqual(self.payment.amount, Decimal("12.00"))

    def test_history_pages_show_the_changes(self):
        self.edit(amount="15", reason="Paid for a friend too")
        for url in (self.detail, reverse("payment_changes")):
            response = self.client.get(url)
            self.assertContains(response, "$12.00 → $15.00")
            self.assertContains(response, "Paid for a friend too")
        self.assertContains(self.client.get(URL), "Edited")

    def test_the_app_refuses_to_change_history(self):
        change = PaymentChange.objects.get()
        change.reason = "rewritten"
        with self.assertRaises(ValueError):
            change.save()
        with self.assertRaises(ValueError):
            change.delete()

    def test_the_database_refuses_to_change_history(self):
        # Even a query that bypasses the model, as Database admin or a
        # hand-written UPDATE would.
        for statement in (
            "UPDATE payments_paymentchange SET reason = 'rewritten'",
            "DELETE FROM payments_paymentchange",
        ):
            with self.subTest(statement), self.assertRaises(DatabaseError), transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(statement)
        with self.assertRaises(DatabaseError), transaction.atomic():
            PaymentChange.objects.update(reason="rewritten")
        self.assertEqual(PaymentChange.objects.get().reason, "")

    def test_history_outlives_the_people_in_it(self):
        self.edit(member=str(self.ann.pk))
        self.ann.delete()
        self.root.delete()
        self.assertEqual(PaymentChange.objects.count(), 2)
        self.assertEqual(PaymentChange.objects.get(action="created").actor_label, "Root User <root@example.com>")

    def test_deleting_in_database_admin_is_recorded(self):
        request = RequestFactory().post("/")
        request.user = self.root
        payment_id = self.payment.pk
        admin.site._registry[Payment].delete_model(request, self.payment)
        self.assertFalse(Payment.objects.exists())
        deleted = PaymentChange.objects.get(action=PaymentChange.Action.DELETED)
        self.assertEqual(deleted.payment_id, payment_id)
        self.assertEqual(deleted.values["amount"], "$12.00")
        self.assertEqual(PaymentChange.objects.count(), 2)
        # The history page still lists it, unlinked.
        self.assertContains(self.client.get(reverse("payment_changes")), f"payment #{payment_id}")

    def test_database_admin_cant_edit_payments_or_history(self):
        request = RequestFactory().get("/")
        request.user = self.root
        self.assertFalse(admin.site._registry[Payment].has_change_permission(request, self.payment))
        history_admin = admin.site._registry[PaymentChange]
        change = PaymentChange.objects.get()
        self.assertFalse(history_admin.has_change_permission(request, change))
        self.assertFalse(history_admin.has_delete_permission(request, change))
