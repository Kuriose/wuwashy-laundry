from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from laundry.models import Alamat, Booking, Notifikasi

PENANDA = '[DEMO]'  # tanda di kolom catatan agar pesanan contoh mudah dikenali dan dihapus

# (status, layanan, berat, menit_lalu): dibuat dari yang TERBARU ke terlama, jadi Beranda (menampilkan 3 pesanan
# aktif terbaru) memperlihatkan menunggu, dijemput, dan diproses; semuanya terlihat di halaman Pesanan saya.
CONTOH = [
    ('menunggu', 'reguler', '4', 5),
    ('dijemput', 'express', '3', 40),
    ('diproses', 'dry', '2', 180),
    ('siap', 'setrika', '5', 20 * 60),
    ('diantar', 'reguler', '6', 30 * 60),
]
TAHAP = [c[0] for c in CONTOH]


class Command(BaseCommand):
    help = ('Membuat pesanan contoh (satu per tahap) untuk akun uji agar bar progres di Beranda dan notifikasi '
            'bisa dibandingkan. Hanya untuk pengembangan.')

    def add_arguments(self, parser):
        parser.add_argument('--email', default='nadia@example.com', help='Akun pelanggan (default nadia@example.com).')
        parser.add_argument('--status', choices=TAHAP, help='Buat HANYA satu pesanan dengan status ini.')
        parser.add_argument('--hapus', action='store_true', help='Hapus pesanan contoh (dan notifikasinya), lalu selesai.')

    def handle(self, *args, **options):
        User = get_user_model()
        user = User.objects.filter(username=options['email']).first()
        if user is None:
            raise CommandError(f"Akun {options['email']} tidak ada. Jalankan dulu: python manage.py seed_users")

        # Selalu bersihkan contoh lama dulu, jadi perintah ini aman dijalankan berulang kali.
        lama = Booking.objects.filter(user=user, catatan__startswith=PENANDA)
        Notifikasi.objects.filter(booking__in=lama).delete()
        terhapus = lama.delete()[0]
        if options['hapus']:
            self.stdout.write(self.style.SUCCESS(f'{terhapus} data contoh dihapus.'))
            return

        utama = Alamat.utama_untuk(user)
        alamat = utama.baris_alamat if utama else 'Jl. Pramuka No. 12, Samarinda Ulu, Samarinda'
        pilihan = [c for c in CONTOH if options['status'] in (None, c[0])]
        sekarang = timezone.now()
        for status, layanan, berat, menit in pilihan:
            b = Booking.objects.create(
                user=user, asal='akun', nama=user.get_full_name() or user.email, whatsapp='081234567890',
                layanan=layanan, berat=Decimal(berat), alamat=alamat, status=status,
                catatan=f'{PENANDA} pesanan contoh tahap "{status}"',
            )
            waktu = sekarang - timedelta(minutes=menit)
            Booking.objects.filter(pk=b.pk).update(dibuat=waktu, diperbarui=waktu)  # lewati auto_now
            self.stdout.write(f'  {b.resi}  {status:<9}  {b.nama_layanan}')
        self.stdout.write(self.style.SUCCESS(
            f"{len(pilihan)} pesanan contoh dibuat untuk {options['email']}. "
            'Lihat Beranda, Pesanan saya, dan Notifikasi. Hapus dengan: python manage.py seed_demo_pesanan --hapus'
        ))
