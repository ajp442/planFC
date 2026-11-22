"""How an amount reads everywhere: $12.00, and -$5.00 for a refund or a
correction in the other direction."""

from decimal import Decimal


def money(amount):
    if amount is None or amount == "":
        return ""
    amount = Decimal(amount)
    return f"{'-' if amount < 0 else ''}${abs(amount):.2f}"
