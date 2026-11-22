"""Signals other apps listen to, so accounts/ needn't know what they store."""

from django.dispatch import Signal

# Sent by members.link() inside its transaction, before the unconfirmed
# account is deleted, with `actor`, `unconfirmed` and `account` (Users).
# Each receiver moves whatever of its own belongs to `unconfirmed` over to
# `account`, and returns a short description of what it moved ("3 payments")
# for the record, or "" if there was nothing.
unconfirmed_account_linked = Signal()
