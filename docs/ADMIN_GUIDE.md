# planFC — Admin guide

How to add members, manage their accounts and decide who else is an admin.
Everything here happens inside the app, on the **Members** page, with the same
sign-in you use for everything else. There is no separate admin login.

Two sections need a terminal on the server and are for whoever runs it:
[the first admin](#the-first-admin) and [if no admin is left](#if-no-admin-is-left).
The rest needs only a phone.

For how the code works, see [ARCHITECTURE.md §3.6](ARCHITECTURE.md#36-accounts-accounts).
For setting up email, Google and Apple sign-in, see [ACCOUNTS.md](ACCOUNTS.md).

## Contents

- [Roles](#roles)
- [The first admin](#the-first-admin)
- [The Members page](#the-members-page)
- [Adding a member](#adding-a-member)
- [Account status](#account-status)
- [Managing a member](#managing-a-member)
- [What admins can't do](#what-admins-cant-do)
- [The record of changes](#the-record-of-changes)
- [If no admin is left](#if-no-admin-is-left)
- [Django's `/admin/`](#djangos-admin)
- [Quick reference](#quick-reference)

---

## Roles

There are two roles. Everyone with an account is a **member**. An **admin** is a
member with extra powers; there is no limit on how many the club has.

| | Member | Admin |
|---|:---:|:---:|
| Sign in, use the app | ✓ | ✓ |
| Change their own name, picture, email address and password | ✓ | ✓ |
| Turn notifications on and off for their own devices | ✓ | ✓ |
| Delete their own account | ✓ | ✓ (not while they are the only admin) |
| See the Members page and every member's account details | | ✓ |
| Add members and send invitations | | ✓ |
| Change another member's name, remove their picture | | ✓ |
| Confirm a member's email address for them | | ✓ |
| Deactivate and reactivate accounts | | ✓ |
| Delete another member's account | | ✓ |
| Make a member an admin, or remove another admin's role | | ✓ |
| See the record of what admins have changed | | ✓ |

Admins are equals: any admin can remove any other admin's role, or deactivate or
delete their account. Give the role to people you would trust with that.

Later milestones (creating games, recording payments) will use the same role:
whoever is an admin here will be an admin there.

## The first admin

A new installation has no admin, and only an admin can make another one. So the
first is made once, from a terminal on the server:

1. Sign up in the app the normal way and confirm your email address.
2. In the directory that holds `compose.yaml`, run:

   ```sh
   docker compose exec web python manage.py make_admin you@example.com
   ```

   It answers `Your Name <you@example.com> is now an admin.`
3. Reload the app. **Members** appears in the header.

From then on, make other admins in the app
([Making someone an admin](#making-someone-an-admin)).

Development and production each have their own database, so an admin in one is
not an admin in the other. Run the command in the stack you mean; production
lives in `/srv/planfc` ([DEPLOYMENT.md](DEPLOYMENT.md)).

## The Members page

Admins see a **Members** link in the header on every page, and a
**Manage members** button on their profile. Members see neither, and get an
"Admins only" page if they type the address in.

The page lists every account, in order of first name, with the member's email
address and two kinds of tag:

- **Admin**, on admins.
- The account's [status](#account-status), when it is anything other than active.

Search by any part of a name or email address. Tap a member to open their
account, where every action in this guide lives.

## Adding a member

People can create their own account from the sign-in page, so you don't have to
add anyone. Adding is for when you would rather set someone up yourself.

1. **Members → Add a member.**
2. Enter their first name, last name (optional) and email address. Tick
   **Make them an admin** if they should be one from the start.
3. **Add and send the invitation.**

What happens next:

- The account exists straight away, with the status **Invited**. It has no
  password, so nobody can sign in to it yet.
- They get an email, "Set up your planFC account", naming you as the person who
  added them, with a link.
- The link opens a page where they choose a password. That signs them in, and
  their status becomes **Active**. Following the link also confirms their email
  address, so they get no second "confirm your email" message.

The link works **once**, and for **3 days**. If it expires or gets lost, open
their account and use **Send the invitation again**. Sending a new one does not
cancel an earlier one that is still within its 3 days.

Things that can go wrong:

- **"A member with that email address already exists."** Search for the address
  on the Members page: the account may be deactivated, or may be someone who
  signed up and never confirmed.
- **"…the invitation email could not be sent."** The account was still created.
  The server's email settings need attention ([ACCOUNTS.md](ACCOUNTS.md#email-required-for-real-use));
  once they are fixed, use **Send the invitation again**.
- **No email provider is configured** (a development stack, usually). The
  invitation is printed to the server's log instead of sent:
  `docker compose logs web | grep /invite/`.

## Account status

| Status | What it means | Can they sign in? | What you can do |
|---|---|:---:|---|
| **Active** | A normal account | Yes | — |
| **Invited** | You added them and they haven't chosen a password yet | No | Send the invitation again |
| **Email not confirmed** | They signed up themselves but never followed the link in the confirmation email | No | Mark the email as confirmed |
| **Deactivated** | An admin switched the account off | No | Reactivate |

## Managing a member

Open the member from the Members page. The top of their page shows their role,
status, whether their email is confirmed, how they sign in (password, Google,
Apple), when they joined and when they last signed in.

### Changing a name or removing a picture

Under **Name**, edit and **Save name**. This is for fixing the roster, such as a
nickname or a typo; members can also change their own name on their profile.

**Remove their profile picture** appears when they have one. They can upload
another afterwards.

### Making someone an admin

1. Under **Role**, tap **Make an admin**.
2. Enter **your own** password when asked. The app asks again even though you
   are signed in, unless you re-entered it in the last few minutes, so that a
   phone left unlocked can't be used to hand out the role. If you only ever
   sign in with Google or Apple you have no password, so the app emails you a
   one-time code to enter instead.
3. Read what the role allows and confirm.

It takes effect at once: **Members** appears in their header on their next page.

**Remove the admin role** works the same way, on an admin's page. They stay a
member and keep their account.

You can't change your own role. If you want to stop being an admin, another
admin removes it for you. That rule is also what guarantees the club always has
at least one admin.

### Confirming an email address

A member who signed up but shows **Email not confirmed** is stuck: the app
won't sign them in until they follow the emailed link, and sometimes that email
lands in spam or never arrives. If you are sure the address is theirs (they
told you in person, say), tap **Mark the email as confirmed**. They can sign in
right away.

Don't use it for an address you can't vouch for. Confirmation is what stops
someone signing up with another person's email.

### Deactivating and reactivating

**Deactivate**, under **Access**, switches an account off:

- they are signed out on every device at their next tap,
- they can't sign in, by password, Google or Apple,
- nobody can sign up again with their email address,
- nothing is deleted, and an outstanding invitation link stops working.

**Reactivate** undoes all of it. A deactivated admin has no admin powers while
deactivated and gets them back on reactivation, so remove the role as well if
that isn't what you want.

Prefer this to deleting when someone leaves the club, takes a season off, or
needs to be kept out.

### Deleting an account

**Delete this account**, at the bottom of their page, asks for your password
like a role change does, then for confirmation. It permanently removes their
name, email address, picture, password, Google and Apple sign-in and
notification settings. It can't be undone, though the person can sign up again
afterwards and start from an empty account.

To delete your **own** account, use your profile, not the Members page. The
app refuses while you are the club's only admin: make someone else an admin
first.

## What admins can't do

- **See or set a member's password.** A member who forgot theirs uses
  **Forgot your password?** on the sign-in page.
- **Change a member's email address.** Members do that themselves under
  Profile → Email address, where the new address is confirmed by email.
- **Sign in as a member.**
- **Change their own role, or deactivate themselves.**
- **Edit or delete the record of changes.**

## The record of changes

Every change an admin makes to an account is recorded with who made it and
when: adding and inviting, sending an invitation again, role changes,
deactivating and reactivating, confirming an email, changing a name, removing a
picture, and deleting an account.

- A member's page shows the last 20 changes to that account, under
  **Changes by admins**.
- **Members → What admins have changed** shows the 200 most recent across all
  accounts, including deleted ones.

Entries keep the names and email addresses as they were at the time, so they
still make sense after either account is gone. Changes made with `make_admin`
on the server are recorded as made by "Command line". What members do to their
own accounts is not recorded here.

## If no admin is left

The rules above keep at least one admin in place. If the club still ends up
without a usable one (the only admin lost access to their email and their
password, for instance), whoever runs the server can make a new one the same
way as the first:

```sh
docker compose exec web python manage.py make_admin someone@example.com
```

and take the role away with `--remove`:

```sh
docker compose exec web python manage.py make_admin someone@example.com --remove
```

Both work on any existing account, by the email address it signs in with. If
the account is deactivated, the command says so; reactivate it from another
admin's Members page, or in [Django's `/admin/`](#djangos-admin).

## Django's `/admin/`

`/admin/` is a separate, technical tool for editing the database directly. It
has its own username-and-password login and is not needed for anything in this
guide. How it relates to the roles above:

- An admin made in the app has Django's **staff** flag, which is what "admin"
  means to the app. Staff alone can open `/admin/` but sees nothing there.
- An account made with `manage.py createsuperuser` has the **superuser** flag
  too. The app treats it as an admin, and it can edit everything in `/admin/`.
  Such an account signs in at `/admin/` with its username. To use it in the app
  as well, its email address has to be confirmed first: another admin can do
  that from the Members page. It is simpler to sign up normally and run
  `make_admin`.
- Removing the admin role in the app clears both flags.

## Quick reference

| I want to… | Do this |
|---|---|
| Make the very first admin | On the server: `docker compose exec web python manage.py make_admin you@example.com` |
| Add someone | Members → Add a member |
| Resend a lost or expired invitation | Their page → Send the invitation again |
| Help someone whose confirmation email never came | Their page → Mark the email as confirmed |
| Help someone who forgot their password | Nothing: they use "Forgot your password?" on the sign-in page |
| Make someone an admin | Their page → Make an admin |
| Stop someone being an admin | Their page → Remove the admin role |
| Keep someone out without losing their account | Their page → Deactivate |
| Remove someone for good | Their page → Delete this account |
| Fix a name or remove an unsuitable picture | Their page → Name |
| See who changed what | Members → What admins have changed |
| Recover when no admin can sign in | On the server: `make_admin`, as for the first admin |
