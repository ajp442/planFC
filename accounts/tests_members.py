"""Roles and the Members area: who may manage accounts, and what each action
does. docs/ADMIN_GUIDE.md describes the same behaviour for the admins."""

import re
from io import StringIO
from unittest import mock

from allauth.account.models import EmailAddress
from allauth.mfa.models import Authenticator
from allauth.mfa.totp.internal.auth import (
    TOTP,
    format_hotp_value,
    generate_totp_secret,
    hotp_value,
    yield_hotp_counters_from_time,
)
from django.core.cache import cache
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase
from django.urls import reverse

from . import members
from .models import AdminAction, ProfilePicture
from .tests import PASSWORD, make_member

User = get_user_model()
Action = AdminAction.Action


def make_superuser(email="root@example.com", first_name="Root", last_name="User"):
    user = make_member(email=email, first_name=first_name, last_name=last_name)
    user.is_staff = user.is_superuser = True
    user.save(update_fields=["is_staff", "is_superuser"])
    return user


def make_admin(email="ada@example.com", first_name="Ada", last_name="Admin"):
    user = make_member(email=email, first_name=first_name, last_name=last_name)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


class AdminTestCase(TestCase):
    def setUp(self):
        self.admin = make_admin()
        self.member = make_member()
        self.client.force_login(self.admin)

    def reauthenticate(self):
        """Sign in properly and re-enter the password, which the role and
        delete pages insist on (force_login leaves no trace of a password)."""
        self.client.post(reverse("account_login"), {"login": self.admin.email, "password": PASSWORD})
        self.client.post(reverse("account_reauthenticate"), {"password": PASSWORD})

    def act(self, action, user=None):
        user = user or self.member
        return self.client.post(reverse("member_action", args=[user.pk, action]), follow=True)

    def actions(self):
        return list(AdminAction.objects.order_by("pk").values_list("action", flat=True))


class AccessTests(AdminTestCase):
    def admin_urls(self):
        pk = self.member.pk
        return [
            reverse("member_list"),
            reverse("member_add"),
            reverse("member_activity"),
            reverse("member_detail", args=[pk]),
            reverse("member_role", args=[pk]),
            reverse("member_delete", args=[pk]),
        ]

    def test_signed_out_visitors_are_sent_to_sign_in(self):
        self.client.logout()
        for url in self.admin_urls():
            response = self.client.get(url)
            self.assertRedirects(response, f"{reverse('account_login')}?next={url}", msg_prefix=url)

    def test_members_who_are_not_admins_are_refused(self):
        self.client.force_login(self.member)
        for url in self.admin_urls():
            response = self.client.get(url)
            self.assertContains(response, "Admins only", status_code=403, msg_prefix=url)

    def test_a_member_cannot_post_an_action_or_promote_themselves(self):
        self.client.force_login(self.member)
        other = make_member(email="kit@example.com")
        self.assertEqual(self.act("deactivate", other).status_code, 403)
        self.assertEqual(self.client.post(reverse("member_role", args=[self.member.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("member_delete", args=[other.pk])).status_code, 403)
        self.assertEqual(self.client.post(reverse("member_add"), {
            "first_name": "X", "email": "x@example.com", "make_admin": "on",
        }).status_code, 403)

        other.refresh_from_db()
        self.member.refresh_from_db()
        self.assertTrue(other.is_active)
        self.assertFalse(self.member.is_staff)
        self.assertFalse(User.objects.filter(email="x@example.com").exists())

    def test_admins_get_the_members_link_and_members_do_not(self):
        self.assertContains(self.client.get(reverse("index")), reverse("member_list"))
        self.assertContains(self.client.get(reverse("profile")), "Manage members")

        self.client.force_login(self.member)
        self.assertNotContains(self.client.get(reverse("index")), reverse("member_list"))
        self.assertNotContains(self.client.get(reverse("profile")), "Manage members")

    def test_a_superuser_counts_as_an_admin(self):
        root = User.objects.create_superuser(username="root", email="root@example.com", password=PASSWORD)
        self.client.force_login(root)
        self.assertEqual(self.client.get(reverse("member_list")).status_code, 200)

    def test_unknown_actions_do_not_exist_and_actions_need_post(self):
        self.assertEqual(self.client.post(f"/members/{self.member.pk}/promote/").status_code, 404)
        self.assertEqual(self.client.get(reverse("member_action", args=[self.member.pk, "deactivate"])).status_code, 405)

    def test_admin_pages_are_never_cached(self):
        self.assertIn("no-store", self.client.get(reverse("member_list"))["Cache-Control"])


class ListTests(AdminTestCase):
    def test_lists_everyone_with_role_and_status(self):
        make_member(email="new@example.com", first_name="Nia", verified=False)
        response = self.client.get(reverse("member_list"))
        self.assertContains(response, "3 accounts")
        self.assertContains(response, "Sam Keeper")
        self.assertContains(response, "pill-admin", count=1)
        self.assertContains(response, "Email not confirmed", count=1)

    def test_search_matches_name_or_email(self):
        make_member(email="kit@elsewhere.org", first_name="Kit", last_name="Winger")
        response = self.client.get(reverse("member_list"), {"q": "winger"})
        self.assertContains(response, "kit@elsewhere.org")
        self.assertNotContains(response, "sam@example.com")

        response = self.client.get(reverse("member_list"), {"q": "elsewhere"})
        self.assertContains(response, "1 match")

    def test_the_admins_tab_lists_only_admins(self):
        User.objects.create_superuser(username="root", email="root@example.com", password=PASSWORD)
        response = self.client.get(reverse("member_list"), {"role": "admin"})
        self.assertContains(response, "2 admins")
        self.assertContains(response, "ada@example.com")
        self.assertContains(response, "root@example.com")
        self.assertNotContains(response, "sam@example.com")

        # Searching stays within the tab.
        response = self.client.get(reverse("member_list"), {"role": "admin", "q": "sam"})
        self.assertNotContains(response, "sam@example.com")


class MainMenuTests(TestCase):
    """The menu behind the three bars and the brand in the header."""

    def menu(self, response):
        return response.content.decode().split('id="main_menu"')[1].split("</nav>")[0]

    def test_visitors_are_offered_home_sign_in_and_sign_up(self):
        menu = self.menu(self.client.get(reverse("index")))
        for name in ("index", "account_login", "account_signup"):
            self.assertIn(f'href="{reverse(name)}"', menu)
        self.assertNotIn("submenu", menu)

    def test_members_get_an_account_section_and_no_admin_one(self):
        self.client.force_login(make_member())
        menu = self.menu(self.client.get(reverse("index")))
        self.assertIn('id="account_menu"', menu)
        for name in ("index", "profile", "account_email", "account_change_password", "account_logout"):
            self.assertIn(f'href="{reverse(name)}"', menu)
        self.assertNotIn('id="admin_menu"', menu)

    def test_the_menu_is_on_allauth_pages_too(self):
        self.assertIn(reverse("account_signup"), self.menu(self.client.get(reverse("account_login"))))


class AdminMenuTests(AdminTestCase):
    """The Admin section of the main menu: the way to every admin page, which
    an installed app needs because it has no address bar."""

    def menu(self, response):
        html = response.content.decode()
        return html.split('id="admin_menu"')[1].split("</details>")[0] if 'id="admin_menu"' in html else None

    def test_admins_get_a_menu_linking_every_admin_page(self):
        for page in (reverse("index"), reverse("profile"), reverse("member_list")):
            menu = self.menu(self.client.get(page))
            self.assertIsNotNone(menu, page)
            for url in (
                reverse("member_list"),
                f"{reverse('member_list')}?role=admin",
                reverse("member_add"),
                reverse("member_activity"),
            ):
                self.assertIn(f'href="{url}"', menu, page)

    def test_members_and_visitors_get_no_menu(self):
        self.client.force_login(self.member)
        self.assertIsNone(self.menu(self.client.get(reverse("index"))))
        self.client.logout()
        self.assertIsNone(self.menu(self.client.get(reverse("index"))))

    def test_only_superusers_are_offered_the_database_admin(self):
        self.assertNotIn("/admin/", self.menu(self.client.get(reverse("index"))))

        root = make_member(email="root@example.com", first_name="Root")
        call_command("superuser", "root@example.com", stdout=StringIO())
        self.client.force_login(root)
        self.assertIn('href="/admin/"', self.menu(self.client.get(reverse("index"))))
        # The app's session and a 2FA code: no second sign-in at /admin/.
        code = give_authenticator_app(root)
        self.client.post(f"{reverse('mfa_reauthenticate')}?next=/admin/", {"code": code()})
        self.assertEqual(self.client.get("/admin/").status_code, 200)


class InviteTests(AdminTestCase):
    def add(self, **overrides):
        data = {"first_name": "Robin", "last_name": "Striker", "email": "Robin@Example.com"}
        data.update(overrides)
        return self.client.post(reverse("member_add"), data, follow=True)

    def invite_link(self, message=None):
        message = message or mail.outbox[-1]
        return re.search(r"https?://testserver(/invite/\S+)", message.body).group(1)

    def test_adding_creates_an_account_with_no_password_and_emails_an_invitation(self):
        response = self.add()
        user = User.objects.get(email="robin@example.com")
        self.assertRedirects(response, reverse("member_detail", args=[user.pk]))
        self.assertContains(response, "an invitation was sent to robin@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Robin", "Striker"))
        self.assertFalse(user.has_usable_password())
        self.assertFalse(user.is_staff)
        self.assertFalse(EmailAddress.objects.get(user=user).verified)
        self.assertContains(response, "Invited")

        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["robin@example.com"])
        self.assertEqual(mail.outbox[0].subject, "[planFC] Set up your planFC account")
        self.assertIn("Ada Admin added you", mail.outbox[0].body)
        self.assertEqual(self.actions(), [Action.INVITED])

    def test_an_admin_can_be_added_directly(self):
        self.add(make_admin="on")
        self.assertTrue(User.objects.get(email="robin@example.com").is_staff)
        self.assertEqual(self.actions(), [Action.INVITED, Action.MADE_ADMIN])

    def test_an_address_already_in_use_is_refused(self):
        response = self.add(email="SAM@example.com")
        self.assertContains(response, "already exists")
        self.assertEqual(User.objects.count(), 2)
        self.assertEqual(len(mail.outbox), 0)

    def test_the_link_lets_them_choose_a_password_and_signs_them_in(self):
        self.add()
        link = self.invite_link()
        visitor = Client()
        self.assertContains(visitor.get(link), "Welcome, Robin Striker")

        response = visitor.post(link, {"new_password1": PASSWORD, "new_password2": PASSWORD})
        self.assertRedirects(response, reverse("index"))
        user = User.objects.get(email="robin@example.com")
        self.assertEqual(int(visitor.session["_auth_user_id"]), user.pk)
        self.assertTrue(user.check_password(PASSWORD))
        # Following the link is the proof a confirmation email would be.
        self.assertTrue(EmailAddress.objects.get(user=user).verified)

        # They can sign in the ordinary way from now on.
        other_device = Client()
        other_device.post(reverse("account_login"), {"login": "robin@example.com", "password": PASSWORD})
        self.assertEqual(int(other_device.session["_auth_user_id"]), user.pk)

    def test_the_link_works_only_once(self):
        self.add()
        link = self.invite_link()
        Client().post(link, {"new_password1": PASSWORD, "new_password2": PASSWORD})

        response = Client().get(link)
        self.assertContains(response, "no longer works", status_code=410)
        response = Client().post(link, {"new_password1": "another-long-pass-9", "new_password2": "another-long-pass-9"})
        self.assertEqual(response.status_code, 410)
        self.assertTrue(User.objects.get(email="robin@example.com").check_password(PASSWORD))

    def test_a_forged_or_mangled_link_is_refused(self):
        self.add()
        link = self.invite_link()
        user = User.objects.get(email="robin@example.com")
        uid = link.split("/")[2]
        for bad in (f"/invite/{uid}/abc-123/", "/invite/!!!/abc-123/", link[:-2] + "x/"):
            response = Client().post(bad, {"new_password1": PASSWORD, "new_password2": PASSWORD})
            self.assertEqual(response.status_code, 410, bad)
        user.refresh_from_db()
        self.assertFalse(user.has_usable_password())

    def test_a_password_reset_link_is_not_an_invitation(self):
        """The two kinds of link are signed with different salts."""
        from django.contrib.auth.tokens import default_token_generator
        from django.utils.encoding import force_bytes
        from django.utils.http import urlsafe_base64_encode

        uid = urlsafe_base64_encode(force_bytes(self.member.pk))
        token = default_token_generator.make_token(self.member)
        self.assertEqual(Client().get(f"/invite/{uid}/{token}/").status_code, 410)

    def test_a_weak_password_is_refused(self):
        self.add()
        visitor = Client()
        response = visitor.post(self.invite_link(), {"new_password1": "12345678", "new_password2": "12345678"})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", visitor.session)

    def test_deactivating_cancels_an_outstanding_invitation(self):
        self.add()
        link = self.invite_link()
        self.act("deactivate", User.objects.get(email="robin@example.com"))
        self.assertEqual(Client().get(link).status_code, 410)

    def test_the_invitation_page_is_never_cached(self):
        self.add()
        self.assertIn("no-store", Client().get(self.invite_link())["Cache-Control"])

    def test_the_invitation_can_be_sent_again(self):
        self.add()
        user = User.objects.get(email="robin@example.com")
        response = self.act("resend-invite", user)
        self.assertContains(response, "A new invitation was sent")
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(self.actions(), [Action.INVITED, Action.INVITE_RESENT])
        # Both links work until one of them is used.
        self.assertEqual(Client().get(self.invite_link(mail.outbox[0])).status_code, 200)
        self.assertEqual(Client().get(self.invite_link(mail.outbox[1])).status_code, 200)

    def test_no_invitation_for_someone_who_already_has_a_password(self):
        response = self.act("resend-invite")
        self.assertContains(response, "already set up their account")
        self.assertEqual(len(mail.outbox), 0)

    def test_the_account_survives_a_mail_server_failure(self):
        with mock.patch("accounts.members.get_adapter") as get_adapter, self.assertLogs("accounts.members", "ERROR"):
            from allauth.account.adapter import get_adapter as real_get_adapter

            adapter = real_get_adapter()
            get_adapter.return_value = adapter
            with mock.patch.object(adapter, "send_mail", side_effect=OSError("connection refused")):
                response = self.add()
        self.assertContains(response, "could not be sent")
        self.assertTrue(User.objects.filter(email="robin@example.com").exists())


class ManageTests(AdminTestCase):
    def test_detail_shows_the_account(self):
        response = self.client.get(reverse("member_detail", args=[self.member.pk]))
        self.assertContains(response, "Sam Keeper")
        self.assertContains(response, "sam@example.com")
        self.assertContains(response, "Password")
        self.assertContains(response, "Make an admin")

    def test_changing_a_name_is_recorded_with_the_old_one(self):
        url = reverse("member_detail", args=[self.member.pk])
        self.client.post(url, {"first_name": "Samira", "last_name": "Keeper"})
        self.member.refresh_from_db()
        self.assertEqual(self.member.first_name, "Samira")
        entry = AdminAction.objects.get()
        self.assertEqual((entry.action, entry.detail), (Action.NAME_CHANGED, "Was “Sam Keeper”"))
        self.assertEqual(entry.actor_label, "Ada Admin <ada@example.com>")

        # Saving without a change records nothing.
        self.client.post(url, {"first_name": "Samira", "last_name": "Keeper"})
        self.assertEqual(AdminAction.objects.count(), 1)

    def test_changing_a_role_needs_the_password_again(self):
        url = reverse("member_role", args=[self.member.pk])
        self.assertRedirects(self.client.get(url), f"{reverse('account_reauthenticate')}?next={url}",
                             fetch_redirect_response=False)
        self.client.post(url)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_staff)

    def test_making_and_unmaking_an_admin(self):
        self.reauthenticate()
        url = reverse("member_role", args=[self.member.pk])
        self.assertContains(self.client.get(url), "Make Sam Keeper an admin?")
        response = self.client.post(url, follow=True)
        self.assertContains(response, "Sam Keeper is now an admin.")
        self.member.refresh_from_db()
        self.assertTrue(members.is_admin(self.member))

        self.assertContains(self.client.get(url), "Remove Sam Keeper's admin role?")
        self.client.post(url)
        self.member.refresh_from_db()
        self.assertFalse(members.is_admin(self.member))
        self.assertEqual(self.actions(), [Action.MADE_ADMIN, Action.REMOVED_ADMIN])

    def test_an_admin_cannot_touch_a_superuser(self):
        root = make_superuser()
        self.reauthenticate()
        detail = self.client.get(reverse("member_detail", args=[root.pk]))
        self.assertContains(detail, "Superuser")
        self.assertNotContains(detail, "Remove the admin role")
        self.assertNotContains(detail, "Deactivate")
        self.assertNotContains(detail, "Delete this account")

        response = self.client.post(reverse("member_role", args=[root.pk]), follow=True)
        self.assertContains(response, "can only be changed on the server")
        self.act("deactivate", root)
        self.client.post(reverse("member_delete", args=[root.pk]))
        root.refresh_from_db()
        self.assertTrue(root.is_superuser and root.is_staff and root.is_active)
        self.assertEqual(self.actions(), [])

    def test_a_superuser_cannot_delete_their_own_account_in_the_app(self):
        root = self.admin = make_superuser()
        self.client.logout()
        self.reauthenticate()
        response = self.client.post(reverse("delete_account"), follow=True)
        self.assertContains(response, "You are a superuser")
        self.assertTrue(User.objects.filter(pk=root.pk).exists())

    def test_an_admin_cannot_change_their_own_role(self):
        self.reauthenticate()
        response = self.client.post(reverse("member_role", args=[self.admin.pk]), follow=True)
        self.assertContains(response, "can&#x27;t change your own role")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_staff)

    def test_deactivating_signs_the_member_out_and_blocks_sign_in(self):
        their_phone = Client()
        their_phone.force_login(self.member)
        self.assertEqual(their_phone.get(reverse("profile")).status_code, 200)

        response = self.act("deactivate")
        self.assertContains(response, "can no longer sign in")
        self.assertEqual(their_phone.get(reverse("profile")).status_code, 302)
        fresh = Client()
        fresh.post(reverse("account_login"), {"login": "sam@example.com", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", fresh.session)

        self.act("reactivate")
        fresh.post(reverse("account_login"), {"login": "sam@example.com", "password": PASSWORD})
        self.assertEqual(int(fresh.session["_auth_user_id"]), self.member.pk)
        self.assertEqual(self.actions(), [Action.DEACTIVATED, Action.REACTIVATED])

    def test_a_deactivated_admin_has_no_powers(self):
        other_admin = make_admin(email="bo@example.com", first_name="Bo")
        their_phone = Client()
        their_phone.force_login(other_admin)
        self.act("deactivate", other_admin)
        other_admin.refresh_from_db()
        self.assertFalse(members.is_admin(other_admin))
        self.assertEqual(their_phone.get(reverse("member_list")).status_code, 302)

    def test_an_admin_cannot_deactivate_themselves(self):
        response = self.act("deactivate", self.admin)
        self.assertContains(response, "can&#x27;t deactivate your own account")
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)

    def test_confirming_an_email_lets_a_stuck_member_sign_in(self):
        stuck = make_member(email="nia@example.com", first_name="Nia", verified=False)
        visitor = Client()
        visitor.post(reverse("account_login"), {"login": "nia@example.com", "password": PASSWORD})
        self.assertNotIn("_auth_user_id", visitor.session)

        response = self.act("confirm-email", stuck)
        self.assertContains(response, "nia@example.com is marked as confirmed")
        visitor.post(reverse("account_login"), {"login": "nia@example.com", "password": PASSWORD})
        self.assertEqual(int(visitor.session["_auth_user_id"]), stuck.pk)
        self.assertEqual(self.actions(), [Action.EMAIL_CONFIRMED])

    def test_removing_a_profile_picture(self):
        ProfilePicture.objects.create(user=self.member, jpeg=b"x")
        self.assertContains(self.client.get(reverse("member_detail", args=[self.member.pk])), "Remove their profile picture")
        self.act("remove-picture")
        self.assertFalse(ProfilePicture.objects.exists())
        self.assertEqual(self.actions(), [Action.PICTURE_REMOVED])

    def test_deleting_needs_the_password_again(self):
        url = reverse("member_delete", args=[self.member.pk])
        self.assertRedirects(self.client.get(url), f"{reverse('account_reauthenticate')}?next={url}",
                             fetch_redirect_response=False)
        self.client.post(url)
        self.assertTrue(User.objects.filter(pk=self.member.pk).exists())

    def test_deleting_removes_the_account_but_keeps_the_record(self):
        self.reauthenticate()
        url = reverse("member_delete", args=[self.member.pk])
        self.assertContains(self.client.get(url), "can't be undone")
        response = self.client.post(url, follow=True)
        self.assertRedirects(response, reverse("member_list"))
        self.assertFalse(User.objects.filter(pk=self.member.pk).exists())
        self.assertFalse(EmailAddress.objects.filter(email="sam@example.com").exists())

        entry = AdminAction.objects.get()
        self.assertEqual(entry.action, Action.DELETED)
        self.assertIsNone(entry.target)
        self.assertEqual(entry.target_label, "Sam Keeper <sam@example.com>")
        self.assertContains(self.client.get(reverse("member_activity")), "Sam Keeper &lt;sam@example.com&gt;")

    def test_deleting_yourself_goes_through_your_own_profile(self):
        self.reauthenticate()
        response = self.client.post(reverse("member_delete", args=[self.admin.pk]))
        self.assertRedirects(response, reverse("delete_account"), fetch_redirect_response=False)
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

    def test_the_only_admin_cannot_delete_their_own_account(self):
        self.reauthenticate()
        response = self.client.post(reverse("delete_account"), follow=True)
        self.assertContains(response, "only admin")
        self.assertTrue(User.objects.filter(pk=self.admin.pk).exists())

        make_admin(email="bo@example.com", first_name="Bo")
        self.client.post(reverse("delete_account"))
        self.assertFalse(User.objects.filter(pk=self.admin.pk).exists())

    def test_the_record_outlives_the_admin_who_made_it(self):
        self.act("deactivate")
        self.admin.delete()
        entry = AdminAction.objects.get()
        self.assertIsNone(entry.actor)
        self.assertEqual(entry.actor_label, "Ada Admin <ada@example.com>")


class MakeAdminCommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("make_admin", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_makes_the_first_admin(self):
        member = make_member()
        self.assertIn("Sam Keeper <sam@example.com> is now an admin.", self.run_command("SAM@example.com"))
        member.refresh_from_db()
        self.assertTrue(members.is_admin(member))
        self.assertFalse(member.is_superuser)

        entry = AdminAction.objects.get()
        self.assertEqual((entry.action, entry.actor, entry.actor_label), (Action.MADE_ADMIN, None, "Command line"))

    def test_remove_takes_the_role_away(self):
        admin = make_admin()
        self.run_command("ada@example.com", "--remove")
        admin.refresh_from_db()
        self.assertFalse(members.is_admin(admin))

    def test_remove_refuses_a_superuser(self):
        root = make_superuser()
        with self.assertRaisesMessage(CommandError, "superuser root@example.com --remove"):
            self.run_command("root@example.com", "--remove")
        root.refresh_from_db()
        self.assertTrue(root.is_superuser and root.is_staff)

    def test_has_no_superuser_option(self):
        make_member()
        with self.assertRaises(CommandError):
            self.run_command("sam@example.com", "--superuser")

    def test_an_unknown_address_is_an_error(self):
        with self.assertRaisesMessage(CommandError, "No account uses nobody@example.com"):
            self.run_command("nobody@example.com")


class SuperuserCommandTests(TestCase):
    def run_command(self, *args):
        out = StringIO()
        call_command("superuser", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_grants_and_removes_the_role(self):
        member = make_member()
        self.assertIn("is now a superuser", self.run_command("SAM@example.com"))
        member.refresh_from_db()
        self.assertTrue(member.is_superuser and member.is_staff)

        self.assertIn("still an admin", self.run_command("sam@example.com", "--remove"))
        member.refresh_from_db()
        self.assertFalse(member.is_superuser)
        self.assertTrue(members.is_admin(member))

        self.assertEqual(
            [(e.action, e.actor, e.actor_label) for e in AdminAction.objects.order_by("pk")],
            [(Action.MADE_SUPERUSER, None, "Command line"), (Action.REMOVED_SUPERUSER, None, "Command line")],
        )

    def test_repeating_changes_nothing(self):
        make_superuser()
        self.assertIn("already a superuser", self.run_command("root@example.com"))
        make_member()
        self.assertIn("not a superuser", self.run_command("sam@example.com", "--remove"))
        self.assertFalse(AdminAction.objects.exists())

    def test_list(self):
        self.assertIn("There are no superusers.", self.run_command("--list"))
        make_superuser()
        self.assertIn("Root User <root@example.com>", self.run_command("--list"))

    def test_an_unknown_address_is_an_error(self):
        with self.assertRaisesMessage(CommandError, "No account uses nobody@example.com"):
            self.run_command("nobody@example.com")


def give_authenticator_app(user):
    """Set up 2FA for `user` as if they had scanned the QR code; returns a
    function that reads the app's current code."""
    secret = generate_totp_secret()
    TOTP.activate(user, secret)

    def current_code():
        # Each code works once, so clear the record of used ones between calls.
        cache.clear()
        return format_hotp_value(hotp_value(secret, next(yield_hotp_counters_from_time())))

    return current_code


class DatabaseAdminTests(TestCase):
    """Django's /admin/: superusers who entered a 2FA code recently, and no
    way to change the superuser role from inside it."""

    def enter_code(self, code, next_url="/admin/"):
        return self.client.post(f"{reverse('mfa_reauthenticate')}?next={next_url}", {"code": code})

    def test_signed_out_visitors_go_to_the_apps_sign_in(self):
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertRedirects(response, f"{reverse('account_login')}?next=%2Fadmin%2F")

    def test_an_admin_is_turned_away(self):
        self.client.force_login(make_admin())
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertContains(response, "Superusers only", status_code=403)
        self.assertNotContains(self.client.get(reverse("member_list")), "Database admin")

    def test_django_login_form_is_never_shown(self):
        root = make_superuser()
        give_authenticator_app(root)
        response = self.client.post(reverse("admin:login"), {"username": root.username, "password": PASSWORD})
        self.assertRedirects(response, f"{reverse('account_login')}?next=%2Fadmin%2F", fetch_redirect_response=False)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_a_superuser_without_an_authenticator_app_is_sent_to_set_one_up(self):
        root = make_superuser()
        self.client.force_login(root)
        response = self.client.get(reverse("admin:index"), follow=True)
        # allauth asks for the password again before setting up an app.
        self.assertEqual(
            [url for url, _ in response.redirect_chain[-2:]],
            [reverse("mfa_activate_totp"), f"{reverse('account_reauthenticate')}?next=%2Faccounts%2F2fa%2Ftotp%2Factivate%2F"],
        )
        self.assertContains(response, "Database admin needs two-factor authentication")
        self.assertContains(self.client.get(reverse("profile")), "Database admin")
        self.assertContains(self.client.get(reverse("profile")), "Two-factor authentication")

    def test_a_superuser_must_enter_a_code(self):
        root = make_superuser()
        code = give_authenticator_app(root)
        self.client.force_login(root)
        response = self.client.get(reverse("admin:index"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], f"{reverse('mfa_reauthenticate')}?next=%2Fadmin%2F")
        # A password can't stand in for the code here, so it isn't offered.
        self.assertContains(response, "Database admin needs a code")
        self.assertNotContains(response, "Use your password")

        self.assertEqual(self.enter_code("000000").status_code, 200)  # Wrong: the form again.
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 302)

        self.assertRedirects(self.enter_code(code()), "/admin/", fetch_redirect_response=False)
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_signing_in_with_password_and_code_opens_it(self):
        root = make_superuser()
        code = give_authenticator_app(root)
        response = self.client.post(reverse("account_login"), {"login": root.email, "password": PASSWORD})
        self.assertRedirects(response, reverse("mfa_authenticate"), fetch_redirect_response=False)
        self.client.post(reverse("mfa_authenticate"), {"code": code()})
        self.assertEqual(self.client.get(reverse("admin:index")).status_code, 200)

    def test_a_code_only_lasts_so_long(self):
        root = make_superuser()
        code = give_authenticator_app(root)
        self.client.force_login(root)
        self.enter_code(code())
        with self.settings(SUPERUSER_2FA_MAX_AGE=-1):
            response = self.client.get(reverse("admin:index"), follow=True)
        self.assertEqual(response.redirect_chain[-1][0], f"{reverse('mfa_reauthenticate')}?next=%2Fadmin%2F")

    def test_the_login_page_will_not_redirect_off_site(self):
        root = make_superuser()
        code = give_authenticator_app(root)
        self.client.force_login(root)
        self.enter_code(code())
        response = self.client.get(f"{reverse('admin:login')}?next=https://evil.example/")
        self.assertRedirects(response, reverse("admin:index"), fetch_redirect_response=False)

    def test_the_superuser_role_cannot_be_changed_there(self):
        root = make_superuser()
        other = make_superuser(email="bo@example.com", first_name="Bo")
        member = make_member()
        code = give_authenticator_app(root)
        self.client.force_login(root)
        self.enter_code(code())

        url = reverse("admin:auth_user_change", args=[member.pk])
        form = self.client.get(url).context["adminform"].form
        self.assertNotIn("is_superuser", form.fields)
        data = {k: v for k, v in form.initial.items() if v is not None and k in form.fields}
        data.update(is_superuser="on", is_staff="on", is_active="on",
                    date_joined_0="2026-01-01", date_joined_1="00:00:00")
        self.client.post(url, data)
        member.refresh_from_db()
        self.assertFalse(member.is_superuser)

        other_form = self.client.get(reverse("admin:auth_user_change", args=[other.pk])).context["adminform"].form
        self.assertNotIn("is_active", other_form.fields)
        self.assertNotIn("is_staff", other_form.fields)
        response = self.client.post(reverse("admin:auth_user_delete", args=[other.pk]), {"post": "yes"})
        self.assertEqual(response.status_code, 403)
        self.assertTrue(User.objects.filter(pk=other.pk).exists())

    def test_reset_2fa_from_the_command_line(self):
        root = make_superuser()
        give_authenticator_app(root)
        out = StringIO()
        call_command("superuser", "--list", stdout=out)
        self.assertNotIn("no two-factor", out.getvalue())

        call_command("superuser", "root@example.com", "--reset-2fa", stdout=StringIO())
        self.assertFalse(Authenticator.objects.filter(user=root).exists())
        self.assertEqual(AdminAction.objects.get().action, Action.TWO_FACTOR_RESET)
        out = StringIO()
        call_command("superuser", "--list", stdout=out)
        self.assertIn("no two-factor authentication yet", out.getvalue())
