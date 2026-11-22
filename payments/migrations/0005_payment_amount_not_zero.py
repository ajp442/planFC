"""Negative amounts are allowed (refunds, corrections in the other
direction); only zero is still refused, by the database too."""

from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0004_payment_method_required'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='payment',
            name='payment_amount_positive',
        ),
        migrations.AddConstraint(
            model_name='payment',
            constraint=models.CheckConstraint(condition=models.Q(('amount', Decimal('0')), _negated=True), name='payment_amount_not_zero'),
        ),
    ]
