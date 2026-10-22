"""Membuat pesanan contoh untuk pengembangan.

Menghasilkan 100 pesanan yang tersebar di bulan Agustus, September, dan Oktober 2026
dengan proporsi realistis antar bulan dan status.
"""
import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from laundry.models import Booking
from laundry.services import SERVICES

NAMA = [
    'Rina Sari', 'Budi Santoso', 'Dewi Lestari', 'Andi Saputra', 'Nadia Putri',
    'Rizky Maulana', 'Siti Aminah', 'Agus Pranoto', 'Lestari Wulandari', 'Fajar Nugroho',
    'Maya Kusuma', 'Arif Hidayat', 'Putri Rahayu', 'Hendra Wijaya', 'Fitriani Hamid',
    'Dimas Prasetyo', 'Yuli Astuti', 'Bayu Nugraha', 'Nurul Aini', 'Rendi Saputra',
]

# (status, bobot) – meniru distribusi di desain dasbor
STATUS = [
    ('selesai', 66),
    ('diproses', 15),
    ('menunggu', 10),
    ('siap', 6),
    ('dibatalkan', 3),
]

# Distribusi pesanan per bulan (total = 100)
# Agustus: 30, September: 35, Oktober (s.d. tgl 22): 35
DISTRIBUSI_BULAN = [
    (2026, 8,  30),
    (2026, 9,  35),
    (2026, 10, 35),
]

# Hari maksimum yang tersedia di bulan Oktober (disesuaikan tanggal seed dijalankan).
# Kita batasi sampai tanggal 22 supaya konsisten dengan desain (periode Oktober 1–22).
BATAS_OKTOBER = 22


def _awal_akhir(tahun, bulan, rnd):
    """Kembalikan (awal, akhir_eksklusif) sebagai datetime-aware untuk bulan tsb."""
    zona = timezone.get_current_timezone()
    awal = datetime(tahun, bulan, 1, 8, 0, 0)
    if bulan == 12:
        akhir = datetime(tahun + 1, 1, 1, 0, 0, 0)
    elif bulan == 10:
        # Hanya sampai tanggal 22 Oktober
        akhir = datetime(tahun, bulan, BATAS_OKTOBER + 1, 0, 0, 0)
    else:
        akhir = datetime(tahun, bulan + 1, 1, 0, 0, 0)
    return timezone.make_aware(awal, zona), timezone.make_aware(akhir, zona)


class Command(BaseCommand):
    help = (
        'Membuat 100 pesanan contoh tersebar di Agustus–Oktober 2026 '
        '(hanya untuk pengembangan).'
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--force', action='store_true',
            help='Tetap buat walau sudah ada pesanan.',
        )

    def handle(self, *args, **options):
        if Booking.objects.exists() and not options['force']:
            raise CommandError(
                'Sudah ada pesanan. Pakai --force bila tetap ingin menambah data contoh.'
            )

        rnd = random.Random(2026)
        status_list, bobot_list = zip(*STATUS)
        total_dibuat = 0

        for tahun, bulan, jumlah in DISTRIBUSI_BULAN:
            awal, akhir = _awal_akhir(tahun, bulan, rnd)
            rentang = int((akhir - awal).total_seconds())

            for _ in range(jumlah):
                layanan = rnd.choice(SERVICES)
                b = Booking.objects.create(
                    nama=rnd.choice(NAMA),
                    whatsapp='0812' + ''.join(rnd.choice('0123456789') for _ in range(8)),
                    layanan=layanan['key'],
                    berat=Decimal(rnd.randint(2, 16)) / 2,
                    alamat='Jl. Contoh No. %d, Samarinda' % rnd.randint(1, 99),
                    status=rnd.choices(status_list, bobot_list)[0],
                )
                waktu = awal + timedelta(seconds=rnd.randint(0, rentang - 1))
                Booking.objects.filter(pk=b.pk).update(dibuat=waktu, diperbarui=waktu)
                total_dibuat += 1

        self.stdout.write(self.style.SUCCESS(
            f'{total_dibuat} pesanan contoh dibuat '
            f'(Agustus: {DISTRIBUSI_BULAN[0][2]}, '
            f'September: {DISTRIBUSI_BULAN[1][2]}, '
            f'Oktober: {DISTRIBUSI_BULAN[2][2]}).'
        ))
