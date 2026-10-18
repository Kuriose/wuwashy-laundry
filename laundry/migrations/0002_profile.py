from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def buat_profile_untuk_akun_lama(apps, schema_editor):
    """Akun yang sudah ada sebelum fitur role: superuser jadi ADMIN, sisanya USER."""
    User = apps.get_model(*settings.AUTH_USER_MODEL.split('.'))
    Profile = apps.get_model('laundry', 'Profile')
    sudah_punya = set(Profile.objects.values_list('user_id', flat=True))
    for user in User.objects.exclude(pk__in=sudah_punya):
        Profile.objects.create(user=user, role='ADMIN' if user.is_superuser else 'USER')


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laundry', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Profile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('role', models.CharField(choices=[('USER', 'Pelanggan'), ('ADMIN', 'Admin')], default='USER', max_length=10)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.RunPython(buat_profile_untuk_akun_lama, migrations.RunPython.noop),
    ]
