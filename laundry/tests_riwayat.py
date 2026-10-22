"""Tes halaman Riwayat pesanan (/riwayat/)."""
from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Booking, PoinLog, Profile
from .riwayat import RiwayatPesanan
from .tests import FAST_HASH, buat_user


def buat(user, hari_lalu=0, **kw):
    """Pesanan milik akun; hari_lalu menggeser tanggal pembuatan."""
    data = dict(nama='Nadia Aulia', whatsapp='081234567890', layanan='express', berat=Decimal('5'),
                alamat='Jl. Contoh No. 1', user=user, asal='akun', status='selesai')
    data.update(kw)
    b = Booking.objects.create(**data)
    if hari_lalu:
        Booking.objects.filter(pk=b.pk).update(dibuat=timezone.now() - timedelta(days=hari_lalu))
        b.refresh_from_db()
    return b


@FAST_HASH
class RiwayatPesananTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('riwayat_pesanan')

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_menampilkan_pesanan_selesai_dan_dibatalkan_milik_sendiri_saja(self):
        selesai = buat(self.user)
        batal = buat(self.user, status='dibatalkan')
        aktif = buat(self.user, status='diproses')
        milik_lain = buat(buat_user('lain@example.com'))
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        hasil = list(r.context['halaman'])
        self.assertCountEqual(hasil, [selesai, batal])
        self.assertNotIn(aktif, hasil)
        self.assertNotIn(milik_lain, hasil)

    def test_tampilan_baris_sesuai_desain(self):
        b = buat(self.user)                                   # express 5 kg = Rp 60.000, +60 poin
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        for teks in ('Bersihnya sudah, ceritanya tersimpan.', 'Semua riwayat', 'PESANAN', 'TOTAL &amp; POIN', 'AKSI',
                     f'#{b.resi}', 'Cuci Express', '5 kg', 'Rp 60.000', '+60 poin', 'Selesai', 'Lihat detail',
                     'Pesan lagi', 'Menampilkan 1 dari 1 pesanan', 'Terapkan filter',
                     'Harga mengikuti daftar layanan yang berlaku saat pemesanan'):
            self.assertContains(r, teks)
        self.assertContains(r, f"{reverse('cari_pesanan')}?q={b.resi}")           # Lihat detail
        self.assertContains(r, f"{reverse('booking')}?layanan=express")           # Pesan lagi

    def test_ringkasan_hanya_dari_pesanan_selesai(self):
        buat(self.user, hari_lalu=40)                          # 60.000 / 60 poin
        buat(self.user, layanan='dry', berat=Decimal('2'))     # 50.000 / 50 poin
        buat(self.user, status='dibatalkan')                   # tidak dihitung
        buat(self.user, status='diproses')                     # belum selesai
        self.client.force_login(self.user)
        s = self.client.get(self.url).context['ringkasan']
        self.assertEqual((s['jumlah'], s['total'], s['poin']), (2, '110.000', 110))

    def test_rentang_bulan(self):
        a = buat(self.user, hari_lalu=100)
        b = buat(self.user)
        riwayat = RiwayatPesanan(self.user, {})
        awal, akhir = timezone.localtime(a.dibuat), timezone.localtime(b.dibuat)
        teks = riwayat.ringkasan()['rentang']
        self.assertIn('\u2013', teks)
        self.assertTrue(teks.endswith(str(akhir.year)))
        self.assertEqual(RiwayatPesanan(buat_user('baru@example.com'), {}).ringkasan()['rentang'], 'Belum ada pesanan selesai')

    def test_keadaan_kosong(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Belum ada riwayat pesanan')
        self.assertContains(r, 'Menampilkan 0 dari 0 pesanan')
        self.assertContains(r, '0 pesanan')

    def test_pesanan_dibatalkan_tanpa_poin_dan_badge_berbeda(self):
        buat(self.user, status='dibatalkan')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'rw-badge is-batal')
        self.assertNotContains(r, 'poin</small>')

    def test_poin_per_baris_dari_buku_poin(self):
        b = buat(self.user)
        self.assertEqual(PoinLog.objects.get(booking=b).jumlah, 60)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).context['halaman'][0].poin_didapat, 60)


@FAST_HASH
class RiwayatFilterTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('riwayat_pesanan')
        self.reg = buat(self.user, layanan='reguler', hari_lalu=10)
        self.exp = buat(self.user, layanan='express', hari_lalu=60)
        self.dry = buat(self.user, layanan='dry', berat=Decimal('2'), hari_lalu=400)
        self.client.force_login(self.user)

    def _hasil(self, **params):
        return list(self.client.get(self.url, params).context['halaman'])

    def test_cari_berdasarkan_nomor_pesanan_dan_nama_layanan(self):
        self.assertEqual(self._hasil(cari=self.reg.resi), [self.reg])
        self.assertEqual(self._hasil(cari=f'#{self.exp.resi.lower()}'), [self.exp])
        self.assertEqual(self._hasil(cari='dry clean'), [self.dry])
        self.assertCountEqual(self._hasil(cari='cuci'), [self.reg, self.exp])

    def test_filter_layanan(self):
        self.assertEqual(self._hasil(layanan='express'), [self.exp])

    def test_filter_periode(self):
        self.assertEqual(self._hasil(periode='30'), [self.reg])
        self.assertCountEqual(self._hasil(periode='90'), [self.reg, self.exp])
        self.assertCountEqual(self._hasil(periode='semua'), [self.reg, self.exp, self.dry])
        tahun_ini = self._hasil(periode='tahun')
        self.assertNotIn(self.dry, tahun_ini)

    def test_filter_digabung(self):
        self.assertEqual(self._hasil(cari='cuci', layanan='reguler', periode='30'), [self.reg])
        self.assertEqual(self._hasil(cari='cuci', layanan='reguler', periode='90', ), [self.reg])

    def test_ringkasan_tidak_ikut_filter(self):
        r = self.client.get(self.url, {'layanan': 'dry'})
        self.assertEqual(r.context['ringkasan']['jumlah'], 3)
        self.assertContains(r, 'Menampilkan 1 dari 1 pesanan')

    def test_nilai_filter_tidak_dikenal_diabaikan(self):
        r = self.client.get(self.url, {'periode': 'ngawur', 'layanan': 'xx', 'cari': '  '})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(r.context['halaman']), 3)
        self.assertFalse(r.context['riwayat'].ada_filter)

    def test_filter_tanpa_hasil_menawarkan_reset(self):
        r = self.client.get(self.url, {'cari': 'tidak-ada'})
        self.assertContains(r, 'Tidak ada pesanan yang cocok')
        self.assertContains(r, 'tampilkan semua riwayat')

    def test_form_filter_mempertahankan_pilihan(self):
        r = self.client.get(self.url, {'cari': 'cuci', 'periode': '90', 'layanan': 'express'})
        html = r.content.decode()
        self.assertIn('value="cuci"', html)
        self.assertIn('<option value="90" selected>', html)
        self.assertIn('<option value="express" selected>', html)

    def test_tidak_bisa_mengintip_pesanan_orang_lain_lewat_filter(self):
        lain = buat(buat_user('lain@example.com'))
        self.assertEqual(self._hasil(cari=lain.resi), [])


@FAST_HASH
class RiwayatHalamanTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('riwayat_pesanan')
        for i in range(12):
            buat(self.user, hari_lalu=i + 1)
        self.client.force_login(self.user)

    def test_pembagian_halaman(self):
        r = self.client.get(self.url)
        self.assertEqual(len(r.context['halaman']), 10)
        self.assertContains(r, 'Menampilkan 10 dari 12 pesanan')
        self.assertContains(r, 'rw-pg is-off')                    # Sebelumnya nonaktif di halaman 1
        r2 = self.client.get(self.url, {'page': 2})
        self.assertEqual(len(r2.context['halaman']), 2)
        self.assertContains(r2, 'Menampilkan 2 dari 12 pesanan')

    def test_halaman_tidak_valid_jatuh_ke_halaman_valid(self):
        self.assertEqual(self.client.get(self.url, {'page': 'abc'}).context['halaman'].number, 1)
        self.assertEqual(self.client.get(self.url, {'page': 999}).context['halaman'].number, 2)

    def test_tautan_halaman_mempertahankan_filter(self):
        r = self.client.get(self.url, {'cari': 'cuci', 'periode': '90'})
        self.assertEqual(r.context['riwayat'].qs_halaman(), 'cari=cuci&periode=90&')
        self.assertEqual(RiwayatPesanan(self.user, {}).qs_halaman(), '')
        self.assertContains(self.client.get(self.url, {'cari': 'cuci'}), '?cari=cuci&amp;page=2')

    def test_urutan_terbaru_dulu(self):
        tanggal = [b.dibuat for b in self.client.get(self.url).context['halaman']]
        self.assertEqual(tanggal, sorted(tanggal, reverse=True))


@FAST_HASH
class RiwayatNavigasiTests(TestCase):
    def test_sidebar_riwayat_aktif_dan_bisa_diklik_di_halaman_lain(self):
        user = buat_user()
        self.client.force_login(user)
        url = reverse('riwayat_pesanan')
        self.assertIn(f'class="nav-item is-active" href="{url}"', self.client.get(url).content.decode())
        self.assertIn(f'href="{url}"', self.client.get(reverse('dashboard')).content.decode())
        self.assertNotIn('is-soon" title="Segera hadir"><svg class="ic"><use href="#i-history"', self.client.get(url).content.decode())
