from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('laundry', '0003_booking_status_baru_diperbarui'),
    ]

    operations = [
        migrations.AddField(
            model_name='profile',
            name='whatsapp',
            field=models.CharField(blank=True, db_index=True, max_length=20),
        ),
        migrations.AddField(
            model_name='booking',
            name='user',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pesanan', to=settings.AUTH_USER_MODEL),
        ),
        migrations.AddField(
            model_name='booking',
            name='asal',
            field=models.CharField(choices=[('akun', 'Login saat memesan'), ('whatsapp', 'Dicocokkan lewat nomor WhatsApp'), ('tamu', 'Tamu (tanpa akun)')], default='tamu', max_length=10),
        ),
        migrations.CreateModel(
            name='PoinLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jumlah', models.IntegerField(help_text='Positif = poin masuk, negatif = poin dipakai.')),
                ('saldo', models.IntegerField(help_text='Saldo poin sesudah transaksi ini.')),
                ('keterangan', models.CharField(max_length=100)),
                ('dibuat', models.DateTimeField(auto_now_add=True)),
                ('booking', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='poin_log', to='laundry.booking')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='poin_log', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['-dibuat', '-id'],
                'constraints': [models.UniqueConstraint(condition=models.Q(('jumlah__gt', 0)), fields=('booking',), name='poin_masuk_unik_per_pesanan')],
            },
        ),
    ]
