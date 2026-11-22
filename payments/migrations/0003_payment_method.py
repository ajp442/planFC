"""Payment methods move from fixed choices to a table superusers can edit in
Database admin. This migration creates the table with the five methods there
were, and points each payment at its row; 0004 then drops the old column.
Two migrations, because Postgres won't alter a table in the transaction that
just updated its rows."""

import django.db.models.deletion
from django.db import migrations, models

# The old choices: stored value -> name shown, in the order they were offered.
METHODS = {
    "paypal": "PayPal",
    "venmo": "Venmo",
    "zelle": "Zelle",
    "cash": "Cash",
    "other": "Other",
}


def create_methods(apps, schema_editor):
    PaymentMethod = apps.get_model("payments", "PaymentMethod")
    Payment = apps.get_model("payments", "Payment")
    rows = {}
    for order, (code, name) in enumerate(METHODS.items()):
        rows[code] = PaymentMethod.objects.create(name=name, sort_order=(order + 1) * 10)
    for code, row in rows.items():
        Payment.objects.filter(method=code).update(method_ref=row)


def restore_codes(apps, schema_editor):
    Payment = apps.get_model("payments", "Payment")
    codes = {name: code for code, name in METHODS.items()}
    for payment in Payment.objects.select_related("method_ref"):
        payment.method = codes.get(payment.method_ref.name, "other")
        payment.save(update_fields=["method"])


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_payment_history'),
    ]

    operations = [
        migrations.CreateModel(
            name='PaymentMethod',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('active', models.BooleanField(default=True, help_text='Offered when recording a payment.')),
                ('sort_order', models.PositiveSmallIntegerField(default=0, help_text='Lower comes first.')),
            ],
            options={
                'ordering': ['sort_order', 'name'],
            },
        ),
        migrations.AddField(
            model_name='payment',
            name='method_ref',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='payments.paymentmethod'),
        ),
        migrations.RunPython(create_methods, restore_codes),
    ]
