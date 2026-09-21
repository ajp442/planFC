# planFC — Plan

Status: draft | Last updated: 2026-09-21

planFC is a play on words: "FC" stands for Football Club, and "plan" describes what this app helps us do; it helps our Football Club plan pickup games.


## Overview and Goal

During the winter our soccer group rents out space in a sports dome where we can play.
Typically we rent out half a field, which gives us space for about 18 people.
The cost is split between each person.

We want an app where group members can log in, sign up for games they want to attend, and pay for those games.

Our group currently uses the TeamReach app; it does most of what we want except accepting payments and tracking payments.

The most critical aspect (the reason for this website) is to be transparent with users of all of their past payments and games played.
This way it will be clear to users to see how much they may owe or how much credit is on their account.

## Milestones
Each milestone should be complete and well vetted before moving onto the next milestone.

### Foundation
- A mobile-friendly web app (installable as a PWA — home screen icon, no store)
  - Avoids app store developer fees, review cycles on every release, and store payment rules, while still giving members a home screen icon.
- We need a catchy URL (something like planfc.com if it is available)
- Need to figure out where/how to host this site.
- Basic manual and automated testing.

### Login system
- A person should be able to create an account.
- Account creation should follow common workflow that people are used to.
  - Being able to create an account with email, google, apple, etc.
  - Be able to delete account
- The person should have an account profile where they can set their name and profile picture.
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
