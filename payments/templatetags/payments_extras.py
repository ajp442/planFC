from django import template

from ..money import money as format_money

register = template.Library()


@register.filter
def money(amount):
    """{{ payment.amount|money }}: "$12.00", or "-$5.00" for a negative amount."""
    return format_money(amount)
