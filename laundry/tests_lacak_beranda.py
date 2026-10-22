"""Tes: kartu "Lacak cucianmu" di Beranda, teks notifikasi saat pesanan dibuat, dan command seed_demo_pesanan."""
import re
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse

from .models import Booking, Notifikasi, Profile
from .notifikasi import DAFTAR
from .tests import FAST_HASH, buat_user


def buat(user, status='menunggu', **kw):
    data = dict(nama='Nadia Aulia', whatsapp='081234567890', layanan='reguler', berat=Decimal('4'),
                alamat='Jl. Contoh No. 1', user=user, asal='akun', status=status)
    data.update(kw)
    return Booking.objects.create(**data)


def langkah_aktif(html):
    """Label tahap yang berstatus 'now' pada bar progres pertama di halaman."""
    li = re.search(r'<li class="[^"]*\bnow\b[^"]*"[^>]*>.*?<strong>(.*?)</strong>', html, re.S)
    return li.group(1) if li else None


def tahap_lewat(html):
    """Jumlah tahap yang sudah dilewati (bertanda 'done' tetapi bukan tahap yang sedang berjalan)."""
    return len([c for c in re.findall(r'<li class="([^"]*)"', html) if 'done' in c.split() and 'now' not in c.split()])


@FAST_HASH
class LacakBerandaTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.client.force_login(self.user)
        self.url = reverse('dashboard')

    def test_bar_progres_muncul_sejak_pesanan_dibuat_bukan_baru_setelah_dijemput(self):
        for status, tahap in (('menunggu', 'Menunggu penjemputan'), ('dijemput', 'Pakaian dijemput'),
                              ('diproses', 'Sedang dicuci'), ('siap', 'Siap diambil'), ('diantar', 'Sedang diantar')):
            Booking.objects.all().delete()
            b = buat(self.user, status)
            html = self.client.get(self.url).content.decode()
            self.assertIn(f'#{b.resi}', html, status)
            self.assertIn('class="steps"', html, status)
            self.assertEqual(langkah_aktif(html), tahap, status)
            self.assertNotIn('Belum ada cucian yang diproses', html, status)

    def test_tahap_yang_sudah_lewat_bertambah_saat_pesanan_dijemput(self):
        buat(self.user, 'menunggu')
        menunggu = self.client.get(self.url).content.decode()
        Booking.objects.all().delete()
        buat(self.user, 'dijemput')
        dijemput = self.client.get(self.url).content.decode()
        self.assertEqual((tahap_lewat(menunggu), tahap_lewat(dijemput)), (0, 1))
        self.assertIn('<use href="#i-check"/>', dijemput.split('class="steps"')[1])   # ikon centang pada tahap lewat

    def test_keadaan_kosong_bila_tidak_ada_pesanan_aktif(self):
        buat(self.user, 'selesai')
        buat(self.user, 'dibatalkan')
        r = self.client.get(self.url)
        self.assertContains(r, 'Belum ada cucian yang diproses')
        self.assertNotContains(r, 'pesanan aktif</span>')
        self.assertEqual(r.context['lacak'], [])

    def test_hanya_pesanan_milik_sendiri(self):
        buat(buat_user('lain@example.com'), 'diproses')
        self.assertContains(self.client.get(self.url), 'Belum ada cucian yang diproses')

    def test_menampilkan_jumlah_dan_membatasi_tiga_pesanan(self):
        pesanan = [buat(self.user) for _ in range(5)]
        r = self.client.get(self.url)
        self.assertContains(r, '5 pesanan aktif')
        self.assertContains(r, 'Lihat 2 pesanan aktif lainnya')
        self.assertEqual(r.context['lacak'], list(reversed(pesanan))[:3])           # terbaru dulu
        self.assertEqual(r.content.decode().count('class="steps"'), 3)

    def test_tiga_pesanan_atau_kurang_tidak_menampilkan_tautan_lainnya(self):
        for _ in range(3):
            buat(self.user)
        self.assertNotContains(self.client.get(self.url), 'pesanan aktif lainnya')

    def test_detail_dan_estimasi_tampil(self):
        b = buat(self.user, 'dijemput', layanan='express', berat=Decimal('3'))
        html = self.client.get(self.url).content.decode()
        self.assertIn('Cuci Express', html)
        self.assertIn('Pakaian dijemput', html)
        self.assertIn('Estimasi selesai:', html)
        self.assertIn(f'href="{reverse("pesanan_saya")}"', html)

    def test_admin_tetap_diarahkan_ke_panel(self):
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))


@FAST_HASH
class NotifikasiPesananDibuatTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def test_notifikasi_saat_dibuat_tidak_menyebut_sedang_atau_sudah_dijemput(self):
        b = buat(self.user)
        n = Notifikasi.objects.get()
        self.assertEqual((n.tipe, n.judul), ('menunggu', 'Pesanan dibuat'))
        self.assertIn(b.resi, n.isi)
        self.assertIn('menunggu penjemputan', n.isi)
        for kata in ('sudah dijemput', 'sedang dijemput', 'segera menjemput', 'sudah kami terima'):
            self.assertNotIn(kata, n.isi)

    def test_penjemputan_baru_diberitakan_saat_status_dijemput(self):
        b = buat(self.user)
        b.status = 'dijemput'
        b.save()
        judul = list(Notifikasi.objects.order_by('id').values_list('judul', flat=True))
        self.assertEqual(judul, ['Pesanan dibuat', 'Pakaian sudah dijemput'])
        self.assertIn('sudah kami jemput', Notifikasi.objects.latest('id').isi)

    def test_hanya_satu_notifikasi_saat_pesanan_dibuat(self):
        buat(self.user)
        self.assertEqual(Notifikasi.objects.count(), 1)

    def test_setiap_tahap_punya_judul_berbeda(self):
        self.assertEqual(len({kelas.judul for kelas in DAFTAR.values()}), len(DAFTAR))

    def test_halaman_notifikasi_menampilkan_teks_baru(self):
        buat(self.user)
        self.client.force_login(self.user)
        r = self.client.get(reverse('notifikasi'))
        self.assertContains(r, 'Pesanan dibuat')
        self.assertContains(r, 'menunggu penjemputan')


@FAST_HASH
class SeedDemoPesananTests(TestCase):
    def setUp(self):
        self.user = buat_user()          # nadia@example.com

    def _jalankan(self, *args):
        out = StringIO()
        call_command('seed_demo_pesanan', *args, stdout=out)
        return out.getvalue()

    def test_membuat_satu_pesanan_per_tahap_aktif(self):
        self._jalankan()
        status = list(Booking.objects.order_by('-dibuat').values_list('status', flat=True))
        self.assertEqual(status, ['menunggu', 'dijemput', 'diproses', 'siap', 'diantar'])
        self.assertTrue(all(b.user == self.user and b.asal == 'akun' for b in Booking.objects.all()))
        self.assertEqual(Notifikasi.objects.count(), 5)                  # satu notifikasi per pesanan

    def test_beranda_menampilkan_tiga_terbaru_dan_pesanan_saya_semuanya(self):
        self._jalankan()
        self.client.force_login(self.user)
        beranda = self.client.get(reverse('dashboard'))
        self.assertEqual([b.status for b in beranda.context['lacak']], ['menunggu', 'dijemput', 'diproses'])
        self.assertContains(beranda, 'Lihat 2 pesanan aktif lainnya')
        self.assertEqual(len(self.client.get(reverse('pesanan_saya')).context['pesanan']), 5)

    def test_aman_dijalankan_berulang(self):
        self._jalankan()
        self._jalankan()
        self.assertEqual(Booking.objects.count(), 5)
        self.assertEqual(Notifikasi.objects.count(), 5)

    def test_status_tunggal_menggantikan_contoh_lama(self):
        self._jalankan()
        self._jalankan('--status', 'dijemput')
        self.assertEqual(list(Booking.objects.values_list('status', flat=True)), ['dijemput'])
        self.assertEqual(Notifikasi.objects.get().tipe, 'dijemput')

    def test_hapus_hanya_menghapus_contoh_bukan_pesanan_asli(self):
        asli = buat(self.user, 'diproses')
        self._jalankan()
        self._jalankan('--hapus')
        self.assertEqual(list(Booking.objects.all()), [asli])
        self.assertEqual(Notifikasi.objects.filter(booking__isnull=True).count(), 0)

    def test_tanpa_akun_memberi_pesan_yang_jelas(self):
        with self.assertRaisesMessage(CommandError, 'seed_users'):
            self._jalankan('--email', 'tidak-ada@example.com')
