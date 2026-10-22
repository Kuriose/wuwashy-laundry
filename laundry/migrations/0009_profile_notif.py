from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0008_notifikasi_tipe'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='notif_status_pesanan',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notif_whatsapp',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notif_email',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='profile',
            name='notif_poin',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='profile',
            name='notif_promo',
            field=models.BooleanField(default=False),
        ),
    ]
