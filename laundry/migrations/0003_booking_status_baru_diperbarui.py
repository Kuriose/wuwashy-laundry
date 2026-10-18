import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0002_profile'),
    ]

    operations = [
        migrations.AlterField(
            model_name='booking',
            name='status',
            field=models.CharField(choices=[('menunggu', 'Menunggu penjemputan'), ('dijemput', 'Pakaian dijemput'), ('diproses', 'Sedang dicuci'), ('siap', 'Siap diambil'), ('diantar', 'Sedang diantar'), ('selesai', 'Selesai'), ('dibatalkan', 'Dibatalkan')], default='menunggu', max_length=20),
        ),
        migrations.AddField(
            model_name='booking',
            name='diperbarui',
            field=models.DateTimeField(auto_now=True, default=django.utils.timezone.now),
            preserve_default=False,
        ),
    ]
