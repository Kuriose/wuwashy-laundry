import random
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from laundry.models import Booking
from laundry.services import SERVICES

NAMA = ['Rina Sari', 'Budi Santoso', 'Dewi Lestari', 'Andi Saputra', 'Nadia Putri', 'Rizky Maulana',
        'Siti Aminah', 'Agus Pranoto', 'Lestari Wulandari', 'Fajar Nugroho']
# (status, bobot) - kira-kira meniru proporsi di desain dasbor
STATUS = [('selesai', 66), ('diproses', 15), ('menunggu', 10), ('siap', 6), ('dibatalkan', 3)]


class Command(BaseCommand):
    help = 'Membuat pesanan contoh bulan ini agar dasbor admin terisi (hanya untuk pengembangan).'

    def add_arguments(self, parser):
        parser.add_argument('--jumlah', type=int, default=60, help='Jumlah pesanan (default 60).')
        parser.add_argument('--force', action='store_true', help='Tetap buat walau sudah ada pesanan.')

    def handle(self, *args, **options):
        if Booking.objects.exists() and not options['force']:
            raise CommandError('Sudah ada pesanan. Pakai --force bila tetap ingin menambah data contoh.')
        rnd = random.Random(2026)
        sekarang = timezone.localtime()
        awal_bulan = sekarang.replace(day=1, hour=8, minute=0, second=0, microsecond=0)
        rentang = max(int((sekarang - awal_bulan).total_seconds()), 1)
        status, bobot = zip(*STATUS)
        for _ in range(options['jumlah']):
            layanan = rnd.choice(SERVICES)
            b = Booking.objects.create(
                nama=rnd.choice(NAMA),
                whatsapp='0812' + ''.join(rnd.choice('0123456789') for _ in range(8)),
                layanan=layanan['key'],
                berat=Decimal(rnd.randint(2, 16)) / 2,
                alamat='Jl. Contoh No. %d, Samarinda' % rnd.randint(1, 99),
                status=rnd.choices(status, bobot)[0],
            )
            waktu = awal_bulan + timedelta(seconds=rnd.randint(0, rentang))
            Booking.objects.filter(pk=b.pk).update(dibuat=waktu, diperbarui=waktu)  # lewati auto_now
        self.stdout.write(self.style.SUCCESS(f"{options['jumlah']} pesanan contoh dibuat."))
