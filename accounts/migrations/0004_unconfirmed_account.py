import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_superuser_actions'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name='adminaction',
            name='action',
            field=models.CharField(choices=[('invited', 'Added and invited'), ('invite_resent', 'Invitation sent again'), ('made_admin', 'Made an admin'), ('removed_admin', 'Admin role removed'), ('made_superuser', 'Made a superuser'), ('removed_superuser', 'Superuser role removed'), ('two_factor_reset', 'Two-factor authentication reset'), ('deactivated', 'Deactivated'), ('reactivated', 'Reactivated'), ('email_confirmed', 'Email marked as confirmed'), ('name_changed', 'Name changed'), ('picture_removed', 'Profile picture removed'), ('deleted', 'Account deleted'), ('added_unconfirmed', 'Added as an unconfirmed member'), ('linked', 'Unconfirmed account linked in')], max_length=32),
        ),
        migrations.CreateModel(
            name='UnconfirmedAccount',
            fields=[
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name='unconfirmed_account', serialize=False, to=settings.AUTH_USER_MODEL)),
                ('created_by_label', models.CharField(max_length=320)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
