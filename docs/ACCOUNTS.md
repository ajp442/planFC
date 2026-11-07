# planFC — Accounts

How members sign up, sign in, stay signed in, and get notifications, and what
an operator has to configure for each. The code is the `accounts` app plus
[django-allauth](https://docs.allauth.org/). For where it fits in the system,
see [ARCHITECTURE.md](ARCHITECTURE.md#36-accounts-accounts).

Everything here is configured in `.env`; `.env.example` lists every variable.
With none of them set, a stack still works: email sign-up, with confirmation
emails printed to `docker compose logs web`.

---

## What members get

| PLAN.md requirement | How |
|---|---|
| Create an account | `/accounts/signup/`: first and last name, email, password twice |
| Email, Google, Apple | Email always; Google and Apple once their credentials are set |
| A valid email address | Mandatory confirmation: no sign-in until the emailed link is followed. Google and Apple supply an address they have already confirmed |
| Delete the account | Profile → Delete my account, after re-entering the password |
| Name and profile picture | `/profile/` |
| Not signing in every time | Sessions last 180 days from the last visit |
| Push notifications in the PWA | Profile → Notifications, per device |

Members can also change their password, reset a forgotten one, and change or
add email addresses (each confirmed again). These are allauth's own pages,
styled to match.

## Email (required for real use)

Without a provider, nobody can confirm their address, so nobody can sign up.
PLAN.md already calls for a sending provider (Resend, Postmark, SES); any of them
offers SMTP credentials:

```
EMAIL_HOST=smtp.resend.com
EMAIL_PORT=587
EMAIL_HOST_USER=resend
EMAIL_HOST_PASSWORD=<api key>
DEFAULT_FROM_EMAIL=planFC <noreply@planfc.com>
```

The sending domain needs the provider's SPF and DKIM records, or Gmail files
the confirmation email under spam.

Until then, the link can be fished out of the log:

```
docker compose logs web | grep confirm-email
```

## HTTPS

Set `DJANGO_HTTPS=1` once the site is served over HTTPS. It marks the session
and CSRF cookies `Secure`, so they never travel over plain HTTP, and it makes
links in emails start with `https://`. Leave it at `0` on `http://localhost`:
browsers never send a Secure cookie over HTTP, so signing in would silently fail.

## Google

1. In the [Google Cloud console](https://console.cloud.google.com/apis/credentials),
   create a project, configure the OAuth consent screen (External; app name
   planFC), and create an **OAuth client ID** of type *Web application*.
2. Authorised redirect URI: `https://planfc.com/accounts/google/login/callback/`.
   For local testing, add `http://localhost:8080/accounts/google/login/callback/`,
   since Google allows plain HTTP for localhost only.
3. Put the client ID and secret in `.env` as `GOOGLE_CLIENT_ID` and
   `GOOGLE_CLIENT_SECRET`, then `docker compose up -d`.

The "Continue with Google" button appears on sign-in and sign-up. The member's
Google name becomes their planFC name, and if a planFC account already uses the
same address, Google sign-in joins it rather than making a second account.

## Apple

Sign in with Apple on the web **requires an Apple Developer Program
membership ($99/year)**. That is the kind of fee PLAN.md chose a PWA to avoid,
so decide whether it is worth it before setting this up. Everyone can still
sign up with email or Google without it.

1. In Certificates, Identifiers & Profiles, create an **App ID** with Sign in
   with Apple enabled, then a **Services ID** (e.g. `com.planfc.web`) linked to
   it. Under the Services ID, add the domain `planfc.com` and the return URL
   `https://planfc.com/accounts/apple/login/callback/`. Apple accepts HTTPS
   only, so this can't be tried on localhost; use a tunnel or the real domain.
2. Create a **Key** with Sign in with Apple enabled and download the `.p8` file.
   It can only be downloaded once.
3. In `.env`:
   ```
   APPLE_CLIENT_ID=com.planfc.web          # the Services ID
   APPLE_TEAM_ID=ABCDE12345                # top right of the developer portal
   APPLE_KEY_ID=XYZ987WXYZ                 # the key's ID
   APPLE_PRIVATE_KEY=-----BEGIN PRIVATE KEY-----\nMIGT...\n-----END PRIVATE KEY-----
   ```
   The key goes on one line with each line break written as `\n`:
   `awk 'NF {printf "%s\\n", $0}' AuthKey_XYZ987WXYZ.p8`.

Apple sends the member's name only the first time they sign in, and lets them
hide their real address behind a relay (`…@privaterelay.appleid.com`). Mail to
the relay still reaches them, but only if the sending domain is registered
under *Sign in with Apple for Email Communication* in the developer portal.

## Push notifications

1. Generate a key pair **once**:
   ```
   docker compose run --rm web python manage.py generate_vapid_keys
   ```
   and put both lines in `.env`, plus `VAPID_SUBJECT=mailto:<an address you read>`.
2. `docker compose up -d`. The profile page now offers *Turn on for this
   device*, and *Send a test notification* once a device is on.

**Never change the key pair** on a running deployment. Every subscription is
bound to the public key it was made with. A new pair makes all of them fail
without any error, and every member would have to turn notifications on again.
Keep the pair with the database backups.

What members need:

- **Android, desktop Chrome/Edge/Firefox:** works in the browser and installed.
- **iPhone and iPad (iOS/iPadOS 16.4+):** only in the **installed** app. In a
  Safari tab the profile page explains how to install it first. Turning
  notifications on must be a tap on the button, which the page does.

Sending from code, for the milestones that need it:

```python
from accounts.push import send_to_user
send_to_user(member, title="Thursday's game is full", body="You're first on the waitlist.", url="/")
```

It returns how many devices accepted the message, and deletes subscriptions
whose push service reports the device gone (404/410).

## Staying signed in

There is no "remember me" box. Every sign-in lasts 180 days, and every visit
pushes that back (`SESSION_SAVE_EVERY_REQUEST`), so an active member never sees
the sign-in page again. On iOS the installed app keeps its own cookies,
separate from Safari, so a member signs in once inside the app after installing.
Signing in in Safari beforehand doesn't carry over.

Signing out (and deleting the account) first turns off the device's push
subscription, so the next person to sign in on a shared phone doesn't receive
the previous member's notifications.

## Profile pictures

Uploads up to 10 MB (JPEG, PNG, WebP, GIF) are decoded, turned upright, cropped
square, shrunk to 256 px and re-encoded as JPEG. Re-encoding drops all metadata,
including the GPS position phones embed, and means nothing a member uploads is
ever served back byte for byte. Pictures are stored in Postgres (about 20 KB
each), so the database backup covers them, and they are visible only to
signed-in members.

## Privacy and caching

Every page a signed-in member sees is sent with `Cache-Control: no-store,
private`, and the service worker never stores such a page. The worker's cache
belongs to the browser, not the member, so storing them could show one member's
balance offline to the next person on the device. Offline, those pages are
replaced by `/offline/`.

## Known limitations

- **Deleting an account removes everything about the member.** That's right
  while there is no ledger. Once payments exist, the ledger must keep its rows
  and their timestamps (PLAN.md), so deletion will have to anonymise the member
  (blank the name and email, delete the password and sign-in links) instead of
  deleting the row. Payment models should use `on_delete=PROTECT` toward the
  user, so a cascade can't quietly remove financial history.
- **Members who only use Google or Apple aren't asked to re-authenticate before
  deleting.** allauth doesn't yet support re-authenticating through a provider,
  so it skips the check for accounts without a password. The confirmation page
  is still there.
- **Rate limits** on sign-in, sign-up and password reset are allauth's
  defaults, kept in the database cache so all gunicorn workers share them.
- **Google/Apple inside the installed iOS app.** The provider's page opens in an
  in-app browser sheet and returns to the app. That should work on current iOS
  but hasn't been tried on a real iPhone yet; test it before relying on it.
