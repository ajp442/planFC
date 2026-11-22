# planFC — Plan

**Status:** draft | Last updated: 2026-11-20

planFC is a play on words: "FC" stands for Football Club, and "plan" describes what this app helps us do; it helps our Football Club plan pickup games.


## Overview and Goal

During the winter our soccer group rents out space in a sports dome where we can play.
Typically we rent out half a field, which gives us space for about 18 people.
The cost is split between each person.

We want an app where group members can log in, sign up for games they want to attend, and pay for those games.

Our group currently uses the TeamReach app; it does most of what we want except accepting payments and tracking payments.

### Minimum Viable Product (MVP)
The most critical aspect (the reason for this website) is to be transparent with users of all of their payments and games played.
This way users can see how much they may owe or how much credit is on their account. A website that can track this information 
reliably and concisely would meet the minimum requirements.

### Ideal/Final Product
A fully integrated one-stop-shop solution would be ideal and would include the following:
- Users would be able to signup for games.
- Users would be able to view their payment history.
- Users would be able to view upcoming and past games (including if they played or not).
- Users can make electronic payments can be made directly from the website, verified and tracked in the database.
- Users can comment on specific payments (i.e. paying for a friend, donation, etc..).
- Users can pay on someone else's behalf (show up as credit on another users account).
- Users can generate reports for games played, and payments made.
- Periodic (monthly) email notifications sent out with a recap of amount owed or credit on their account.
- Event driven email notifications for situations that require prompt attention (removal from games if their account is negative).
- Admins can manually add/remove games
- Admins can update costs on a game/game basis if needed.
- Admins can add reoccurring games, this is useful since all the games are usually same time, place, cost, and location.
- Admins can manually add Users payments. (The first version: superusers add and edit, admins only view; see Payments.)
- Admins can manually track expenses: field rentals, Jersey's, game ball, Website maintenance, etc...
- Everything like payments, signups, manual editions, comments, etc... would require a non-editable internal timestamp for when data was
  entered into the system.

## Milestones
Each milestone should be complete and well vetted before moving onto the next milestone.

### Foundation
- A mobile-friendly web app (installable as a PWA — home screen icon, no store)
  - Avoids app store developer fees, review cycles on every release, and store payment rules, while still giving members a home screen icon.
- The site lives at **myplanfc.com**, bought from Cloudflare Registrar on 2026-11-07.
- HTTPS is free and automatic. Behind the Cloudflare Tunnel (see hosting below), Cloudflare issues and
  renews the public certificate. If we later serve the domain directly, Caddy does the same with
  Let's Encrypt from a two-line config. Neither needs a purchased certificate or a renewal cron job.
  - This is not only about the padlock. Service workers refuse to run on insecure origins, so HTTPS
    is a hard prerequisite for the PWA installing at all, not a finishing touch.
- The stack is Django (Python) with PostgreSQL.
  - Chosen over a TypeScript/Node stack, FastAPI and Go. The deciding factor was how much of the
    milestone list it removes: `django-allauth` covers email, Google and Apple sign-in, verification
    and account deletion as configuration, and Django's built-in admin covers game CRUD, manual
    payment entry and user management. That is most of Login system and Admin accounts.
  - The price is two languages. The PWA frontend is still hand-written JavaScript and the service
    worker is wired up manually, where a JS stack would have generated both.
  - Python's native `Decimal` suits a money ledger. Whatever we do, balances never touch floats.
  - This would be a relatively low traffic site (maybe a max of 500 users). we typically only have
    about 30-40 active users. Every candidate stack was fast enough; speed decided nothing here.
- Hosting: **decided 2026-11-07**. Production runs on the home laptop (`corncob`) behind a named
  Cloudflare Tunnel at myplanfc.com. A VPS is deferred to keep costs down. The decision, the
  step-by-step action plan and the triggers for revisiting it are in
  [`docs/HOSTING.md`](docs/HOSTING.md).
  - The tunnel removes the usual problems with home hosting. No router ports are opened, a
    changing home IP or ISP CGNAT doesn't matter, and the home IP stays hidden. It costs only
    the domain (about $10–11 a year).
  - The accepted trade-off is that Cloudflare decrypts traffic at its edge to route it, so it
    could read logins and ledger pages. Nothing crosses the internet unencrypted.
  - Still true from the original analysis: the ledger sits on one disk in one house, and payment
    webhooks and reminder emails assume uptime. Off-site backups and uptime monitoring are
    therefore part of the plan, not optional. Move to a VPS (~$5–7/month) if outages become
    something members notice. The compose stack moves unchanged.
- Use containers to spin up the website.
  -  CI/CD support is also another reason to use containers, as this can improve testing and delivery using pipelines.
  - Compose, not Kubernetes: three services (`db`, `web`, `caddy`), plus `cloudflared` where a stack
    is served through the tunnel. An orchestrator at this scale
    would be complexity with nothing to manage.
  - Containers also decouple the app from the hosting question above. Laptop, VPS, or a PaaS that
    consumes a Dockerfile are then the same deployment pointed somewhere else.
  - The database is the exception to "containers are disposable". Its data lives in a named volume,
    and `docker compose down -v` deletes it.
- Backups must exist before any real payment data does.
  - The MVP is a financial ledger, so losing it means losing records members will dispute. A volume
    is not a backup, and neither is a single disk.
  - What that means concretely: scheduled `pg_dump`, written somewhere off the host, and a restore
    that has actually been performed. An untested backup is not a backup.
- Notification email needs a sending provider and DNS records.
  - The recaps and event-driven emails above only work if they arrive. Mail sent straight from a
    self-hosted box to Gmail addresses largely lands in spam. A provider (Resend, Postmark, SES)
    plus SPF, DKIM and DMARC records fixes that, and free tiers cover 30-40 members comfortably.
  - This is a second reason to buy the domain early: the records hang off it.
- Development and host machines target Ubuntu 26.04 LTS.
  - Matching versions means a problem on one machine reproduces on the other. The app's runtime is
    pinned by the container image rather than the host, so the host's own Python version is irrelevant.
- Device testing: Android in an emulator, iOS on real hardware.
  - Android Studio's emulator runs at near-native speed on Linux with KVM. There is no iPhone
    simulator for Linux — the iOS Simulator ships inside Xcode and requires macOS — so iOS testing
    uses a physical iPhone, with `ios-webkit-debug-proxy` when we need a console.
  - Testing on any phone needs a trusted certificate, since both Safari and Chrome refuse to register
    a service worker over plain HTTP. Production gets it from the named tunnel at myplanfc.com.
    Dev stacks keep using a throwaway Cloudflare quick tunnel.
- Our set up must include unit tests, as this will be easier to implement and maintain right from the start.
  - Unit tests alone will not cover the riskiest logic: money arithmetic, and the signup/waitlist
    race when two members tap at the same instant. Those need integration tests against a real
    database, not mocks.
- Foundation is done when a placeholder PWA installs from myplanfc.com on a real iPhone and a real
  Android phone over HTTPS, deploys through CI, and has been restored from backup once.
  - The rule above says each milestone should be complete and well vetted before the next one starts.
    That needs a test someone can run, not a feeling.

### Login system
- A person should be able to create an account.
- Account creation should follow common workflow that people are used to.
  - Being able to create an account with email, google, apple, etc.
  - Be able to delete account
- The person should have an account profile where they can set their name and profile picture.
- A user login using installable PWA must support push notifications.
- There must be a way for users to not have to log in every time to PWA.
- A user account must include a valid email address.

### Admin accounts
- Assign and un-assign admin privileges

### Game creation
- Games will be created by admins
- Games can be edited by admins
- **Required** fields for a game:
  - Date & Time
  - Location
  - Cost (individual cost for a game)
  - timestamp of creation
- **Optional** fields for a game:
  -  limit of players (Max number of players).

### Game sign-up mechanics
- Users will be able to view and sign up for games
- If a game is full a user will be placed on the waitlist
- User will be able to cancel a game.

### Payments
- Users will be able to pay for a game.
- The first version tracks payments rather than processing them.
  - The MVP above is transparency about what each member owes or holds as credit, and that needs no
    payment processor. Members pay by Venmo or Zelle as they already do and an admin records it —
    the same manual path already agreed for cash. No fees, and Payments stops blocking the ledger.
  - A "Pay with Venmo" link can prefill the amount and note, but confirmation is still a human
    marking it received. Neither Venmo nor Zelle exposes an API for personal transfers.
- **Manual payment entry (first version, built 2026-11-20).** A superuser records each payment
  by hand on one page, Menu → Payments → Record a payment (`/payments/`). The fields, in order:
  1. **Who paid.** A text box that suggests existing members as you type, matching any part of
     their name or email ("ann" finds Ann Smith, Annie Jones and Mark Annandale; "smi ann" only
     Ann Smith). Picking a suggestion, or typing a member's full name exactly, links the payment
     to that account. If nobody matches, the payment is still recorded under the name as typed
     and shown as "No account". Tracking payments without hassle matters more than linking.
  2. **Amount** in dollars, more than zero, to the cent. Stored as `Decimal`, never a float, and
     the database itself refuses zero or negative amounts.
  3. **Date paid**, today by default (club time, America/Chicago). Earlier dates are fine,
     future ones are refused.
  4. **Method**: PayPal, Venmo, Zelle, Cash or Other, one tap each.
  5. **Note**: optional free text (paying for a friend, a donation, a check number).
  - Each payment also keeps who recorded it and a creation timestamp nobody can edit, separate
    from the date paid. Names are copied onto the row, so it still reads properly after an
    account is deleted. The payment survives that, unlinked.
  - **Who can do what:**
    - **Superusers** record payments and can edit any detail of one afterwards: who paid, the
      linked account, amount, date, method and note, with an optional reason. The role is granted
      only on the server's command line, which is the safeguard. Unlike Database admin, these
      pages ask for no fresh two-factor code every 12 hours, so entering payments stays quick on
      a phone.
    - **Admins** see every payment and its history, read-only. They can't add or edit.
    - **Members** see nothing here yet.
  - **The history is for auditing only.** Every payment recorded, edited or deleted leaves an
    entry: the values recorded, or each changed field's old and new value, plus who, when and
    the reason. Nobody can edit or remove an entry, not even a superuser. The app refuses, and
    the database itself refuses (a trigger blocks UPDATE and DELETE on the history table), so
    Database admin or a hand-typed query can't either. Entries copy names and values as text, so
    they survive the payment or the accounts involved being deleted.
  - The recording page lists the latest 100 payments under the form, so a run of payments can
    be entered and checked in one place. Each opens its own page with its history, and
    *Payment history* lists every change to every payment. Edited payments are marked "Edited".
  - Deleting a payment is only possible in Database admin (with 2FA), for a true duplicate, and
    the deletion is written to the history with the payment's last values.
- **Step-by-step recording and unconfirmed members (built 2026-11-21).** Recording became four
  steps (Who paid → Amount → Method & date → Review with a comment), with the steps shown on
  every page as the navigation back. The draft is kept in the session until it is recorded.
  - Who paid lists every account, with a pinned search box. Someone not listed is added as an
    **unconfirmed member** when the payment is recorded: a real account with no email and no
    password, so their payments live under a member and show up everywhere.
  - Admins link an unconfirmed account to the person's real one once they sign up. Their payments
    move over, each with an edit in its history, and the unconfirmed account is removed. Other
    apps (games, later) move their own records through the same signal
    (`accounts.signals.unconfirmed_account_linked`).
  - Payment methods are a table superusers edit in Database admin instead of fixed choices.
- **Next for manual payments**, not built yet:
  - Members see their own payment history and balance. This needs games and their costs, so it
    belongs with the ledger.
  - Admins (not only superusers) recording payments, if superusers become a bottleneck.
- Card processing, when we add it, means Stripe.
  - Fees run about 2.9% + 30c everywhere. The flat 30c is what hurts at our size: 65c on a $12 game
    is an effective 5.4%, against 3.4% on a $60 five-game top-up and 0.8% by ACH direct debit
    (capped at $5). That is an argument for the prepaid credit model the refund policy already assumes.
  - What the fee actually buys is programmatic confirmation, which Venmo and Zelle cannot give us.
  - Webhooks are the source of truth, never the browser redirect. A member can close the tab before
    it loads, and anyone can forge it by visiting the URL.
  - Webhook signatures must be verified, or anyone who finds the endpoint can post a fake success
    and play free all season.
  - Webhook handling must be idempotent, keyed on Stripe's event ID. Stripe retries and can deliver
    the same event twice, and double-crediting corrupts the one thing this app exists to get right.
  - ACH settles in 3-5 business days and can fail after appearing to succeed, so credit the ledger
    on settlement rather than on submission.
  - Test mode and the Stripe CLI let the whole flow be built and tested locally without real money.
- Whoever's name goes on a business payment account receives tax paperwork (1099-K) that friends
  reimbursing each other over Venmo do not. Worth settling before the account is opened.

### Analytics
- Be able to review attendance, finances, statistics (like cancellation rates, etc.)

## Open questions
When a question is answered, it will be deleted from here and incorporated into the main plan
- How will the payment structure work? Fixed cost? Early sign up discount?
- Will there be refunds? If so, under what circumstances?
  - Yes, refunds need to be an option. However, this is up to the discretion of the administrators.
    Details must be documented in a Rules/Payments section of the website with specific examples.
    **Note:** default behavior is to keep as a credit on the account. at some point we will have to consider credit on
    accounts as donations to the group.
- Will we support bringing a guest who does not have an account?


## Decisions

Most decisions with a note on their reasoning will be incorporated into the main document.

- Plan lives in `PLAN.md` at the repo root in Markdown, so it
  diffs and reviews like code, renders on GitHub for humans, and stays readable
  to Claude without a fetch step. Kept separate from any future `CLAUDE.md`,
  which is instructions for the agent rather than the shared project plan.
