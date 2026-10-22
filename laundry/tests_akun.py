"""Tes untuk: Akun saya, pencarian pesanan, tagihan admin, notifikasi, dan konfigurasi produksi."""
import os
import subprocess
import sys
from decimal import Decimal

from django.conf import settings
from django.test import TestCase
from django.urls import reverse

from .models import Alamat, Booking, Notifikasi, PoinLog, Profile, TagihanTerkunci
from .notifikasi import DAFTAR, NotifDiterima, PembuatNotifikasi
from .tests import FAST_HASH, buat_booking, buat_user


def buat_alamat(user, **kw):
    data = dict(label='Rumah', nama_penerima='Nadia Aulia', whatsapp='081234567890',
                alamat_lengkap='Jl. Pramuka No. 12', kecamatan='Samarinda Ulu', kota='Samarinda',
                kode_pos='75123', catatan_kurir='Pagar putih')
    data.update(kw)
    return Alamat.objects.create(user=user, **data)


def buat_pesanan(user, **kw):
    """Pesanan milik akun (akun terpasang sejak dibuat, seperti booking oleh pelanggan yang login)."""
    data = dict(nama='Nadia Aulia', whatsapp='081234567890', layanan='express', berat=Decimal('5'),
                alamat='Jl. Contoh No. 1', user=user, asal='akun')
    data.update(kw)
    return Booking.objects.create(**data)


@FAST_HASH
class AkunSayaTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        Profile.objects.filter(user=self.user).update(whatsapp='6281234567890')
        self.url = reverse('akun_saya')

    def _data(self, **kw):
        data = {'nama_lengkap': 'Nadia Aulia Putri', 'nama_panggilan': 'Nadia', 'whatsapp': '0812 3456 7890',
                'tanggal_lahir': '2000-05-12'}
        data.update(kw)
        return data

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        admin = buat_user('admin@example.com', role=Profile.Role.ADMIN)
        self.client.force_login(admin)
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_tampil_data_awal_dan_email_hanya_baca(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Informasi pribadi')
        self.assertEqual(r.context['form'].initial['nama_lengkap'], 'Nadia Aulia')
        self.assertContains(r, 'value="nadia@example.com" readonly')
        self.assertNotIn('email', r.context['form'].fields)

    def test_simpan_memperbarui_user_dan_profil(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, self._data(email='hacker@example.com'))
        self.assertRedirects(r, self.url)
        self.user.refresh_from_db()
        self.assertEqual((self.user.first_name, self.user.last_name), ('Nadia', 'Aulia Putri'))
        self.assertEqual(self.user.email, 'nadia@example.com')  # email tidak bisa diubah lewat form
        p = Profile.objects.get(user=self.user)
        self.assertEqual((p.nama_panggilan, p.whatsapp, str(p.tanggal_lahir)), ('Nadia', '6281234567890', '2000-05-12'))

    def test_akun_saya_tidak_mengubah_alamat(self):
        """Alamat diurus di halaman Alamat saya; form Akun saya tidak boleh menyentuhnya."""
        alamat = buat_alamat(self.user, alamat_lengkap='Jl. Lama No. 1')
        self.client.force_login(self.user)
        self.client.post(self.url, self._data(alamat_lengkap='Jl. Baru No. 9', label='Kantor'))
        alamat.refresh_from_db()
        self.assertEqual((alamat.label, alamat.alamat_lengkap), ('Rumah', 'Jl. Lama No. 1'))
        form = self.client.get(self.url).context['form']
        self.assertEqual(set(form.fields), {'nama_lengkap', 'nama_panggilan', 'whatsapp', 'tanggal_lahir'})

    def test_kartu_alamat_hanya_baca_dengan_tautan_ke_alamat_saya(self):
        buat_alamat(self.user)
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Jl. Pramuka No. 12, Samarinda Ulu, Samarinda')
        self.assertContains(r, '0812 3456 7890')                      # nomor tampil dalam format lokal
        self.assertContains(r, 'Pagar putih')
        self.assertContains(r, f"href=\"{reverse('alamat_saya')}\"")
        self.assertNotContains(r, 'name="alamat_lengkap"')

    def test_kartu_poin_memakai_voucher_rp_10000(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(self.url), 'Menuju voucher Rp 10.000')

    def test_nama_wajib_dan_tanggal_lahir_tidak_boleh_masa_depan(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, self._data(nama_lengkap='', tanggal_lahir='2999-01-01'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Nama lengkap wajib diisi.')
        self.assertContains(r, 'Tanggal lahir tidak valid.')
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Nadia')  # tidak ada yang tersimpan

    def test_whatsapp_milik_akun_lain_ditolak_tetapi_milik_sendiri_boleh(self):
        lain = buat_user('lain@example.com')
        Profile.objects.filter(user=lain).update(whatsapp='6285555000111')
        self.client.force_login(self.user)
        r = self.client.post(self.url, self._data(whatsapp='085555000111'))
        self.assertContains(r, 'Nomor ini sudah dipakai akun lain.')
        r = self.client.post(self.url, self._data(whatsapp='081234567890'))  # nomor sendiri
        self.assertRedirects(r, self.url)

    def test_whatsapp_tidak_valid_ditolak(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.post(self.url, self._data(whatsapp='123')), 'Nomor WhatsApp tidak valid')

    def test_alamat_tersimpan_mengisi_form_booking(self):
        buat_alamat(self.user)
        self.client.force_login(self.user)
        r = self.client.get(reverse('booking'))
        self.assertEqual(r.context['form'].initial['alamat'], 'Jl. Pramuka No. 12, Samarinda Ulu, Samarinda')

    def test_menu_akun_saya_ada_di_sidebar(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('dashboard')), f'href="{self.url}"')


@FAST_HASH
class AlamatModelTests(TestCase):
    """Aturan di model Alamat: satu alamat utama per akun."""

    def setUp(self):
        self.user = buat_user()

    def test_alamat_pertama_otomatis_utama_dan_berikutnya_tidak(self):
        a1, a2 = buat_alamat(self.user), buat_alamat(self.user, label='Kantor')
        self.assertEqual((a1.utama, a2.utama), (True, False))
        self.assertEqual(Alamat.utama_untuk(self.user), a1)

    def test_jadikan_utama_memindahkan_status(self):
        a1, a2 = buat_alamat(self.user), buat_alamat(self.user, label='Kantor')
        a2.jadikan_utama()
        a1.refresh_from_db(), a2.refresh_from_db()
        self.assertEqual((a1.utama, a2.utama), (False, True))
        self.assertEqual(Alamat.objects.filter(user=self.user, utama=True).count(), 1)

    def test_database_menolak_dua_alamat_utama(self):
        from django.db import IntegrityError, transaction
        buat_alamat(self.user)
        with self.assertRaises(IntegrityError), transaction.atomic():
            Alamat.objects.create(user=self.user, label='X', nama_penerima='N', whatsapp='6281', alamat_lengkap='Jl. X', utama=True)

    def test_hapus_alamat_utama_memilih_pengganti(self):
        a1, a2 = buat_alamat(self.user), buat_alamat(self.user, label='Kantor')
        a1.hapus_dan_pilih_pengganti()
        a2.refresh_from_db()
        self.assertTrue(a2.utama)

    def test_hapus_alamat_biasa_tidak_mengubah_utama(self):
        a1, a2 = buat_alamat(self.user), buat_alamat(self.user, label='Kantor')
        a2.hapus_dan_pilih_pengganti()
        a1.refresh_from_db()
        self.assertTrue(a1.utama)

    def test_tampilan_alamat_dan_whatsapp(self):
        a = buat_alamat(self.user)
        self.assertEqual(a.baris_alamat, 'Jl. Pramuka No. 12, Samarinda Ulu, Samarinda')
        self.assertEqual(a.whatsapp, '6281234567890')            # tersimpan ternormalisasi
        self.assertEqual(a.whatsapp_tampil, '0812 3456 7890')    # tampil format lokal


@FAST_HASH
class AlamatSayaTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('alamat_saya')

    def _data(self, **kw):
        data = {'aksi': 'simpan', 'label': 'Kos', 'nama_penerima': 'Nadia Aulia', 'whatsapp': '0812 3456 7890',
                'alamat_lengkap': 'Jl. M. Yamin No. 15', 'kota': 'Samarinda', 'kecamatan': 'Samarinda Ulu',
                'kode_pos': '75123', 'catatan_kurir': 'Bangunan kedua, pagar abu-abu'}
        data.update(kw)
        return data

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_halaman_kosong_dan_form_terisi_saran_dari_akun(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Alamat tersimpan (0)')
        self.assertContains(r, 'Tambah alamat baru')
        self.assertEqual(r.context['form'].initial['nama_penerima'], 'Nadia Aulia')
        self.assertContains(r, 'Kalimantan Timur')

    def test_tambah_alamat_pertama_menjadi_utama(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post(self.url, self._data()), self.url)
        a = Alamat.objects.get()
        self.assertEqual((a.label, a.kecamatan, a.kota, a.kode_pos, a.provinsi, a.whatsapp, a.utama),
                         ('Kos', 'Samarinda Ulu', 'Samarinda', '75123', 'Kalimantan Timur', '6281234567890', True))

    def test_alamat_kedua_tidak_menggeser_utama_kecuali_dicentang(self):
        pertama = buat_alamat(self.user)
        self.client.force_login(self.user)
        self.client.post(self.url, self._data(label='Kantor'))
        pertama.refresh_from_db()
        self.assertTrue(pertama.utama)
        self.client.post(self.url, self._data(label='Kos', utama='on'))
        pertama.refresh_from_db()
        self.assertFalse(pertama.utama)
        self.assertEqual(Alamat.objects.get(utama=True).label, 'Kos')
        self.assertEqual(Alamat.objects.filter(user=self.user, utama=True).count(), 1)

    def test_daftar_menampilkan_utama_dan_lainnya_sesuai_desain(self):
        buat_alamat(self.user)
        buat_alamat(self.user, label='Kantor', alamat_lengkap='Jl. S. Parman No. 8')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Alamat tersimpan (2)')
        self.assertContains(r, 'Rumah &middot; Alamat utama')
        self.assertContains(r, 'Dipakai sebagai alamat utama')
        self.assertContains(r, 'Jadikan utama')
        self.assertContains(r, 'Hapus')
        self.assertContains(r, 'Pesanan aktif tetap memakai alamat saat dipesan')

    def test_ubah_alamat_memuat_data_dan_menyimpan_perubahan(self):
        a = buat_alamat(self.user)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {'ubah': a.pk})
        self.assertContains(r, 'Ubah alamat')
        self.assertEqual(r.context['form'].instance, a)
        self.client.post(self.url, self._data(alamat_id=a.pk, label='Rumah Baru'))
        a.refresh_from_db()
        self.assertEqual((a.label, Alamat.objects.count(), a.utama), ('Rumah Baru', 1, True))

    def test_tidak_bisa_mengubah_atau_menghapus_alamat_orang_lain(self):
        lain = buat_user('lain@example.com')
        milik_lain = buat_alamat(lain)
        self.client.force_login(self.user)
        for data in (self._data(alamat_id=milik_lain.pk, label='Diretas'), {'aksi': 'hapus', 'alamat_id': milik_lain.pk},
                     {'aksi': 'utama', 'alamat_id': milik_lain.pk}, self._data(alamat_id='abc')):
            self.client.post(self.url, data)
        milik_lain.refresh_from_db()
        self.assertEqual((milik_lain.label, Alamat.objects.count()), ('Rumah', 1))
        self.assertEqual(self.client.get(self.url, {'ubah': milik_lain.pk}).context['sedang_ubah'], None)

    def test_jadikan_utama_dan_hapus_lewat_post(self):
        a1, a2 = buat_alamat(self.user), buat_alamat(self.user, label='Kantor')
        self.client.force_login(self.user)
        self.client.post(self.url, {'aksi': 'utama', 'alamat_id': a2.pk})
        a2.refresh_from_db()
        self.assertTrue(a2.utama)
        self.client.post(self.url, {'aksi': 'hapus', 'alamat_id': a2.pk})   # hapus yang utama -> a1 jadi utama
        a1.refresh_from_db()
        self.assertEqual((Alamat.objects.count(), a1.utama), (1, True))

    def test_validasi_form(self):
        self.client.force_login(self.user)
        kasus = [
            ({'label': ''}, 'Label alamat wajib diisi.'),
            ({'nama_penerima': ''}, 'Nama penerima wajib diisi.'),
            ({'whatsapp': '123'}, 'Nomor WhatsApp tidak valid'),
            ({'alamat_lengkap': 'Jl. A'}, 'selengkap mungkin'),
            ({'kode_pos': '751'}, 'Kode pos terdiri dari 5 angka.'),
            ({'kota': 'Balikpapan'}, 'Pilih kecamatan yang sesuai dengan kota.'),   # Samarinda Ulu bukan di Balikpapan
            ({'kecamatan': ''}, 'Pilih kecamatan.'),
        ]
        for ubah, pesan in kasus:
            self.assertContains(self.client.post(self.url, self._data(**ubah)), pesan, msg_prefix=str(ubah))
        self.assertFalse(Alamat.objects.exists())

    def test_kota_lain_dengan_kecamatannya_diterima_dan_kode_pos_boleh_kosong(self):
        self.client.force_login(self.user)
        self.client.post(self.url, self._data(kota='Balikpapan', kecamatan='Balikpapan Selatan', kode_pos=''))
        self.assertEqual(Alamat.objects.get().kecamatan, 'Balikpapan Selatan')

    def test_pilihan_kecamatan_mengikuti_kota(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, self._data(kota='Bontang', kecamatan='Salah'))
        pilihan = [v for v, _ in r.context['form'].fields['kecamatan'].choices]
        self.assertEqual(pilihan, ['', 'Bontang Barat', 'Bontang Selatan', 'Bontang Utara'])

    def test_batas_jumlah_alamat(self):
        from .services import MAKS_ALAMAT
        for i in range(MAKS_ALAMAT):
            buat_alamat(self.user, label=f'A{i}')
        self.client.force_login(self.user)
        self.assertContains(self.client.post(self.url, self._data()), 'sudah mencapai batas')
        self.assertEqual(Alamat.objects.filter(user=self.user).count(), MAKS_ALAMAT)

    def test_sidebar_alamat_saya_aktif_dan_bisa_diklik(self):
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn(f'class="nav-item is-active" href="{self.url}"', html)
        self.assertIn(f'href="{self.url}"', self.client.get(reverse('dashboard')).content.decode())

    def test_kartu_alamat_di_beranda_dan_pesanan_saya_memakai_alamat_utama(self):
        buat_alamat(self.user, alamat_lengkap='Jl. Utama No. 7')
        buat_alamat(self.user, label='Kantor', alamat_lengkap='Jl. Kantor No. 9')
        buat_pesanan(self.user, alamat='Jl. Pesanan No. 99')
        self.client.force_login(self.user)
        for nama in ('dashboard', 'pesanan_saya'):
            html = self.client.get(reverse(nama)).content.decode()
            self.assertIn('Jl. Utama No. 7', html, nama)
            self.assertNotIn('Jl. Kantor No. 9', html, nama)
            self.assertNotIn('Jl. Pesanan No. 99', html, nama)

    def test_pesanan_saya_memakai_alamat_pesanan_bila_belum_punya_alamat(self):
        buat_pesanan(self.user, alamat='Jl. Pesanan No. 99')
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('pesanan_saya')), 'Jl. Pesanan No. 99')

    def test_whatsapp_profil_tampil(self):
        p = Profile.objects.get(user=self.user)
        for tersimpan, tampil in (('6281234567890', '0812 3456 7890'), ('', '')):
            p.whatsapp = tersimpan
            self.assertEqual(p.whatsapp_tampil, tampil)


@FAST_HASH
class CariPesananTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('cari_pesanan')

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_menemukan_pesanan_sendiri_semua_status(self):
        aktif = buat_pesanan(self.user)
        selesai = buat_pesanan(self.user, status='selesai')
        self.client.force_login(self.user)
        for kata in (aktif.resi, aktif.resi.lower(), f'#{aktif.resi}', aktif.resi[-4:]):
            r = self.client.get(self.url, {'q': kata})
            self.assertIn(aktif, r.context['hasil'], kata)
        r = self.client.get(self.url, {'q': selesai.resi})
        self.assertEqual(r.context['hasil'], [selesai])

    def test_tidak_menampilkan_pesanan_orang_lain(self):
        lain = buat_user('lain@example.com')
        milik_lain = buat_pesanan(lain)
        self.client.force_login(self.user)
        r = self.client.get(self.url, {'q': milik_lain.resi})
        self.assertEqual(r.context['hasil'], [])
        self.assertContains(r, 'Pesanan tidak ditemukan')

    def test_tanpa_kata_kunci_menampilkan_petunjuk(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Cari nomor pesanan')
        self.assertEqual(r.context['hasil'], [])

    def test_kolom_pencarian_header_aktif(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('pesanan_saya')).content.decode()
        self.assertIn(f'action="{self.url}"', html)
        self.assertNotIn('disabled>', html.split('Cari nomor pesanan')[0][-200:])


@FAST_HASH
class TagihanTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def test_total_memakai_berat_timbang_dan_koreksi(self):
        b = buat_pesanan(self.user)                       # express 12.000 x 5 = 60.000 (estimasi)
        self.assertEqual((b.berat_efektif, b.total), (Decimal('5'), 60000))
        b.terapkan_tagihan(Decimal('6'), -2000, 'Potongan loyal')   # 72.000 - 2.000
        b.refresh_from_db()
        self.assertEqual((b.berat_efektif, b.dasar, b.total), (Decimal('6.0'), 72000, 70000))
        self.assertEqual(b.koreksi_fmt, '-Rp 2.000')

    def test_total_tidak_pernah_negatif(self):
        b = buat_pesanan(self.user, layanan='setrika', berat=Decimal('1'))
        b.terapkan_tagihan(Decimal('1'), -999999, 'Uji')
        self.assertEqual(b.total, 0)

    def test_tagihan_dikunci_setelah_poin_diberikan(self):
        b = buat_pesanan(self.user, status='selesai')     # poin langsung masuk
        self.assertTrue(PoinLog.objects.filter(booking=b).exists())
        self.assertTrue(b.tagihan_terkunci)
        with self.assertRaises(TagihanTerkunci):
            b.terapkan_tagihan(Decimal('9'))

    def test_tagihan_yang_diperbesar_bisa_memicu_poin_bila_belum_pernah_dapat(self):
        b = buat_pesanan(self.user, layanan='setrika', berat=Decimal('0.1'), status='selesai')  # 500 -> 0 poin
        self.assertFalse(PoinLog.objects.exists())
        b.terapkan_tagihan(Decimal('2'))                  # 10.000 -> 10 poin
        self.assertEqual(PoinLog.objects.get().jumlah, 10)

    def _admin(self):
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))

    def test_admin_menyimpan_tagihan_lewat_halaman_detail(self):
        b = buat_pesanan(self.user)
        self._admin()
        url = reverse('admin_pesanan_detail', args=[b.pk])
        r = self.client.post(url, {'aksi': 'tagihan', 'berat_final': '6', 'koreksi_harga': '5000',
                                   'catatan_koreksi': 'Noda membandel'})
        self.assertRedirects(r, url)
        b.refresh_from_db()
        self.assertEqual((b.total, b.catatan_koreksi), (77000, 'Noda membandel'))
        self.assertContains(self.client.get(url), 'Koreksi harga')

    def test_koreksi_tanpa_alasan_ditolak_dan_tidak_menyimpan(self):
        b = buat_pesanan(self.user)
        self._admin()
        r = self.client.post(reverse('admin_pesanan_detail', args=[b.pk]),
                             {'aksi': 'tagihan', 'berat_final': '6', 'koreksi_harga': '5000', 'catatan_koreksi': ''})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Isi alasan koreksi harga.')
        b.refresh_from_db()
        self.assertIsNone(b.berat_final)

    def test_halaman_menampilkan_kunci_bila_poin_sudah_diberikan(self):
        b = buat_pesanan(self.user, status='selesai')
        self._admin()
        r = self.client.post(reverse('admin_pesanan_detail', args=[b.pk]), {'aksi': 'tagihan', 'berat_final': '9'},
                             follow=True)
        self.assertContains(r, 'tagihan tidak bisa diubah lagi')
        b.refresh_from_db()
        self.assertIsNone(b.berat_final)

    def test_pelanggan_biasa_tidak_boleh_mengubah_tagihan(self):
        b = buat_pesanan(self.user)
        self.client.force_login(self.user)
        r = self.client.post(reverse('admin_pesanan_detail', args=[b.pk]), {'aksi': 'tagihan', 'berat_final': '1'})
        self.assertEqual(r.status_code, 403)

    def test_form_status_lama_tetap_berfungsi(self):
        b = buat_pesanan(self.user)
        self._admin()
        self.client.post(reverse('admin_pesanan_detail', args=[b.pk]), {'status': 'diproses'})
        b.refresh_from_db()
        self.assertEqual(b.status, 'diproses')


@FAST_HASH
class NotifikasiTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def test_pesanan_baru_membuat_notifikasi_diterima(self):
        b = buat_pesanan(self.user)
        n = Notifikasi.objects.get()
        self.assertEqual((n.user, n.booking, n.judul, n.dibaca), (self.user, b, 'Pesanan dibuat', False))
        self.assertIn(b.resi, n.isi)

    def test_perubahan_status_membuat_satu_notifikasi_dan_simpan_ulang_tidak_menggandakan(self):
        b = buat_pesanan(self.user)
        b.status = 'diproses'
        b.save()
        b.save()
        self.assertEqual(Notifikasi.objects.count(), 2)
        self.assertEqual(Notifikasi.objects.first().judul, 'Cucian sedang diproses')

    def test_pesanan_tamu_tanpa_akun_tidak_membuat_notifikasi(self):
        buat_booking(status='diproses')
        self.assertFalse(Notifikasi.objects.exists())

    def test_notifikasi_selesai_menyebut_poin(self):
        b = buat_pesanan(self.user)                       # 60.000 -> 60 poin
        b.status = 'selesai'
        b.save()
        self.assertIn('+60 poin', Notifikasi.objects.get(judul='Pesanan selesai').isi)

    def test_belum_dibaca_dihitung_per_akun(self):
        buat_pesanan(self.user)
        buat_pesanan(buat_user('lain@example.com'))
        self.assertEqual(Notifikasi.jumlah_belum_dibaca(self.user), 1)

    def test_setiap_status_punya_pembuat_dengan_judul_berbeda(self):
        self.assertEqual(set(DAFTAR), {k for k, _ in Booking.STATUS})
        judul = {kelas.judul for kelas in DAFTAR.values()}
        self.assertEqual(len(judul), len(DAFTAR))
        self.assertTrue(all(issubclass(k, PembuatNotifikasi) for k in DAFTAR.values()))

    def test_kelas_abstrak_tidak_bisa_dibuat_langsung(self):
        with self.assertRaises(TypeError):
            PembuatNotifikasi(buat_pesanan(self.user))
        self.assertTrue(NotifDiterima(buat_pesanan(self.user)).isi())


class KonfigurasiProduksiTests(TestCase):
    def _jalankan(self, **env):
        lingkungan = {k: v for k, v in os.environ.items() if not k.startswith('DJANGO_')}
        lingkungan.update(env, DJANGO_SETTINGS_MODULE='config.settings')
        return subprocess.run(
            [sys.executable, '-c', "import config.settings as s; print(s.DEBUG, s.ALLOWED_HOSTS, getattr(s, 'SESSION_COOKIE_SECURE', False))"],
            cwd=settings.BASE_DIR, env=lingkungan, capture_output=True, text=True,
        )

    def test_produksi_tanpa_secret_key_ditolak(self):
        r = self._jalankan(DJANGO_DEBUG='False')
        self.assertNotEqual(r.returncode, 0)
        self.assertIn('DJANGO_SECRET_KEY', r.stderr)

    def test_produksi_memakai_env_dan_cookie_aman(self):
        r = self._jalankan(DJANGO_DEBUG='False', DJANGO_SECRET_KEY='x' * 50, DJANGO_ALLOWED_HOSTS='wuwashy.test')
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(r.stdout.strip(), "False ['wuwashy.test'] True")

    def test_mode_lokal_tanpa_env_tetap_jalan(self):
        r = self._jalankan()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(r.stdout.startswith('True'))
