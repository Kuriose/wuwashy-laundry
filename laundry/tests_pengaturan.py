"""Tes halaman Pengaturan (/pengaturan/): ganti kata sandi dan preferensi notifikasi."""
from django.test import TestCase
from django.urls import reverse

from .models import Profile
from .tests import FAST_HASH, buat_user


@FAST_HASH
class PengaturanTests(TestCase):
    def setUp(self):
        self.user = buat_user(password='kata-sandi-lama-1')
        self.url = reverse('pengaturan')

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_halaman_tampil_dengan_dua_form(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertIn('form_sandi', r.context)
        self.assertIn('form_notif', r.context)
        self.assertContains(r, 'Keamanan Akun')
        self.assertContains(r, 'Preferensi Notifikasi')

    def test_sidebar_pengaturan_aktif(self):
        self.client.force_login(self.user)
        html = self.client.get(self.url).content.decode()
        self.assertIn(f'is-active" href="{self.url}" aria-current="page"', html)
        self.assertNotIn('is-soon" title="Segera hadir"><svg class="ic"><use href="#i-gear"', html)

    # ---------- Ubah kata sandi ----------
    def test_ubah_sandi_berhasil_dan_sesi_tetap_aktif(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {
            'aksi': 'ubah_sandi',
            'kata_sandi_lama': 'kata-sandi-lama-1',
            'kata_sandi_baru': 'kata-sandi-baru-99',
            'konfirmasi_sandi': 'kata-sandi-baru-99',
        })
        self.assertRedirects(r, self.url)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('kata-sandi-baru-99'))
        # Sesi masih aktif setelah ganti sandi (update_session_auth_hash)
        self.assertEqual(self.client.get(self.url).status_code, 200)

    def test_ubah_sandi_gagal_jika_lama_salah(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {
            'aksi': 'ubah_sandi',
            'kata_sandi_lama': 'salah',
            'kata_sandi_baru': 'kata-sandi-baru-99',
            'konfirmasi_sandi': 'kata-sandi-baru-99',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'tidak cocok')
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password('kata-sandi-baru-99'))

    def test_ubah_sandi_gagal_jika_konfirmasi_tidak_cocok(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {
            'aksi': 'ubah_sandi',
            'kata_sandi_lama': 'kata-sandi-lama-1',
            'kata_sandi_baru': 'kata-sandi-baru-99',
            'konfirmasi_sandi': 'kata-sandi-beda',
        })
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Konfirmasi kata sandi tidak cocok')

    def test_ubah_sandi_gagal_jika_baru_terlalu_pendek(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {
            'aksi': 'ubah_sandi',
            'kata_sandi_lama': 'kata-sandi-lama-1',
            'kata_sandi_baru': 'abc',
            'konfirmasi_sandi': 'abc',
        })
        self.assertEqual(r.status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('kata-sandi-lama-1'))

    # ---------- Preferensi notifikasi ----------
    def test_nilai_default_notifikasi(self):
        p = Profile.untuk(self.user)
        self.assertTrue(p.notif_status_pesanan)
        self.assertTrue(p.notif_whatsapp)
        self.assertFalse(p.notif_email)
        self.assertTrue(p.notif_poin)
        self.assertFalse(p.notif_promo)

    def test_simpan_notif_mengubah_preferensi(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {
            'aksi': 'simpan_notif',
            'notif_email': 'on',
            'notif_promo': 'on',
            # notif_status_pesanan, notif_whatsapp, notif_poin TIDAK dikirim → False
        })
        self.assertRedirects(r, self.url)
        p = Profile.untuk(self.user)
        self.assertFalse(p.notif_status_pesanan)
        self.assertFalse(p.notif_whatsapp)
        self.assertTrue(p.notif_email)
        self.assertFalse(p.notif_poin)
        self.assertTrue(p.notif_promo)

    def test_simpan_notif_tidak_menyentuh_kata_sandi(self):
        self.client.force_login(self.user)
        self.client.post(self.url, {'aksi': 'simpan_notif', 'notif_email': 'on'})
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password('kata-sandi-lama-1'))

    def test_aksi_tidak_dikenal_tidak_mengubah_apa_pun(self):
        self.client.force_login(self.user)
        r = self.client.post(self.url, {'aksi': 'hapus_semua'})
        self.assertEqual(r.status_code, 200)
        p = Profile.untuk(self.user)
        self.assertTrue(p.notif_status_pesanan)

    def test_toggle_form_sudah_terisi_dari_profil(self):
        p = Profile.untuk(self.user)
        p.notif_email = True
        p.notif_status_pesanan = False
        p.save(update_fields=['notif_email', 'notif_status_pesanan'])
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertTrue(r.context['form_notif']['notif_email'].value())
        self.assertFalse(r.context['form_notif']['notif_status_pesanan'].value())

    # ---------- Sesi aktif ----------
    def test_sesi_aktif_menampilkan_ip_dan_waktu(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, REMOTE_ADDR='192.168.1.50')
        self.assertEqual(len(r.context['sesi_aktif']), 1)
        sesi = r.context['sesi_aktif'][0]
        self.assertEqual(sesi['ip'], '192.168.1.50')
        self.assertTrue(sesi['aktif'])
        self.assertContains(r, '192.168.1.50')

    def test_x_forwarded_for_dipakai_jika_ada(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url, HTTP_X_FORWARDED_FOR='10.0.0.1, 172.16.0.1')
        self.assertEqual(r.context['sesi_aktif'][0]['ip'], '10.0.0.1')
