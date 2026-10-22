from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('laundry', '0008_notifikasi_tipe'),
    ]

    operations = [
        migrations.CreateModel(
            name='AnggotaTim',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nama', models.CharField(max_length=100)),
                ('email', models.EmailField(error_messages={'unique': 'Email ini sudah terdaftar sebagai anggota tim.'}, max_length=150, unique=True)),
                ('telepon', models.CharField(error_messages={'unique': 'Nomor telepon ini sudah dipakai anggota lain.'}, max_length=20, unique=True)),
                ('peran', models.CharField(choices=[('kasir', 'Kasir'), ('kurir', 'Kurir')], default='kasir', max_length=10)),
                ('aktif', models.BooleanField(default=True)),
                ('dibuat', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'anggota tim',
                'verbose_name_plural': 'anggota tim',
                'ordering': ['peran', 'id'],
            },
        ),
    ]
