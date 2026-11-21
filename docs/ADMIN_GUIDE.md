# planFC — Admin guide

How to add members, manage their accounts and decide who else is an admin.
Everything here happens inside the app, on the **Members** page, with the same
sign-in you use for everything else. There is no separate admin login.

Three sections need a terminal on the server and are for whoever runs it:
[the first admin](#the-first-admin), [if no admin is left](#if-no-admin-is-left)
and [superusers](#superusers-and-database-admin). The rest needs only a phone.

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
- [Payments](#payments)
- [Superusers and Database admin](#superusers-and-database-admin)
  - [Two-factor authentication](#two-factor-authentication)
  - [A lost phone](#a-lost-phone)
- [Quick reference](#quick-reference)

---

## Roles

There are three roles. Everyone with an account is a **member**. An **admin** is a
member with extra powers; there is no limit on how many the club has. A
**superuser** is an admin who can also edit the database directly, in
[Database admin](#superusers-and-database-admin). It is meant for whoever runs
the server, and is given and taken away only on the server's command line.

| | Member | Admin | Superuser |
|---|:---:|:---:|:---:|
| Sign in, use the app | ✓ | ✓ | ✓ |
| Change their own name, picture, email address and password | ✓ | ✓ | ✓ |
| Turn notifications on and off for their own devices | ✓ | ✓ | ✓ |
| Delete their own account | ✓ | ✓ (not while they are the only admin) | Not in the app: the role is removed on the server first |
| See the Members page and every member's account details | | ✓ | ✓ |
| Add members and send invitations | | ✓ | ✓ |
| Change another member's name, remove their picture | | ✓ | ✓ |
| Confirm a member's email address for them | | ✓ | ✓ |
| Deactivate and reactivate accounts | | ✓ (not a superuser's) | ✓ (not a superuser's) |
| Delete another member's account | | ✓ (not a superuser's) | ✓ (not a superuser's) |
| Make a member an admin, or remove another admin's role | | ✓ | ✓ |
| See the record of what admins have changed | | ✓ | ✓ |
| Turn on two-factor authentication for their own account | | ✓ | Required |
| See every payment and its history | | ✓ | ✓ |
| Record payments and edit any detail of one | | | ✓ |
| Open Database admin (Django's `/admin/`) | | | ✓, with a code from their authenticator app |
| Make someone a superuser, or remove the role | | | Nobody in the app: only on the server |

Admins are equals: any admin can remove any other admin's role, or deactivate or
delete their account. Give the role to people you would trust with that.
Superusers are the exception: no one can change their role or account from
inside the app ([details](#superusers-and-database-admin)).

Later milestones (creating games) will use the same role: whoever is an admin
here will be an admin there. Payments are the exception: admins can see them, but
only superusers can record or edit them ([details](#payments)).

## The first admin

A new installation has no admin, and only an admin can make another one. So the
first is made once, from a terminal on the server:

1. Sign up in the app the normal way and confirm your email address.
2. In the directory that holds `compose.yaml`, run:

   ```sh
   docker compose exec web python manage.py make_admin you@example.com
   ```

   It answers `Your Name <you@example.com> is now an admin.`
3. Reload the app and open the menu (the three bars beside **planFC**, top
   left). It now has an **Admin** section.

Whoever runs the server will probably want database access too, which means
being a **superuser**: `manage.py superuser you@example.com`. See
[Superusers and Database admin](#superusers-and-database-admin).

From then on, make other admins in the app
([Making someone an admin](#making-someone-an-admin)).

Development and production each have their own database, so an admin in one is
not an admin in the other. Run the command in the stack you mean; production
lives in `/srv/planfc` ([DEPLOYMENT.md](DEPLOYMENT.md)).

## The Members page

The app's menu opens from the three bars beside **planFC** in the top left
corner of every page. For admins it has an **Admin** section; tap it to open
it. It is how you reach everything in this guide, including in the installed app, which has no address
bar to type into:

| Menu item | Opens |
|---|---|
| **Members** | Every account |
| **Admins and roles** | The same list, showing only admins |
| **Add a member** | The [invitation form](#adding-a-member) |
| **Admin changes** | [The record of changes](#the-record-of-changes) |
| **Database admin** | [Django's `/admin/`](#superusers-and-database-admin). Only shown to superusers |

Members have no Admin section in their menu, and get an "Admins only" page if they type one of
these addresses in. Admins also have a **Manage members** button on their
profile.

The Members page lists every account, in order of first name, with the
member's email address and two kinds of tag:

- **Admin**, on admins, or **Superuser**, on superusers.
- The account's [status](#account-status), when it is anything other than active.

**Everyone** and **Admins** at the top switch between all accounts and admins
only. Search by any part of a name or email address. Tap a member to open
their account, where every action in this guide lives, including changing
their role.

## Adding a member

People can create their own account from the sign-in page, so you don't have to
add anyone. Adding is for when you would rather set someone up yourself.

1. **Admin → Add a member.**
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

It takes effect at once: the **Admin** section appears in their menu on their next page.

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
- **Change a superuser.** A superuser's page has no role, deactivate or delete
  buttons. That role, and their access, is changed only on the server.
- **Make anyone a superuser.** Only the server's command line can.
- **Edit or delete the record of changes.**

## The record of changes

Every change an admin makes to an account is recorded with who made it and
when: adding and inviting, sending an invitation again, role changes,
deactivating and reactivating, confirming an email, changing a name, removing a
picture, and deleting an account.

- A member's page shows the last 20 changes to that account, under
  **Changes by admins**.
- **Admin → Admin changes** shows the 200 most recent across all
  accounts, including deleted ones.

Entries keep the names and email addresses as they were at the time, so they
still make sense after either account is gone. Changes made with `make_admin`
or `superuser` on the server (including making or removing a superuser, and
resetting someone's two-factor authentication) are recorded as made by
"Command line". What members do to their
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
admin's Members page, or in [Django's `/admin/`](#superusers-and-database-admin).

## Payments

Members pay by PayPal, Venmo, Zelle or cash as they already do, and a
superuser writes each payment down in the app. Nothing is charged through the
app.

| | Admin | Superuser |
|---|:---:|:---:|
| See every payment and its history | ✓ | ✓ |
| Record a payment | | ✓ |
| Edit any detail of a payment | | ✓ |
| Edit or remove anything in the history | | |

### Recording a payment (superusers)

Open **Menu → Payments → Record a payment**, and fill in, top to bottom:

1. **Who paid.** Start typing any part of their name or email, and pick them
   from the list (tap, or arrow keys and Enter). Typing someone's full name
   exactly links them too. The line under the box says which account the
   payment will go to. If nobody matches, keep typing the name: the payment is
   recorded under that name and shown as **No account**. You can link it to
   their account later by editing it.
2. **Amount** in dollars, e.g. `12` or `24.50`.
3. **Date paid**: today unless you change it. Use the day the money arrived,
   not the day you're entering it. The app keeps that separately anyway.
4. **Method**: PayPal, Venmo, Zelle, Cash or Other.
5. **Note**, optional: "paid for Sam too", "donation", a check number.

Then **Record the payment**. A green line confirms what was saved, and the
form is ready for the next one. The latest 100 payments are listed below it.

Unlike Database admin, these pages never ask for a code from your
authenticator app: your normal sign-in is enough. The superuser role itself
is the safeguard, since it can only be given on the server.

### Correcting a payment (superusers)

Tap the payment in the list to open it. Under its details is **Edit this
payment**: change whatever is wrong (who paid, the account, amount, date,
method or note), optionally say why in **Reason for the change**, and **Save
the changes**. The list marks the payment **Edited**.

When and by whom it was first recorded can't be changed.

A payment recorded twice by mistake can be deleted only in Database admin →
Payments (with your 2FA code). The deletion goes into the history too.

### The payment history (everyone who can see payments)

Each payment's page ends with its **History**: when it was recorded and with
what values, and every later edit, field by field ("Amount $12.00 → $15.00"),
with who made it, when and why. **Menu → Payments → Payment history** lists
every entry for every payment, newest first.

The history is for auditing. Nobody can edit or remove it, not even a
superuser and not even in Database admin: the database itself refuses.

## Superusers and Database admin

**Database admin** (Django's `/admin/`) is a separate, technical tool for
editing the database directly: every table, with none of the safeguards or the
record of changes described above. Nothing in this guide needs it except
deleting a duplicate payment, and most admins should not have it.

Only **superusers** can open it, and only with
[two-factor authentication](#two-factor-authentication). An ordinary admin
who goes to `/admin/` gets a "Superusers only" page.

The superuser role is given and taken away **only on the server's command
line**, never in the app:

```sh
docker compose exec web python manage.py superuser you@example.com             # make one
docker compose exec web python manage.py superuser you@example.com --remove    # back to plain admin
docker compose exec web python manage.py superuser --list                      # who has it, and who has no 2FA yet
docker compose exec web python manage.py superuser you@example.com --reset-2fa # a lost phone
```

Each change is written to the [record of changes](#the-record-of-changes), as
made from the "Command line".

A superuser gets a **Database admin** item in the Admin section of their menu.
It uses the sign-in they already have, plus a code from their phone. There is
no separate username and password.

How the roles fit together:

- A superuser is always an admin in the app as well.
- No admin can change a superuser in the app: their page has no role,
  deactivate or delete buttons, and says so. Not even another superuser can,
  in `/admin/`: "Superuser status" is read-only there, and a superuser's
  account can't be deactivated, demoted or deleted from it. A superuser can't
  delete their own account in the app either until the role is removed.
- To take everything away from a superuser, remove the superuser role first,
  then the admin role: `superuser <email> --remove`, then
  `make_admin <email> --remove`. `make_admin --remove` refuses a superuser.
- An account made with Django's `manage.py createsuperuser` has a username and
  no confirmed email address. It can't open Database admin, which goes through
  the app's own sign-in. Sign up normally and run `manage.py superuser`
  instead.

### Two-factor authentication

Database admin asks for a 6-digit code from an **authenticator app** on the
superuser's phone. Google Authenticator, Microsoft Authenticator, 1Password,
Authy or any other app that scans a QR code will do. There are no text
messages.

**Setting it up**, the first time a superuser opens Database admin:

1. Menu → Admin → **Database admin**. The app explains that two-factor
   authentication is needed and asks for your password again.
2. Scan the QR code with your authenticator app (or type in the secret shown
   under it), then enter the 6-digit code the app shows.
3. The app shows ten **recovery codes**. Download them or write them down, and
   keep them somewhere other than your phone. Each one works once, in place of
   a code from the app.
4. Open **Database admin** again and enter a code from the app.

**After that**, Database admin asks for a fresh code once every 12 hours.
Signing in to the app with your password asks for a code too, once you have
an authenticator app set up.

Menu → Account → **Two-factor authentication** (shown to every admin) is where
you see how many recovery codes are left, make new ones, or turn the app off.
Turning it off locks you out of Database admin until you set it up again.

Any admin can turn on two-factor authentication for their own account there.
For admins it is optional; for Database admin it is required.

### A lost phone

Sign in and enter one of your **recovery codes** where the app asks for a
code. Then go to Account → Two-factor authentication, turn the app off and set
it up again on the new phone.

Without the recovery codes either, whoever runs the server can reset it:

```sh
docker compose exec web python manage.py superuser you@example.com --reset-2fa
```

That deletes the authenticator app and recovery codes on the account. The
superuser then signs in with their password alone and sets up a new app the
next time they open Database admin. It works the same way for an admin who
turned on two-factor authentication and lost their phone.

## Quick reference

| I want to… | Do this |
|---|---|
| Make the very first admin | On the server: `docker compose exec web python manage.py make_admin you@example.com` |
| Make someone a superuser (Database admin) | On the server: `docker compose exec web python manage.py superuser you@example.com` |
| Take the superuser role away | On the server: the same with `--remove` |
| See who the superusers are | On the server: `docker compose exec web python manage.py superuser --list` |
| Record a payment (superusers) | Menu → Payments → Record a payment |
| Fix a payment entered wrong (superusers) | Open it from the list → Edit this payment |
| Remove a payment recorded twice (superusers) | Database admin → Payments → delete it |
| See who changed a payment, and when | Open it → History, or Menu → Payments → Payment history |
| Open Database admin | Menu → Admin → Database admin, then a code from your authenticator app |
| Turn two-factor authentication on or off, or get new recovery codes | Menu → Account → Two-factor authentication |
| Help someone who lost the phone with their authenticator app | Their recovery codes; otherwise, on the server: `superuser <email> --reset-2fa` |
| Find any admin page | Menu (☰, top left) → **Admin** |
| See who the admins are | Admin → Admins and roles |
| Add someone | Admin → Add a member |
| Resend a lost or expired invitation | Their page → Send the invitation again |
| Help someone whose confirmation email never came | Their page → Mark the email as confirmed |
| Help someone who forgot their password | Nothing: they use "Forgot your password?" on the sign-in page |
| Make someone an admin | Their page → Make an admin |
| Stop someone being an admin | Their page → Remove the admin role |
| Keep someone out without losing their account | Their page → Deactivate |
| Remove someone for good | Their page → Delete this account |
| Fix a name or remove an unsuitable picture | Their page → Name |
| See who changed what | Admin → Admin changes |
| Recover when no admin can sign in | On the server: `make_admin`, as for the first admin |
