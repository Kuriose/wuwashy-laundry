from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0010_merge_0009_anggotatim_0009_profile_notif'),
    ]

    operations = [
        migrations.AddField(
            model_name='alamat',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='alamat',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='latitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
        migrations.AddField(
            model_name='booking',
            name='longitude',
            field=models.DecimalField(blank=True, decimal_places=6, max_digits=9, null=True),
        ),
    ]
