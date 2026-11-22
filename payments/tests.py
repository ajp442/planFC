"""Recording payments: who may, what is kept, and what is refused; linking an
unconfirmed payer to their real account later. docs/ADMIN_GUIDE.md describes
the same behaviour for superusers and admins."""

from datetime import timedelta
from decimal import Decimal

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.db.models import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from accounts import members
from accounts.models import AdminAction, UnconfirmedAccount
from accounts.tests import make_member
from accounts.tests_members import make_admin, make_superuser

from .models import Payment, PaymentChange, PaymentMethod
from .wizard import SESSION_KEY

User = get_user_model()

URL = reverse("payments")
START = reverse("payment_new")
WHO = reverse("payment_new_who")
AMOUNT = reverse("payment_new_amount")
DETAILS = reverse("payment_new_details")
REVIEW = reverse("payment_new_review")
STEP_URLS = [START, WHO, AMOUNT, DETAILS, REVIEW]


def method(name):
    """The methods 0003_payment_method created: PayPal, Venmo, Zelle, Cash, Other."""
    return PaymentMethod.objects.get(name=name)


def record(client, member=None, new_name="", amount="12.00", method_name="Venmo", paid_on=None, note=""):
    """Goes through every step, as a superuser would, and records it."""
    client.get(START)
    if member is not None:
        client.post(WHO, {"member": str(member.pk)})
    else:
        client.post(WHO, {"new_name": new_name})
    client.post(AMOUNT, {"amount": amount})
    client.post(DETAILS, {
        "method": str(method(method_name).pk),
        "paid_on": (paid_on or timezone.localdate()).isoformat(),
    })
    return client.post(REVIEW, {"note": note})


def make_unconfirmed(name="Bob Guest", by=None):
    request = RequestFactory().post("/")
    request.user = by or make_superuser(email="maker@example.com")
    return members.create_unconfirmed_member(request, name)


class AccessTests(TestCase):
    def test_signed_out_visitors_go_to_sign_in(self):
        response = self.client.get(URL)
        self.assertRedirects(response, f"{reverse('account_login')}?next={URL}", fetch_redirect_response=False)
        response = self.client.get(WHO)
        self.assertRedirects(response, f"{reverse('account_login')}?next={WHO}", fetch_redirect_response=False)

    def test_members_are_refused(self):
        self.client.force_login(make_member())
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.get(reverse("payment_changes")).status_code, 403)
        for url in STEP_URLS:
            self.assertEqual(self.client.get(url).status_code, 403, url)
            self.assertEqual(self.client.post(url, {"amount": "5"}).status_code, 403, url)
        self.assertFalse(Payment.objects.exists())

    def test_admins_can_look_but_not_record(self):
        self.client.force_login(make_admin())
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Record a payment")
        for url in STEP_URLS:
            self.assertEqual(self.client.get(url).status_code, 403, url)
        self.assertEqual(self.client.post(REVIEW, {"note": ""}).status_code, 403)
        self.assertFalse(Payment.objects.exists())
        self.assertEqual(self.client.get(reverse("payment_changes")).status_code, 200)

    def test_deactivated_superuser_is_refused(self):
        root = make_superuser()
        self.client.force_login(root)
        root.is_active = False
        root.save(update_fields=["is_active"])
        # A deactivated user's session no longer authenticates.
        self.assertNotEqual(self.client.get(WHO).status_code, 200)

    def test_superuser_needs_no_two_factor_code(self):
        # Unlike Database admin: no authenticator app, no recent code.
        self.client.force_login(make_superuser())
        self.assertContains(self.client.get(URL), "Record a payment")
        self.assertEqual(self.client.get(WHO).status_code, 200)

    def test_pages_are_never_cached(self):
        self.client.force_login(make_superuser())
        self.assertIn("no-store", self.client.get(URL)["Cache-Control"])
        self.assertIn("no-store", self.client.get(WHO)["Cache-Control"])


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
        self.assertContains(self.client.get(reverse("index")), f'<a href="{START}">Record a payment</a>', html=True)


class WizardTestCase(TestCase):
    def setUp(self):
        self.root = make_superuser()
        self.ann = make_member(email="ann@example.com", first_name="Ann", last_name="Smith")
        self.client.force_login(self.root)
        self.client.get(START)

    def draft(self):
        return self.client.session.get(SESSION_KEY, {})

    def fill_all(self):
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.client.post(AMOUNT, {"amount": "20"})
        self.client.post(DETAILS, {"method": str(method("Zelle").pk), "paid_on": timezone.localdate().isoformat()})


class StepTests(WizardTestCase):
    def test_start_always_begins_a_fresh_payment(self):
        self.fill_all()
        response = self.client.get(START)
        self.assertRedirects(response, WHO)
        self.assertEqual(self.draft(), {})

    def test_who_lists_everyone_with_a_focused_search_box(self):
        bob = make_unconfirmed("Bob Guest", by=self.root)
        gone = make_member(email="gone@example.com", first_name="Gone", last_name="Away")
        gone.is_active = False
        gone.save()
        response = self.client.get(WHO)
        self.assertContains(response, 'id="who_search"')
        self.assertContains(response, "autofocus")
        for user in (self.root, self.ann, bob, gone):
            self.assertContains(response, f'name="member" value="{user.pk}"')
        self.assertContains(response, "pill-unconfirmed_account", count=1)
        self.assertContains(response, "Deactivated")
        self.assertContains(response, "4 members")

    def test_who_search_works_without_javascript(self):
        response = self.client.get(WHO, {"q": "smi ann"})
        self.assertContains(response, f'name="member" value="{self.ann.pk}"')
        self.assertNotContains(response, f'name="member" value="{self.root.pk}"')
        # The typed name is ready to be added as a new member.
        self.assertContains(response, 'name="new_name" value="smi ann"')

    def test_every_page_shows_the_steps_with_the_current_one_marked(self):
        self.fill_all()
        for url, title in ((WHO, "Who paid"), (AMOUNT, "Amount"), (DETAILS, "Method &amp; date"), (REVIEW, "Review")):
            response = self.client.get(url)
            content = response.content.decode()
            self.assertEqual(content.count('class="step step-current"'), 1, url)
            current = content.split('class="step step-current"')[1].split("</li>")[0]
            self.assertIn(title, current, url)
            self.assertIn('aria-current="step"', current, url)
            # Every other step was already reached, so each is a link back.
            self.assertEqual(content.count('class="step step-open"'), 3, url)

    def test_later_steps_are_locked_until_earlier_ones_are_filled_in(self):
        response = self.client.get(WHO)
        self.assertContains(response, 'class="step step-locked"', count=3)
        for url in (AMOUNT, DETAILS, REVIEW):
            self.assertRedirects(self.client.get(url), WHO, msg_prefix=url)
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.assertRedirects(self.client.get(REVIEW), AMOUNT)

    def test_picking_someone_moves_straight_on_to_the_amount(self):
        response = self.client.post(WHO, {"member": str(self.ann.pk)})
        self.assertRedirects(response, AMOUNT)
        response = self.client.get(AMOUNT)
        self.assertContains(response, "<h1>Ann Smith</h1>", html=True)
        # The steps show who was picked.
        self.assertContains(response, '<span class="step-summary">Ann Smith</span>', html=True)

    def test_amount_then_method_and_date_then_review(self):
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.assertRedirects(self.client.post(AMOUNT, {"amount": "7"}), DETAILS)
        response = self.client.get(DETAILS)
        self.assertContains(response, f'value="{timezone.localdate().isoformat()}"')
        self.assertContains(response, "<select")
        response = self.client.post(DETAILS, {"method": str(method("Cash").pk), "paid_on": timezone.localdate().isoformat()})
        self.assertRedirects(response, REVIEW)
        response = self.client.get(REVIEW)
        self.assertContains(response, "Ann Smith")
        self.assertContains(response, "$7.00")
        self.assertContains(response, "Cash")
        self.assertContains(response, 'name="note"')

    def test_refuses_bad_amounts(self):
        self.client.post(WHO, {"member": str(self.ann.pk)})
        for amount in ("", "0", "-5", "1.005", "ten", "1000000"):
            with self.subTest(amount):
                response = self.client.post(AMOUNT, {"amount": amount})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertNotIn("amount", self.draft())

    def test_refuses_bad_details(self):
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.client.post(AMOUNT, {"amount": "5"})
        retired = PaymentMethod.objects.create(name="Bitcoin", active=False)
        today = timezone.localdate()
        cases = {
            "no method": {"method": "", "paid_on": today.isoformat()},
            "unknown method": {"method": "999999", "paid_on": today.isoformat()},
            "retired method": {"method": str(retired.pk), "paid_on": today.isoformat()},
            "future date": {"method": str(method("Cash").pk), "paid_on": (today + timedelta(days=1)).isoformat()},
            "no date": {"method": str(method("Cash").pk), "paid_on": ""},
        }
        for name, data in cases.items():
            with self.subTest(name):
                response = self.client.post(DETAILS, data)
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["form"].errors)
        self.assertNotIn("method_id", self.draft())

    def test_who_refuses_a_missing_account_or_an_empty_name(self):
        for data in ({"member": "999999"}, {"member": "abc"}, {"new_name": "   "}, {}):
            with self.subTest(data):
                self.assertRedirects(self.client.post(WHO, data), WHO)
        self.assertEqual(self.draft(), {})

    def test_going_back_keeps_everything_and_returns_to_review(self):
        self.fill_all()
        self.client.post(REVIEW, {"note": "two games", "goto": "amount"})
        response = self.client.get(AMOUNT)
        self.assertContains(response, 'value="20.00"')
        # Everything else is filled in, so a correction goes back to Review.
        self.assertRedirects(self.client.post(AMOUNT, {"amount": "25"}), REVIEW)
        response = self.client.get(REVIEW)
        self.assertContains(response, "$25.00")
        self.assertContains(response, "Zelle")
        self.assertContains(response, "two games")
        # And the person picked is marked when coming back to the first step.
        self.assertContains(self.client.get(WHO), "Chosen")

    def test_leaving_through_the_steps_keeps_a_valid_value_and_drops_a_bad_one(self):
        self.fill_all()
        self.assertRedirects(self.client.post(AMOUNT, {"amount": "30", "goto": "who"}), WHO)
        self.assertEqual(self.draft()["amount"], "30.00")
        self.assertRedirects(self.client.post(AMOUNT, {"amount": "-1", "goto": "details"}), DETAILS)
        self.assertEqual(self.draft()["amount"], "30.00")

    def test_a_locked_step_cant_be_jumped_to(self):
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.assertRedirects(self.client.post(AMOUNT, {"amount": "", "goto": "review"}), AMOUNT)


class RecordTests(WizardTestCase):
    def test_records_a_payment_linked_to_a_member(self):
        response = record(self.client, member=self.ann, amount="24.50", method_name="Zelle", note="  Two games  ")
        self.assertRedirects(response, URL)
        payment = Payment.objects.get()
        self.assertEqual(payment.member, self.ann)
        self.assertEqual(payment.payer_name, "Ann Smith")
        self.assertEqual(payment.amount, Decimal("24.50"))
        self.assertEqual(payment.method, method("Zelle"))
        self.assertEqual(payment.note, "Two games")
        self.assertEqual(payment.paid_on, timezone.localdate())
        self.assertEqual(payment.recorded_by, self.root)
        self.assertEqual(payment.recorded_by_label, "Root User <root@example.com>")
        self.assertIsNotNone(payment.created_at)
        # Done: the next payment starts from scratch.
        self.assertEqual(self.draft(), {})

    def test_records_a_payment_from_someone_without_an_account(self):
        self.assertEqual(self.client.post(WHO, {"new_name": "  Bob   the  Guest "}).status_code, 302)
        # Nobody is added until the payment is recorded.
        self.assertFalse(UnconfirmedAccount.objects.exists())
        self.assertContains(self.client.get(AMOUNT), "<h1>Bob the Guest</h1>", html=True)
        self.client.post(AMOUNT, {"amount": "12"})
        self.client.post(DETAILS, {"method": str(method("Cash").pk), "paid_on": timezone.localdate().isoformat()})
        self.assertContains(self.client.get(REVIEW), "New, unconfirmed")
        self.client.post(REVIEW, {"note": ""})

        payment = Payment.objects.get()
        bob = payment.member
        self.assertEqual(payment.payer_name, "Bob the Guest")
        self.assertEqual((bob.first_name, bob.last_name, bob.email), ("Bob", "the Guest", ""))
        self.assertTrue(members.is_unconfirmed_account(bob))
        # Nobody can sign in to it.
        self.assertFalse(bob.has_usable_password())
        self.assertEqual(UnconfirmedAccount.objects.get().created_by, self.root)
        self.assertTrue(AdminAction.objects.filter(target=bob, action=AdminAction.Action.ADDED_UNCONFIRMED).exists())
        self.assertEqual(PaymentChange.objects.get().values["member"], "Bob the Guest")

        # They are in every list from now on.
        self.client.get(START)
        self.assertContains(self.client.get(WHO), f'name="member" value="{bob.pk}"')
        self.assertContains(self.client.get(reverse("member_list")), "Unconfirmed")

    def test_an_abandoned_payment_leaves_nothing_behind(self):
        self.client.post(WHO, {"new_name": "Walk In"})
        self.client.post(AMOUNT, {"amount": "12"})
        self.client.get(START)
        self.assertEqual(User.objects.count(), 2)
        self.assertFalse(Payment.objects.exists())

    def test_recording_twice_records_once(self):
        record(self.client, member=self.ann)
        response = self.client.post(REVIEW, {"note": ""})
        self.assertRedirects(response, WHO)
        self.assertEqual(Payment.objects.count(), 1)

    def test_an_account_deleted_meanwhile_sends_you_back_to_pick_again(self):
        self.fill_all()
        self.ann.delete()
        self.assertRedirects(self.client.post(REVIEW, {"note": ""}), WHO)
        self.assertFalse(Payment.objects.exists())

    def test_success_message_and_listing(self):
        response = record(self.client, member=self.ann, amount="7")
        self.assertContains(self.client.get(response.url), "Recorded $7.00 from Ann Smith (Venmo,")
        self.assertContains(self.client.get(URL), "$7.00")

    def test_an_earlier_date_is_kept(self):
        earlier = timezone.localdate() - timedelta(days=10)
        record(self.client, member=self.ann, paid_on=earlier)
        self.assertEqual(Payment.objects.get().paid_on, earlier)

    def test_the_database_refuses_a_non_positive_amount(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Payment.objects.create(
                payer_name="X", amount=Decimal("0"), paid_on=timezone.localdate(),
                method=method("Cash"), recorded_by_label="test",
            )

    def test_payment_outlives_the_members_account(self):
        record(self.client, member=self.ann)
        self.ann.delete()
        payment = Payment.objects.get()
        self.assertIsNone(payment.member)
        self.assertEqual(payment.payer_name, "Ann Smith")


class MethodTests(WizardTestCase):
    """Methods are rows superusers edit in Database admin."""

    def test_the_old_methods_exist_in_order(self):
        self.assertEqual(
            list(PaymentMethod.objects.values_list("name", flat=True)),
            ["PayPal", "Venmo", "Zelle", "Cash", "Other"],
        )

    def test_only_active_methods_are_offered(self):
        PaymentMethod.objects.create(name="Check", sort_order=1)
        PaymentMethod.objects.filter(name="PayPal").update(active=False)
        self.client.post(WHO, {"member": str(self.ann.pk)})
        self.client.post(AMOUNT, {"amount": "5"})
        response = self.client.get(DETAILS)
        self.assertContains(response, "Check")
        self.assertNotContains(response, "PayPal")

    def test_a_method_in_use_cant_be_deleted_but_can_be_retired(self):
        record(self.client, member=self.ann, method_name="Cash")
        cash = method("Cash")
        with self.assertRaises(ProtectedError):
            cash.delete()
        cash.active = False
        cash.save()
        payment = Payment.objects.get()
        detail = reverse("payment_detail", args=[payment.pk])
        # Editing an old payment still offers, and keeps, its retired method.
        self.assertContains(self.client.get(detail), "Cash")
        self.client.post(detail, {
            "payer_name": "Ann Smith", "member": str(self.ann.pk), "amount": "13",
            "paid_on": payment.paid_on.isoformat(), "method": str(cash.pk), "note": "",
        })
        payment.refresh_from_db()
        self.assertEqual((payment.amount, payment.method), (Decimal("13.00"), cash))

    def test_database_admin_can_edit_methods(self):
        request = RequestFactory().get("/")
        request.user = self.root
        method_admin = admin.site._registry[PaymentMethod]
        self.assertTrue(method_admin.has_add_permission(request))
        self.assertTrue(method_admin.has_change_permission(request, method("Cash")))


class LinkTests(TestCase):
    """An unconfirmed account handed over to the person's real one."""

    def setUp(self):
        self.root = make_superuser()
        self.admin = make_admin()
        self.client.force_login(self.root)
        self.bob = make_unconfirmed("Bob Guest", by=self.root)
        record(self.client, member=self.bob, amount="10", method_name="Cash")
        record(self.client, member=self.bob, amount="15", method_name="Venmo")
        self.real = make_member(email="bguest@example.com", first_name="Bob", last_name="Guest")
        self.link_url = reverse("member_link", args=[self.bob.pk])

    def test_member_page_offers_linking_and_no_sign_in_actions(self):
        response = self.client.get(reverse("member_detail", args=[self.bob.pk]))
        self.assertContains(response, "Unconfirmed account")
        self.assertContains(response, self.link_url)
        self.assertContains(response, "2 so far")
        self.assertNotContains(response, "Make an admin")
        self.assertNotContains(response, "Send the invitation again")

    def test_unconfirmed_accounts_cant_be_invited_or_made_admin(self):
        response = self.client.post(reverse("member_action", args=[self.bob.pk, "resend-invite"]), follow=True)
        self.assertContains(response, "no invitation to send")
        self.client.force_login(self.admin)
        self.client.get(reverse("member_role", args=[self.bob.pk]))
        self.bob.refresh_from_db()
        self.assertFalse(self.bob.is_staff)

    def test_link_page_lists_real_accounts_with_same_name_first(self):
        other = make_unconfirmed("Other Guest", by=self.root)
        response = self.client.get(self.link_url)
        self.assertContains(response, "Same name")
        self.assertContains(response, f"?into={self.real.pk}", count=2)
        self.assertNotContains(response, f"?into={other.pk}")
        self.assertNotContains(response, f"?into={self.bob.pk}")

    def test_linking_moves_the_payments_and_removes_the_unconfirmed_account(self):
        response = self.client.get(self.link_url, {"into": self.real.pk})
        self.assertContains(response, "Link to Bob Guest?")
        self.assertContains(response, "2 will move")

        response = self.client.post(self.link_url, {"into": self.real.pk}, follow=True)
        self.assertRedirects(response, reverse("member_detail", args=[self.real.pk]))
        self.assertContains(response, "2 payments moved over")

        self.assertFalse(User.objects.filter(pk=self.bob.pk).exists())
        self.assertFalse(UnconfirmedAccount.objects.exists())
        self.assertEqual(Payment.objects.filter(member=self.real).count(), 2)
        edits = PaymentChange.objects.filter(action=PaymentChange.Action.EDITED)
        self.assertEqual(edits.count(), 2)
        for edit in edits:
            self.assertEqual(edit.values["member"], ["Bob Guest", "Bob Guest <bguest@example.com>"])
            self.assertIn("linked to Bob Guest <bguest@example.com>", edit.reason)
            self.assertEqual(edit.actor, self.root)
        action = AdminAction.objects.get(action=AdminAction.Action.LINKED)
        self.assertEqual(action.target, self.real)
        self.assertEqual(action.detail, "From “Bob Guest”: 2 payments moved")

    def test_admins_can_link_too(self):
        self.client.force_login(self.admin)
        self.client.post(self.link_url, {"into": self.real.pk})
        self.assertEqual(Payment.objects.filter(member=self.real).count(), 2)

    def test_members_cant_link(self):
        self.client.force_login(self.real)
        self.assertEqual(self.client.post(self.link_url, {"into": self.real.pk}).status_code, 403)
        self.assertEqual(Payment.objects.filter(member=self.bob).count(), 2)

    def test_refuses_to_link_the_wrong_way_round(self):
        other = make_unconfirmed("Other Guest", by=self.root)
        cases = [
            (self.link_url, {"into": other.pk}),  # into another unconfirmed account
            (self.link_url, {"into": self.bob.pk}),  # into itself
            (self.link_url, {"into": "999999"}),  # into nobody
            (reverse("member_link", args=[self.real.pk]), {"into": self.root.pk}),  # a real account
        ]
        for url, data in cases:
            with self.subTest(data):
                self.client.post(url, data)
        self.assertEqual(Payment.objects.filter(member=self.bob).count(), 2)
        self.assertTrue(User.objects.filter(pk=self.real.pk).exists())
        self.assertFalse(AdminAction.objects.filter(action=AdminAction.Action.LINKED).exists())


class HistoryTests(TestCase):
    """Superusers can change any detail of a payment; the history of what was
    recorded and changed, and when, can't be changed by anyone."""

    def setUp(self):
        self.root = make_superuser()
        self.ann = make_member(email="ann@example.com", first_name="Ann", last_name="Smith")
        self.walk_in = make_member(email="walk@example.com", first_name="Walk", last_name="In")
        self.client.force_login(self.root)
        record(self.client, member=self.walk_in, amount="12", method_name="Cash", note="first game")
        self.payment = Payment.objects.get()
        self.detail = reverse("payment_detail", args=[self.payment.pk])

    def edit(self, **overrides):
        data = {
            "payer_name": self.payment.payer_name,
            "member": str(self.payment.member_id or ""),
            "amount": str(self.payment.amount),
            "paid_on": self.payment.paid_on.isoformat(),
            "method": str(self.payment.method_id),
            "note": self.payment.note,
        }
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
            paid_on=earlier.isoformat(), method=str(method("PayPal").pk), note="two games", reason="Typo",
        )
        self.assertRedirects(response, self.detail)
        self.payment.refresh_from_db()
        self.assertEqual(
            (self.payment.member, self.payment.payer_name, self.payment.amount,
             self.payment.paid_on, self.payment.method.name, self.payment.note),
            (self.ann, "Ann Smith", Decimal("15.50"), earlier, "PayPal", "two games"),
        )
        change = PaymentChange.objects.get(action=PaymentChange.Action.EDITED)
        self.assertEqual(change.reason, "Typo")
        self.assertEqual(change.values["amount"], ["$12.00", "$15.50"])
        self.assertEqual(change.values["payer_name"], ["Walk In", "Ann Smith"])
        self.assertEqual(change.values["member"], ["Walk In <walk@example.com>", "Ann Smith <ann@example.com>"])
        self.assertEqual(change.values["method"], ["Cash", "PayPal"])
        self.assertEqual(set(change.values), {"payer_name", "member", "amount", "paid_on", "method", "note"})
        # The original entry is untouched.
        created = PaymentChange.objects.get(action=PaymentChange.Action.CREATED)
        self.assertEqual(created.values["amount"], "$12.00")

    def test_a_payment_can_still_be_unlinked_to_a_typed_name(self):
        self.edit(payer_name="Someone Else", member="")
        self.payment.refresh_from_db()
        self.assertIsNone(self.payment.member)
        self.assertEqual(self.payment.payer_name, "Someone Else")
        self.assertContains(self.client.get(URL), "No account")

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

    def test_edit_is_validated(self):
        for name, data in {
            "negative": {"amount": "-1"},
            "future": {"paid_on": (timezone.localdate() + timedelta(days=1)).isoformat()},
            "no method": {"method": ""},
            "deleted account": {"member": "999999"},
        }.items():
            with self.subTest(name):
                self.assertEqual(self.edit(**data).status_code, 200)
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
