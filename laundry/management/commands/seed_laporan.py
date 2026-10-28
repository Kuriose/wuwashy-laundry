"""Data contoh untuk menguji halaman Laporan Tersimpan dan unduhan Excel.

    python manage.py seed_laporan            # buat pesanan contoh 4 bulan terakhir + bulan ini
    python manage.py seed_laporan --hapus    # hapus HANYA data contoh dari perintah ini

Pesanan contoh ditandai catatan "[data-uji-laporan]" sehingga aman dibedakan dari pesanan asli.
Semua pesanan tamu (tanpa akun), jadi tidak memicu poin/notifikasi pelanggan.
"""
import random
from datetime import datetime, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from laundry.models import Booking
from laundry.services import SERVICES

PENANDA = '[data-uji-laporan]'
NAMA = ['Rina Sari', 'Budi Santoso', 'Dewi Lestari', 'Andi Saputra', 'Nadia Putri', 'Rizky Maulana',
        'Siti Aminah', 'Agus Pranoto', 'Lestari Wulandari', 'Fajar Nugroho', 'Maya Anggraini', 'Hendra Wijaya']
JALAN = ['Jl. Juanda', 'Jl. Pangeran Antasari', 'Jl. Ir. H. Juanda', 'Jl. KH. Wahid Hasyim', 'Jl. Gunung Lipan',
         'Jl. Cendana', 'Jl. Pramuka', 'Jl. Dr. Soetomo']
STATUS = [('selesai', 72), ('diproses', 8), ('menunggu', 6), ('siap', 5), ('diantar', 4), ('dibatalkan', 5)]


class Command(BaseCommand):
    help = 'Membuat (atau menghapus dengan --hapus) pesanan contoh multi-bulan untuk menguji laporan.'

    def add_arguments(self, parser):
        parser.add_argument('--bulan', type=int, default=4, help='Berapa bulan ke belakang (default 4).')
        parser.add_argument('--per-bulan', type=int, default=45, help='Pesanan per bulan (default 45).')
        parser.add_argument('--hapus', action='store_true', help='Hapus data contoh seed_laporan lalu selesai.')

    def handle(self, *args, **opsi):
        contoh = Booking.objects.filter(catatan=PENANDA)
        if opsi['hapus']:
            n = contoh.count()
            contoh.delete()
            self.stdout.write(self.style.SUCCESS(f'{n} pesanan contoh dihapus.'))
            return
        if contoh.exists():
            contoh.delete()  # jalankan ulang = ganti, bukan menggandakan
        rnd = random.Random(7)
        sekarang = timezone.localtime()
        zona = timezone.get_current_timezone()
        status, bobot = zip(*STATUS)
        dibuat = 0
        for mundur in range(opsi['bulan'], -1, -1):
            tahun, bulan = sekarang.year, sekarang.month - mundur
            while bulan < 1:
                bulan += 12
                tahun -= 1
            batas = (sekarang.day if mundur == 0 else 28)
            for _ in range(opsi['per_bulan'] if mundur else max(8, opsi['per_bulan'] // 3)):
                layanan = rnd.choice(SERVICES)
                waktu = timezone.make_aware(
                    datetime(tahun, bulan, rnd.randint(1, batas), rnd.randint(7, 20), rnd.randint(0, 59)), zona)
                if waktu > sekarang:
                    waktu = sekarang - timedelta(hours=rnd.randint(1, 5))
                b = Booking.objects.create(
                    nama=rnd.choice(NAMA),
                    whatsapp='0812' + ''.join(rnd.choice('0123456789') for _ in range(8)),
                    layanan=layanan['key'],
                    berat=Decimal(rnd.randint(2, 16)) / 2,
                    alamat=f'{rnd.choice(JALAN)} No. {rnd.randint(1, 99)}, Samarinda',
                    catatan=PENANDA,
                    status=rnd.choices(status, bobot)[0],
                )
                # Sebagian pesanan selesai ditimbang ulang / diberi koreksi agar kolom tagihan bervariasi.
                ubah = {'dibuat': waktu, 'diperbarui': waktu}
                if b.status == 'selesai' and rnd.random() < 0.3:
                    ubah['berat_final'] = Decimal(rnd.randint(2, 18)) / 2
                    ubah['koreksi_harga'] = rnd.choice([0, 0, -2000, 3000])
                Booking.objects.filter(pk=b.pk).update(**ubah)  # lewati auto_now
                dibuat += 1
        self.stdout.write(self.style.SUCCESS(
            f'{dibuat} pesanan contoh dibuat. Buka Panel Admin > Laporan Tersimpan. '
            'Hapus dengan: python manage.py seed_laporan --hapus'))
