# planFC — Plan

**Status:** draft | Last updated: 2026-09-22

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
- Admins can manually add Users payments.
- Admins can manually track expenses: field rentals, Jersey's, game ball, Website maintenance, etc...
- Everything like payments, signups, manual editions, comments, etc... would require a non-editable internal timestamp for when data was
  entered into the system.

## Milestones
Each milestone should be complete and well vetted before moving onto the next milestone.

### Foundation
- A mobile-friendly web app (installable as a PWA — home screen icon, no store)
  - Avoids app store developer fees, review cycles on every release, and store payment rules, while still giving members a home screen icon.
- We need a catchy URL (something like planfc.com if it is available).
- TLS certificates come from Let's Encrypt, obtained and renewed automatically by Caddy.
  - Caddy is the reverse proxy in front of Django and does this from a two-line config, so the
    certificate is a line in the `Caddyfile` rather than a task. Free, and renewal needs no cron job.
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
- Need to figure out where/how to host this site.
  - The proof of concept runs on the Ubuntu laptop, which is enough to prove the stack and the PWA.
  - Real use probably wants a small VPS (~$5-7/month). Residential connections have dynamic IPs and
    usually block or forbid inbound 80/443; the ledger would sit on one disk in one house; payment
    webhooks and reminder emails assume uptime; and whoever owns the laptop becomes on-call. That is
    less per year than one member's share of a couple of games.
  - Decide before the first real payment data exists, because that is the point where the laptop's
    failure modes stop being an inconvenience and start being a dispute about money.
- Use containers to spin up the website.
  -  CI/CD support is also another reason to use containers, as this can improve testing and delivery using pipelines.
  - Compose, not Kubernetes: three services (`db`, `web`, `caddy`). An orchestrator at this scale
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
    a service worker over plain HTTP. Until planfc.com resolves somewhere real, a Cloudflare quick
    tunnel supplies an HTTPS URL.
- Our set up must include unit tests, as this will be easier to implement and maintain right from the start.
  - Unit tests alone will not cover the riskiest logic: money arithmetic, and the signup/waitlist
    race when two members tap at the same instant. Those need integration tests against a real
    database, not mocks.
- Foundation is done when a placeholder PWA installs from planfc.com on a real iPhone and a real
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
- How do we handle cash payments?
  - This will be a manual process. electronic payment is preferred, but admins must be able to accept cash and document in the app.
- Will we support bringing a guest who does not have an account?


## Decisions

Most decisions with a note on their reasoning will be incorporated into the main document.

- Plan lives in `PLAN.md` at the repo root in Markdown, so it
  diffs and reviews like code, renders on GitHub for humans, and stays readable
  to Claude without a fetch step. Kept separate from any future `CLAUDE.md`,
  which is instructions for the agent rather than the shared project plan.
