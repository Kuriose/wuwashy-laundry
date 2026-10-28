"""Tes halaman Notifikasi (/notifikasi/) dan notifikasi poin/hadiah."""
import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .kotak_notifikasi import KotakNotifikasi
from .models import Booking, Notifikasi, PoinLog, Profile
from .notifikasi import (DAFTAR, PEMBUAT_PER_TIPE, NotifHadiah, NotifPoinMasuk, PembuatNotifikasi,
                         kirim_notifikasi_poin, pembuat_untuk)
from .tests import FAST_HASH, buat_user


def buat_pesanan(user, **kw):
    data = dict(nama='Nadia Aulia', whatsapp='081234567890', layanan='express', berat=Decimal('5'),
                alamat='Jl. Contoh No. 1', user=user, asal='akun')
    data.update(kw)
    return Booking.objects.create(**data)


def selesaikan(booking):
    booking.status = 'selesai'
    booking.save()
    return booking


def buat_notif(user, **kw):
    data = dict(judul='Cucian sedang diproses', isi='Pesanan #X sedang diproses.', tipe='diproses')
    data.update(kw)
    return Notifikasi.objects.create(user=user, **data)


@FAST_HASH
class HalamanNotifikasiTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('notifikasi')

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_hanya_menampilkan_notifikasi_milik_sendiri(self):
        milik = buat_notif(self.user)
        buat_notif(buat_user('lain@example.com'), judul='Rahasia orang lain')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(list(r.context['halaman']), [milik])
        self.assertNotContains(r, 'Rahasia orang lain')

    def test_banner_menyapa_dengan_nama_depan_dan_sidebar_aktif(self):
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn('Kabar terbaru untukmu, Nadia.', html)
        self.assertIn(f'is-active" href="{self.url}" aria-current="page"', html)

    def test_terbaru_ditampilkan_lebih_dulu(self):
        lama = buat_notif(self.user, judul='Lama')
        baru = buat_notif(self.user, judul='Baru')
        self.client.force_login(self.user)
        self.assertEqual(list(self.client.get(self.url).context['halaman']), [baru, lama])

    def test_keadaan_kosong(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), 'Belum ada notifikasi')
        self.assertContains(self.client.get(self.url, {'filter': 'poin'}), 'Tidak ada notifikasi di sini')

    def test_filter_belum_pesanan_poin_dan_nilai_tak_dikenal(self):
        baca = buat_notif(self.user, judul='Sudah dibaca', dibaca=True)
        pesanan = buat_notif(self.user, judul='Status')
        poin = buat_notif(self.user, judul='+5 poin', tipe='poin')
        hadiah = buat_notif(self.user, judul='Hadiah', tipe='hadiah', dibaca=True)
        self.client.force_login(self.user)

        def hasil(**params):
            return set(self.client.get(self.url, params).context['halaman'])

        self.assertEqual(hasil(), {baca, pesanan, poin, hadiah})
        self.assertEqual(hasil(filter='belum'), {pesanan, poin})
        self.assertEqual(hasil(filter='pesanan'), {baca, pesanan})
        self.assertEqual(hasil(filter='poin'), {poin, hadiah})
        self.assertEqual(hasil(filter='ngawur'), {baca, pesanan, poin, hadiah})

    def test_chip_menampilkan_jumlah_semua_dan_belum_dibaca(self):
        buat_notif(self.user, dibaca=True)
        buat_notif(self.user)
        buat_notif(self.user, tipe='poin')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.context['kotak'].tab[:2], [('semua', 'Semua (3)'), ('belum', 'Belum dibaca (2)')])
        self.assertContains(r, '2 notifikasi belum dibaca')

    def test_pembagian_halaman_mempertahankan_filter(self):
        for i in range(12):
            buat_notif(self.user, judul=f'N{i}', tipe='poin')
        self.client.force_login(self.user)
        r = self.client.get(self.url, {'filter': 'poin'})
        self.assertEqual(len(r.context['halaman']), KotakNotifikasi.UKURAN_HALAMAN)
        self.assertContains(r, 'href="?filter=poin&amp;page=2"')
        self.assertEqual(len(self.client.get(self.url, {'filter': 'poin', 'page': 2}).context['halaman']), 2)
        self.assertContains(self.client.get(self.url), 'href="?page=2"')  # filter Semua: tanpa awalan filter
        # halaman ngawur tidak membuat galat
        self.assertEqual(self.client.get(self.url, {'page': 'abc'}).status_code, 200)

    def test_tandai_semua_dibaca_hanya_milik_sendiri_dan_filter_tetap(self):
        a, b = buat_notif(self.user), buat_notif(self.user, tipe='poin')
        lain = buat_notif(buat_user('lain@example.com'))
        self.client.force_login(self.user)
        r = self.client.post(f'{self.url}?filter=poin', {'aksi': 'tandai_semua'})
        self.assertRedirects(r, f'{self.url}?filter=poin')
        for n in (a, b, lain):
            n.refresh_from_db()
        self.assertEqual((a.dibaca, b.dibaca, lain.dibaca), (True, True, False))
        self.assertContains(self.client.get(self.url), 'Semua notifikasi sudah dibaca')

    def test_tandai_semua_tanpa_notifikasi_baru_memberi_pesan_dan_tombol_nonaktif(self):
        buat_notif(self.user, dibaca=True)
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), 'type="submit" disabled')
        r = self.client.post(self.url, {'aksi': 'tandai_semua'}, follow=True)
        self.assertContains(r, 'Semua notifikasi sudah dibaca.')

    def test_post_tanpa_aksi_dikenal_tidak_mengubah_apa_pun(self):
        n = buat_notif(self.user)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(self.url, {'aksi': 'hapus'}).status_code, 200)
        n.refresh_from_db()
        self.assertFalse(n.dibaca)

    def test_lonceng_bertitik_selama_ada_yang_belum_dibaca(self):
        self.client.force_login(self.user)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'bell-dot')
        buat_notif(self.user)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertIn('bell-dot', html)
        self.assertIn(f'<a class="bell" href="{self.url}" aria-label="Notifikasi (1 belum dibaca)"', html)
        Notifikasi.objects.update(dibaca=True)
        self.assertNotContains(self.client.get(reverse('dashboard')), 'bell-dot')

    def test_notifikasi_tidak_lagi_bertanda_segera_hadir(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('dashboard')).content.decode()
        self.assertNotIn('is-soon" title="Segera hadir"><svg class="ic"><use href="#i-bell"', html)


@FAST_HASH
class IkonDanTautanTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.client.force_login(self.user)

    def _kartu(self):
        return list(self.client.get(reverse('notifikasi')).context['halaman'])[0]

    def test_status_pesanan_menuju_detail_pesanan_dengan_ikon_sendiri(self):
        b = buat_pesanan(self.user)
        b.status = 'diproses'
        b.save()
        n = self._kartu()
        self.assertEqual(n.ikon, 'i-iron')
        self.assertEqual(n.tautan, ('Lihat detail pesanan', f"{reverse('cari_pesanan')}?q={b.resi}"))

    def test_pesanan_selesai_mengajak_pesan_lagi_layanan_yang_sama(self):
        b = selesaikan(buat_pesanan(self.user, layanan='dry'))
        n = Notifikasi.objects.get(judul='Pesanan selesai')
        self.assertEqual(pembuat_untuk(n.tipe).tautan(n), ('Pesan lagi', f"{reverse('booking')}?layanan=dry"))
        self.assertEqual(b.status, 'selesai')

    def test_notifikasi_poin_dan_hadiah_menuju_halaman_poin(self):
        for tipe, ikon in (('poin', 'i-sparkles'), ('hadiah', 'i-gift')):
            n = buat_notif(self.user, tipe=tipe)
            pembuat = pembuat_untuk(tipe)
            self.assertEqual(pembuat.ikon, ikon)
            self.assertEqual(pembuat.tautan(n)[1], reverse('poin_hadiah'))

    def test_notifikasi_lama_tanpa_tipe_memakai_ikon_lonceng(self):
        buat_pesanan(self.user)
        Notifikasi.objects.update(tipe='')
        n = self._kartu()
        self.assertEqual(n.ikon, 'i-bell')
        self.assertEqual(n.tautan[0], 'Lihat detail pesanan')

    def test_pesanan_terhapus_tidak_menampilkan_tautan_dan_tidak_galat(self):
        b = buat_pesanan(self.user)
        b.delete()  # FK booking SET_NULL: notifikasi tetap ada
        r = self.client.get(reverse('notifikasi'))
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(self._kartu().tautan)

    def test_setiap_tipe_unik_dan_ikonnya_ada_di_sprite(self):
        for status, kelas in DAFTAR.items():
            self.assertEqual(kelas.tipe, status)
        self.assertEqual(len(PEMBUAT_PER_TIPE), len(DAFTAR) + 2)
        self.assertIs(pembuat_untuk('tidak-ada'), PembuatNotifikasi)
        sprite = (settings.BASE_DIR / 'laundry/templates/laundry/dashboard_base.html').read_text(encoding='utf-8')
        for kelas in PEMBUAT_PER_TIPE.values():
            self.assertIn(f'id="{kelas.ikon}"', sprite, kelas.__name__)


@FAST_HASH
class NotifikasiPoinHadiahTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def test_pesanan_selesai_membuat_notifikasi_poin_dengan_saldo(self):
        b = selesaikan(buat_pesanan(self.user))  # 60.000 -> 60 poin
        n = Notifikasi.objects.get(tipe='poin')
        self.assertEqual(n.judul, '+60 poin masuk ke akunmu')
        self.assertEqual(n.isi, f'Pesanan #{b.resi} sudah selesai. Saldo poinmu sekarang 60 poin.')
        self.assertEqual((n.user, n.booking, n.kategori, n.dibaca), (self.user, b, 'Poin & hadiah', False))

    def test_simpan_ulang_tidak_menggandakan_notifikasi_poin(self):
        b = selesaikan(buat_pesanan(self.user))
        b.save()
        b.save()
        self.assertEqual(Notifikasi.objects.filter(tipe='poin').count(), 1)
        self.assertEqual(kirim_notifikasi_poin(b), [])

    def test_tanpa_poin_atau_tanpa_akun_tidak_ada_notifikasi_poin(self):
        selesaikan(buat_pesanan(self.user, layanan='reguler', berat=Decimal('0.1')))  # Rp700 -> 0 poin
        selesaikan(buat_pesanan(None, asal='tamu'))
        self.assertFalse(Notifikasi.objects.filter(tipe__in=Notifikasi.TIPE_POIN).exists())
        self.assertFalse(PoinLog.objects.exists() and Notifikasi.objects.filter(tipe='poin').exists())

    def test_poin_yang_masuk_belakangan_tetap_diberitahukan(self):
        b = selesaikan(buat_pesanan(self.user, layanan='reguler', berat=Decimal('0.1')))
        self.assertFalse(Notifikasi.objects.filter(tipe='poin').exists())
        b.terapkan_tagihan(Decimal('5'))  # 5 pcs reguler = Rp35.000 -> 35 poin, status tidak berubah
        self.assertEqual(Notifikasi.objects.get(tipe='poin').judul, '+35 poin masuk ke akunmu')

    def test_saldo_melewati_batas_hadiah_membuat_notifikasi_hadiah_sekali_saja(self):
        b = selesaikan(buat_pesanan(self.user, berat=Decimal('42')))  # 504.000 -> 504 poin, lewat 500
        h = Notifikasi.objects.get(tipe='hadiah')
        self.assertEqual(h.judul, 'Hadiah kecil menantimu!')
        self.assertEqual(h.isi, 'Saldo 504 poinmu cukup untuk voucher Rp 5.000 (500 poin). '
                                'Voucher Rp 10.000 perlu 496 poin lagi.')
        self.assertEqual((h.booking, h.kategori), (b, 'Poin & hadiah'))
        selesaikan(buat_pesanan(self.user, berat=Decimal('10')))  # +120 poin, tidak melewati batas baru
        self.assertEqual(Notifikasi.objects.filter(tipe='hadiah').count(), 1)

    def test_melewati_dua_batas_sekaligus_menyebut_hadiah_tertinggi_dan_hadiah_berikutnya(self):
        selesaikan(buat_pesanan(self.user, berat=Decimal('90')))  # 1.080.000 -> 1.080 poin
        h = Notifikasi.objects.get(tipe='hadiah')
        self.assertEqual(h.isi, 'Saldo 1080 poinmu cukup untuk voucher Rp 10.000 (1000 poin). '
                                'Saldo DANA Rp 10.000 perlu 420 poin lagi.')

    def test_saldo_melewati_semua_hadiah_menyebut_hadiah_tertinggi_tanpa_hadiah_berikutnya(self):
        selesaikan(buat_pesanan(self.user, berat=Decimal('300')))  # 3.600.000 -> 3.600 poin
        h = Notifikasi.objects.get(tipe='hadiah')
        self.assertEqual(h.isi, 'Saldo 3600 poinmu cukup untuk saldo GoPay Rp 25.000 (3500 poin).')

    def test_kelas_pembuat_poin_dan_hadiah_mewarisi_kelas_dasar(self):
        self.assertTrue(issubclass(NotifPoinMasuk, PembuatNotifikasi))
        self.assertTrue(issubclass(NotifHadiah, PembuatNotifikasi))


@FAST_HASH
class WaktuTampilDanMigrasiTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def _waktu(self, **selisih):
        n = buat_notif(self.user)
        Notifikasi.objects.filter(pk=n.pk).update(dibuat=timezone.now() - timedelta(**selisih))
        n.refresh_from_db()
        return n.waktu_tampil

    def test_hari_ini_kemarin_dan_tanggal_lengkap(self):
        self.assertTrue(self._waktu(minutes=1).startswith('Hari ini \u00b7 '))
        self.assertTrue(self._waktu(days=1).startswith('Kemarin \u00b7 '))
        lama = timezone.localtime(timezone.now() - timedelta(days=10))
        self.assertTrue(self._waktu(days=10).startswith(f'{lama.day} '))
        self.assertRegex(self._waktu(days=10), r'^\d{1,2} \w+ \d{4} \u00b7 \d{2}\.\d{2}$')

    def test_migrasi_mengisi_tipe_notifikasi_lama_dari_judul(self):
        migrasi = importlib.import_module('laundry.migrations.0008_notifikasi_tipe')
        lama = buat_notif(self.user, judul='Cucian sedang diproses', tipe='')
        lain = buat_notif(self.user, judul='Judul tak dikenal', tipe='')
        migrasi.isi_tipe_dari_judul(apps, None)
        lama.refresh_from_db()
        lain.refresh_from_db()
        self.assertEqual((lama.tipe, lain.tipe), ('diproses', ''))
        # Judul tipe 'menunggu' diganti sesudah migrasi 0008 dibuat; baris lama di database tetap memakai judul lama,
        # jadi peta migrasi sengaja mempertahankannya.
        judul_lama = {'menunggu': 'Pesanan diterima'}
        for judul, tipe in migrasi.JUDUL_KE_TIPE.items():
            self.assertEqual(judul_lama.get(tipe, DAFTAR[tipe].judul), judul)  # peta migrasi sama dengan judul di kode
