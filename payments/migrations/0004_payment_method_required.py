import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0003_payment_method'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='payment',
            name='method',
        ),
        migrations.RenameField(
            model_name='payment',
            old_name='method_ref',
            new_name='method',
        ),
        migrations.AlterField(
            model_name='payment',
            name='method',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='payments', to='payments.paymentmethod'),
        ),
    ]
