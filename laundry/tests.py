from decimal import Decimal

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import panel
from .models import Booking, PoinLog, Profile
from .poin import cari_akun_dari_wa, saldo_poin
from .services import normalisasi_wa


class LandingPageTests(TestCase):
    def test_home_memuat_semua_bagian_navbar(self):
        html = self.client.get(reverse('home')).content.decode()
        for anchor in ('home', 'about', 'services', 'outlet'):
            self.assertIn(f'id="{anchor}"', html)
            self.assertIn(f'#{anchor}"', html)  # tautan navbar menuju bagian tsb
        self.assertIn('Outlet Kami', html)
        self.assertNotIn('Lacak', html)

    def test_url_lama_diarahkan_ke_anchor(self):
        for url, tujuan in (('/about/', '/#about'), ('/services/', '/#services')):
            self.assertRedirects(self.client.get(url), tujuan, fetch_redirect_response=False)

    def test_booking_page_ok(self):
        self.assertEqual(self.client.get(reverse('booking')).status_code, 200)


FAST_HASH = override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])


@FAST_HASH
class NavbarLoginIconTests(TestCase):
    def test_ikon_orang_menuju_login(self):
        for name in ('home', 'booking'):
            html = self.client.get(reverse(name)).content.decode()
            self.assertIn(f'href="{reverse("login")}" aria-label="Login"', html)

    def test_drawer_logout_hanya_saat_login(self):
        User.objects.create_user('budi', 'budi@example.com', 'rahasia-123')
        self.assertNotContains(self.client.get(reverse('home')), 'drawer-logout')
        self.client.login(username='budi', password='rahasia-123')
        self.assertContains(self.client.get(reverse('home')), 'drawer-logout')


@FAST_HASH
class LoginTests(TestCase):
    PASSWORD = 'rahasia-123'

    def setUp(self):
        self.user = User.objects.create_user('budi', 'Budi@Example.com', self.PASSWORD)
        self.url = reverse('login')

    def _post(self, **extra):
        data = {'username': 'budi@example.com', 'password': self.PASSWORD, 'remember_me': 'on'}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_halaman_login_tampil(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'Selamat datang kembali!')
        self.assertContains(r, 'Masukkan alamat email Anda')

    def test_login_email_tidak_peka_huruf(self):
        r = self._post(username='BUDI@example.COM')
        self.assertRedirects(r, reverse('dashboard'))
        self.assertEqual(int(self.client.session['_auth_user_id']), self.user.pk)

    def test_password_salah(self):
        r = self._post(password='salah')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Email atau kata sandi salah')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_email_tidak_terdaftar(self):
        r = self._post(username='nobody@example.com')
        self.assertContains(r, 'Email atau kata sandi salah')

    def test_email_tidak_valid(self):
        self.assertContains(self._post(username='bukan-email'), 'valid email address')

    def test_akun_nonaktif_ditolak(self):
        self.user.is_active = False
        self.user.save()
        self.assertContains(self._post(), 'Email atau kata sandi salah')

    def test_email_ganda_ditolak(self):
        User.objects.create_user('budi2', 'budi@example.com', self.PASSWORD)
        self.assertContains(self._post(), 'Email atau kata sandi salah')

    def test_remember_me(self):
        self._post()
        self.assertGreater(self.client.session.get_expiry_age(), 60 * 60 * 24)
        self.client.logout()
        self._post(remember_me='')
        self.assertTrue(self.client.session.get_expire_at_browser_close())

    def test_next_aman(self):
        self.assertRedirects(self._post(next='/booking/'), '/booking/')
        self.client.logout()
        r = self._post(next='https://evil.example/')
        self.assertRedirects(r, reverse('dashboard'))

    def test_sudah_login_dialihkan(self):
        self.client.login(username='budi', password=self.PASSWORD)
        self.assertRedirects(self.client.get(self.url), reverse('dashboard'))

    def test_logout_harus_post(self):
        self.client.login(username='budi', password=self.PASSWORD)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_superuser_username_tetap_bisa_login_admin(self):
        User.objects.create_superuser('admin', 'admin@example.com', 'admin-pass-123')
        self.assertTrue(self.client.login(username='admin', password='admin-pass-123'))


def buat_user(email='nadia@example.com', password='rahasia-123', role=Profile.Role.USER, **extra):
    user = User.objects.create_user(email, email, password, first_name=extra.pop('first_name', 'Nadia'),
                                    last_name=extra.pop('last_name', 'Aulia'), **extra)
    Profile.objects.filter(user=user).update(role=role)
    return user


@FAST_HASH
class RoleTests(TestCase):
    def test_akun_baru_otomatis_user(self):
        user = User.objects.create_user('a', 'a@example.com', 'x')
        self.assertEqual(user.profile.role, Profile.Role.USER)

    def test_superuser_otomatis_admin(self):
        user = User.objects.create_superuser('root', 'root@example.com', 'x')
        self.assertEqual(user.profile.role, Profile.Role.ADMIN)

    def test_profil_dibuat_bila_belum_ada(self):
        user = User.objects.create_user('a', 'a@example.com', 'x')
        Profile.objects.all().delete()
        self.assertEqual(Profile.untuk(user).role, Profile.Role.USER)


@FAST_HASH
class SignUpTests(TestCase):
    PASSWORD = 'Kain-Wangi-2026'

    def setUp(self):
        self.url = reverse('signup')

    def _post(self, **extra):
        data = {'full_name': 'Nadia Aulia', 'email': 'Nadia@Example.com', 'whatsapp': '0812-3456-7890',
                'password1': self.PASSWORD, 'password2': self.PASSWORD}
        data.update(extra)
        return self.client.post(self.url, data)

    def test_halaman_signup_tampil(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'Buat akunmu')
        self.assertContains(r, 'Confirm password')

    def test_link_signup_dari_login(self):
        self.assertContains(self.client.get(reverse('login')), f'href="{self.url}"')

    def test_signup_berhasil_membuat_user_dan_login(self):
        r = self._post()
        self.assertRedirects(r, reverse('dashboard'))
        user = User.objects.get(email='nadia@example.com')  # email disimpan huruf kecil
        self.assertEqual((user.first_name, user.last_name), ('Nadia', 'Aulia'))
        self.assertTrue(user.check_password(self.PASSWORD))
        self.assertEqual(user.profile.role, Profile.Role.USER)
        self.assertEqual(int(self.client.session['_auth_user_id']), user.pk)

    def test_role_tidak_bisa_diubah_lewat_form(self):
        self._post(role='ADMIN', is_superuser='on', is_staff='on')
        user = User.objects.get(email='nadia@example.com')
        self.assertEqual(user.profile.role, Profile.Role.USER)
        self.assertFalse(user.is_superuser or user.is_staff)

    def test_bisa_login_lagi_dengan_akun_baru(self):
        self._post()
        self.client.logout()
        r = self.client.post(reverse('login'), {'username': 'nadia@example.com', 'password': self.PASSWORD})
        self.assertRedirects(r, reverse('dashboard'))

    def test_email_sudah_terdaftar_tidak_peka_huruf(self):
        buat_user('nadia@example.com')
        r = self._post(email='NADIA@example.com')
        self.assertContains(r, 'sudah terdaftar')
        self.assertEqual(User.objects.count(), 1)

    def test_password_tidak_sama(self):
        r = self._post(password2='beda-sekali-123')
        self.assertContains(r, "passwords don")
        self.assertFalse(User.objects.exists())

    def test_password_lemah_ditolak(self):
        for lemah in ('pendek1', '12345678', 'password'):
            r = self._post(password1=lemah, password2=lemah)
            self.assertEqual(r.status_code, 200, lemah)
        self.assertFalse(User.objects.exists())

    def test_password_mirip_email_ditolak(self):
        r = self._post(email='nadia@example.com', password1='nadia@example.com', password2='nadia@example.com')
        self.assertEqual(r.status_code, 200)
        self.assertFalse(User.objects.exists())

    def test_field_wajib_dan_email_valid(self):
        r = self.client.post(self.url, {})
        self.assertContains(r, 'Masukkan nama lengkap Anda.')
        self.assertContains(r, 'Masukkan alamat email Anda.')
        self.assertContains(r, 'Buat kata sandi Anda.')
        self.assertContains(r, 'Masukkan nomor WhatsApp Anda.')
        self.assertContains(self._post(email='bukan-email'), 'valid email address')

    def test_sudah_login_dialihkan(self):
        buat_user()
        self.client.login(username='nadia@example.com', password='rahasia-123')
        self.assertRedirects(self.client.get(self.url), reverse('dashboard'))


@FAST_HASH
class DashboardTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.admin = buat_user('admin@example.com', role=Profile.Role.ADMIN, first_name='Admin', last_name='WuWashy')

    def test_anonim_diarahkan_ke_login(self):
        for name in ('dashboard', 'admin_dashboard'):
            url = reverse(name)
            self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_user_melihat_dashboard_pelanggan(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Halo, Nadia!')
        self.assertContains(r, 'Nadia Aulia')
        self.assertContains(r, 'Cuci Express')  # layanan tampil

    def test_dialog_keluar_memakai_post_ke_logout(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('dashboard'))
        self.assertContains(r, 'Yakin ingin keluar, Nadia?')
        self.assertContains(r, f'method="post" action="{reverse("logout")}"')

    def test_user_tidak_boleh_masuk_panel_admin(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('admin_dashboard')).status_code, 403)

    def test_admin_diarahkan_ke_panel_admin(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.get(reverse('dashboard')), reverse('admin_dashboard'))
        self.assertContains(self.client.get(reverse('admin_dashboard')), 'Ringkasan laundry')

    def test_login_user_dan_admin_masuk_ke_halaman_masing_masing(self):
        r = self.client.post(reverse('login'), {'username': 'nadia@example.com', 'password': 'rahasia-123'})
        self.assertRedirects(r, reverse('dashboard'))
        self.client.logout()
        r = self.client.post(reverse('login'), {'username': 'admin@example.com', 'password': 'rahasia-123'})
        self.assertRedirects(r, reverse('dashboard'), fetch_redirect_response=False)

    def test_logout_dari_dashboard_kembali_ke_website_dan_menutup_akses(self):
        self.client.force_login(self.user)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('home'))
        url = reverse('dashboard')
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_ikon_akun_navbar_menuju_dashboard_saat_login(self):
        self.client.force_login(self.user)
        html = self.client.get(reverse('home')).content.decode()
        self.assertIn(f'href="{reverse("dashboard")}" aria-label="Akun: ', html)


@FAST_HASH
class SeedUsersTests(TestCase):
    def test_membuat_satu_user_dan_satu_admin_dan_aman_diulang(self):
        for _ in range(2):
            call_command('seed_users', verbosity=0)
        user = User.objects.get(email='nadia@example.com')
        admin = User.objects.get(email='admin@example.com')
        self.assertEqual(user.profile.role, Profile.Role.USER)
        self.assertEqual(admin.profile.role, Profile.Role.ADMIN)
        self.assertEqual(User.objects.count(), 2)
        self.assertTrue(self.client.login(username='nadia@example.com', password='wuwashy-user-123'))


def buat_booking(status='menunggu', layanan='reguler', berat='4', nama='Rina Sari'):
    return Booking.objects.create(nama=nama, whatsapp='081234567890', layanan=layanan,
                                  berat=Decimal(berat), alamat='Jl. Contoh No. 1', status=status)


@FAST_HASH
class AdminLogoutTests(TestCase):
    def setUp(self):
        self.admin = buat_user('ayu@wuwashy.id', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')

    def test_dialog_keluar_sesuai_desain(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, 'Keluar dari WuWashy?')
        self.assertContains(r, 'Anda akan keluar dari akun Ayu Pratiwi.')
        self.assertContains(r, 'ayu@wuwashy.id &middot; Cabang Utama')
        self.assertContains(r, f'method="post" action="{reverse("logout")}"')
        self.assertContains(r, 'Ya, Keluar')

    def test_logout_harus_post(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_kembali_ke_landing_page_dan_menutup_akses(self):
        self.client.force_login(self.admin)
        self.assertRedirects(self.client.post(reverse('logout')), reverse('home'))
        self.assertNotIn('_auth_user_id', self.client.session)
        url = reverse('admin_dashboard')
        self.assertRedirects(self.client.get(url), f"{reverse('login')}?next={url}")

    def test_logout_tanpa_csrf_ditolak(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        self.assertEqual(c.post(reverse('logout')).status_code, 403)


class BookingModelTests(TestCase):
    def test_total_dihitung_dari_harga_layanan(self):
        self.assertEqual(buat_booking(layanan='express', berat='3.5').total, 42000)
        self.assertEqual(buat_booking(layanan='dry', berat='2').total, 50000)
        self.assertEqual(buat_booking(layanan='reguler', berat='0.5').total, 3500)

    def test_nama_layanan(self):
        self.assertEqual(buat_booking(layanan='setrika').nama_layanan, 'Setrika Saja')

    def test_langkah_pelacakan_dan_dibatalkan(self):
        langkah = buat_booking(status='siap').langkah
        self.assertEqual([x['now'] for x in langkah].index(True), 3)
        self.assertEqual(buat_booking(status='dibatalkan').langkah, [])


class PanelRingkasanTests(TestCase):
    def test_skala_sumbu(self):
        self.assertEqual(panel.skala_sumbu(160), [160, 120, 80, 40, 0])
        self.assertEqual(panel.skala_sumbu(0), [4, 3, 2, 1, 0])
        self.assertEqual(panel.skala_sumbu(7000), [8000, 6000, 4000, 2000, 0])

    def test_data_kosong_tidak_error(self):
        r = panel.ringkasan()
        self.assertEqual(r['stat']['total'], '0')
        self.assertEqual(r['stat']['tingkat'], '0,0')
        self.assertTrue(r['donut']['gradien'].startswith('conic-gradient(#e3e8f3'))
        self.assertEqual(r['terbaru'], [])

    def test_hitung_per_kelompok_status(self):
        for status, n in (('menunggu', 2), ('dijemput', 1), ('diproses', 1), ('siap', 1), ('diantar', 1),
                          ('selesai', 3), ('dibatalkan', 1)):
            for _ in range(n):
                buat_booking(status=status)
        r = panel.ringkasan()
        self.assertEqual(r['stat']['total'], '10')
        self.assertEqual(r['jml'], {'menunggu': '2', 'diproses': '2', 'siap': '2', 'selesai': '3', 'dibatalkan': '1'})
        self.assertEqual(r['stat']['aktif'], '6')          # menunggu + diproses + siap
        self.assertEqual(r['stat']['tingkat'], '30,0')     # 3 dari 10
        self.assertEqual(r['stat']['masuk_hari_ini'], '10')
        self.assertEqual(r['stat']['selesai_hari_ini'], '3')
        self.assertEqual(r['sidebar']['semua'], '10')

    def test_donut_satu_status_penuh(self):
        buat_booking(status='selesai')
        self.assertEqual(panel.ringkasan()['donut']['gradien'], 'conic-gradient(#ccff48 0.00% 100.00%)')

    def test_batang_harian_sampai_hari_ini(self):
        buat_booking()
        buat_booking()
        r = panel.ringkasan()
        hari_ini = timezone.localdate().day
        self.assertEqual(len(r['batang']), hari_ini)
        self.assertEqual(r['batang'][-1]['jumlah'], 2)
        self.assertEqual(r['batang'][-1]['persen'], 50)  # skala [4,3,2,1,0]: 2 dari 4

    def test_pesanan_terbaru_maksimal_lima_urut_terbaru(self):
        for i in range(7):
            buat_booking(nama=f'Pelanggan {i}')
        r = panel.ringkasan()
        self.assertEqual(len(r['terbaru']), 5)
        self.assertEqual(r['terbaru'][0]['nama'], 'Pelanggan 6')
        self.assertEqual(r['jumlah_semua'], '7')


@FAST_HASH
class PanelDashboardViewTests(TestCase):
    def setUp(self):
        self.admin = buat_user('ayu@wuwashy.id', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')

    def test_hanya_admin(self):
        url = reverse('admin_dashboard')
        self.assertEqual(self.client.get(url).status_code, 302)
        self.client.force_login(buat_user('nadia@example.com'))
        self.assertEqual(self.client.get(url).status_code, 403)

    def test_dasbor_menampilkan_data_nyata(self):
        buat_booking(status='diproses', layanan='express', berat='3.5', nama='Rina Sari')
        buat_booking(status='siap', nama='Budi Santoso')
        buat_booking(status='dibatalkan', nama='Nadia Putri')
        self.client.force_login(self.admin)
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, 'Selamat datang, Ayu. Berikut aktivitas Cabang Utama bulan ini.')
        self.assertContains(r, 'WuWashy Laundry')
        self.assertContains(r, 'Cabang Utama &middot; Samarinda')
        for teks in ('Rina Sari', 'Budi Santoso', 'Rp 42.000', 'Cuci Express', 'Jemput &amp; antar',
                     '1 pesanan Siap Diambil', 'Menampilkan 1&ndash;3 dari 3 pesanan'):
            self.assertContains(r, teks)
        self.assertEqual(r.context['stat']['total'], '3')

    def test_dasbor_kosong(self):
        self.client.force_login(self.admin)
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, 'Belum ada pesanan masuk.')
        self.assertNotContains(r, 'Siap Diambil. Hubungi')


class NormalisasiWaTests(TestCase):
    def test_berbagai_format_menjadi_62(self):
        for mentah in ('0812-3456-7890', '+62 812 3456 7890', '6281234567890', '81234567890'):
            self.assertEqual(normalisasi_wa(mentah), '6281234567890')

    def test_tidak_valid_menjadi_kosong(self):
        for mentah in ('', None, '123', 'abc', '0'):
            self.assertEqual(normalisasi_wa(mentah), '')


@FAST_HASH
class SignUpWhatsAppTests(TestCase):
    def _post(self, **extra):
        data = {'full_name': 'Nadia Aulia', 'email': 'nadia@example.com', 'whatsapp': '08123456789',
                'password1': 'Kain-Wangi-2026', 'password2': 'Kain-Wangi-2026'}
        data.update(extra)
        return self.client.post(reverse('signup'), data)

    def test_nomor_disimpan_ter_normalisasi_di_profil(self):
        self._post()
        self.assertEqual(User.objects.get(email='nadia@example.com').profile.whatsapp, '628123456789')

    def test_nomor_tidak_valid_ditolak(self):
        self.assertContains(self._post(whatsapp='abc'), 'nomor WhatsApp yang valid')
        self.assertFalse(User.objects.filter(email='nadia@example.com').exists())

    def test_nomor_sudah_dipakai_akun_lain_ditolak(self):
        self._post()
        self.client.logout()
        r = self._post(email='lain@example.com', whatsapp='+62 812-3456-789')
        self.assertContains(r, 'sudah dipakai akun lain')


BOOKING_DATA = {'nama': 'Nadia Aulia', 'whatsapp': '081234567890', 'layanan': 'express',
                'berat': '5', 'alamat': 'Jl. Pramuka No. 12, Samarinda', 'catatan': ''}


@FAST_HASH
class BookingTautanTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        Profile.objects.filter(user=self.user).update(whatsapp='6281234567890')

    def _booking(self, **extra):
        r = self.client.post(reverse('booking'), {**BOOKING_DATA, **extra})
        self.assertEqual(r.status_code, 302)
        return Booking.objects.latest('dibuat')

    def test_login_saat_memesan_tertaut_ke_akun(self):
        self.client.force_login(self.user)
        b = self._booking(whatsapp='089900001111')  # nomor boleh beda: akun yang login menang
        self.assertEqual((b.user, b.asal), (self.user, 'akun'))

    def test_tamu_dengan_nomor_cocok_tertaut_lewat_whatsapp(self):
        b = self._booking(whatsapp='+62 812-3456-7890')
        self.assertEqual((b.user, b.asal), (self.user, 'whatsapp'))

    def test_tamu_tanpa_akun_cocok_tetap_tersimpan_untuk_analitik(self):
        b = self._booking(whatsapp='085555555555')
        self.assertEqual((b.user, b.asal), (None, 'tamu'))
        self.assertEqual((b.nama, b.layanan, str(b.berat)), ('Nadia Aulia', 'express', '5.0'))

    def test_nomor_dipakai_dua_akun_tidak_ditebak(self):
        lain = buat_user('lain@example.com')
        Profile.objects.filter(user=lain).update(whatsapp='6281234567890')  # lewat update: lolos validasi form
        self.assertIsNone(cari_akun_dari_wa('081234567890'))
        self.assertEqual(self._booking().asal, 'tamu')

    def test_admin_tidak_dipakai_untuk_pencocokan(self):
        admin = buat_user('admin@example.com', role=Profile.Role.ADMIN)
        Profile.objects.filter(user=admin).update(whatsapp='6288800001111')
        self.assertIsNone(cari_akun_dari_wa('088800001111'))

    def test_form_booking_terisi_untuk_pelanggan_login(self):
        self.client.force_login(self.user)
        r = self.client.get(reverse('booking'))
        self.assertContains(r, 'value="Nadia Aulia"')
        self.assertContains(r, 'value="6281234567890"')


@FAST_HASH
class PoinTests(TestCase):
    def setUp(self):
        self.user = buat_user()

    def _pesanan(self, **kw):
        b = buat_booking(**kw)
        Booking.objects.filter(pk=b.pk).update(user=self.user, asal='akun')
        b = Booking.objects.get(pk=b.pk)
        b.save()  # akun dipasang setelah pesanan dibuat; simpan ulang agar signal poin ikut jalan seperti di aplikasi
        return b

    def test_poin_masuk_saat_selesai_rp1000_satu_poin(self):
        b = self._pesanan(layanan='express', berat='5')  # 60.000 -> 60 poin
        self.assertEqual(saldo_poin(self.user.pk), 0)
        b.status = 'selesai'
        b.save()
        log = PoinLog.objects.get()
        self.assertEqual((log.jumlah, log.saldo, log.booking), (60, 60, b))
        self.assertEqual(saldo_poin(self.user.pk), 60)

    def test_disimpan_berulang_tidak_menggandakan_poin(self):
        b = self._pesanan(layanan='express', berat='5', status='selesai')
        b.save()
        b.save()
        self.assertEqual(PoinLog.objects.count(), 1)

    def test_status_belum_selesai_atau_dibatalkan_tidak_memberi_poin(self):
        for status in ('menunggu', 'diproses', 'siap', 'diantar', 'dibatalkan'):
            b = self._pesanan(status=status)
            b.save()
        self.assertEqual(PoinLog.objects.count(), 0)

    def test_pesanan_tamu_tanpa_akun_tidak_memberi_poin(self):
        buat_booking(status='selesai')
        self.assertEqual(PoinLog.objects.count(), 0)

    def test_saldo_berjalan_akumulatif(self):
        self._pesanan(layanan='express', berat='5', status='selesai')       # +60
        self._pesanan(layanan='reguler', berat='4', status='selesai')       # 28.000 -> +28
        self.assertEqual([l.saldo for l in PoinLog.objects.order_by('id')], [60, 88])

    def test_pesanan_yang_baru_ditautkan_admin_memberi_poin_saat_disimpan(self):
        b = buat_booking(status='selesai', layanan='express', berat='5')
        b.user = self.user
        b.save()
        self.assertEqual(saldo_poin(self.user.pk), 60)

    def test_dashboard_menampilkan_poin_dan_pesanan_aktif_nyata(self):
        self._pesanan(layanan='express', berat='5', status='selesai')  # +60
        self._pesanan(status='diproses')
        self.client.force_login(self.user)
        r = self.client.get(reverse('dashboard'))
        self.assertEqual(r.context['poin'], 60)
        self.assertEqual(r.context['pesanan_aktif'], 1)


@FAST_HASH
class PesananSayaTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.lain = buat_user('lain@example.com', first_name='Lain', last_name='Orang')
        self.url = reverse('pesanan_saya')

    def _pesanan(self, pemilik=None, **kw):
        b = buat_booking(**kw)
        Booking.objects.filter(pk=b.pk).update(user=pemilik or self.user, asal='akun')
        return Booking.objects.get(pk=b.pk)

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        admin = buat_user('admin@example.com', role=Profile.Role.ADMIN)
        self.client.force_login(admin)
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_hanya_pesanan_aktif_milik_sendiri(self):
        milik = self._pesanan(status='diproses', nama='Pesanan Saya')
        self._pesanan(pemilik=self.lain, status='diproses')
        self._pesanan(status='selesai')
        self._pesanan(status='dibatalkan')
        buat_booking()  # tamu tanpa akun
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(list(r.context['pesanan']), [milik])
        self.assertEqual(r.context['jumlah_aktif'], 1)
        self.assertContains(r, f'#{milik.resi}')

    def test_tab_menunggu_penjemputan(self):
        menunggu = self._pesanan(status='menunggu')
        self._pesanan(status='diproses')
        self.client.force_login(self.user)
        r = self.client.get(self.url, {'tab': 'menunggu'})
        self.assertEqual(list(r.context['pesanan']), [menunggu])
        self.assertEqual((r.context['jumlah_aktif'], r.context['jumlah_menunggu']), (2, 1))
        self.assertEqual(self.client.get(self.url, {'tab': 'ngawur'}).context['tab'], 'aktif')

    def test_total_calon_poin_dan_estimasi(self):
        self._pesanan(layanan='express', berat='5', status='diproses')  # 60.000 -> +60 poin, estimasi 6 jam
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, 'Rp 60.000')
        self.assertContains(r, '+60 poin setelah selesai')
        self.assertEqual(r.context['total_aktif'], '60.000')
        b = r.context['utama']
        self.assertEqual(r.context['estimasi_terdekat'] - b.dibuat, timezone.timedelta(hours=6))

    def test_kosong_tidak_error(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Belum ada pesanan aktif')

    def test_lencana_sidebar_dan_menu_aktif(self):
        self._pesanan(status='menunggu')
        self._pesanan(status='siap')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, '<span class="badge">2</span>')
        self.assertContains(r, 'href="%s" aria-current="page"' % self.url)

    def test_pesanan_tamu_yang_cocok_whatsapp_muncul_di_halaman(self):
        Profile.objects.filter(user=self.user).update(whatsapp='6281234567890')
        self.client.post(reverse('booking'), {**BOOKING_DATA, 'whatsapp': '081234567890'})
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).context['jumlah_aktif'], 1)


@FAST_HASH
class PoinHadiahTests(TestCase):
    def setUp(self):
        self.user = buat_user()
        self.url = reverse('poin_hadiah')

    def _selesai(self, **kw):
        b = buat_booking(**kw)
        Booking.objects.filter(pk=b.pk).update(user=self.user, asal='akun')
        b = Booking.objects.get(pk=b.pk)
        b.status = 'selesai'
        b.save()
        return b

    def test_anonim_ke_login_dan_admin_ke_panel(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(buat_user('admin@example.com', role=Profile.Role.ADMIN))
        self.assertRedirects(self.client.get(self.url), reverse('admin_dashboard'))

    def test_saldo_nol_target_voucher_5000(self):
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual((r.context['saldo'], r.context['target']['key']), (0, 'voucher-5000'))
        self.assertEqual((r.context['target_persen'], r.context['jumlah_bisa']), (0, 0))
        self.assertContains(r, 'Belum ada riwayat poin')

    def test_750_poin_seperti_desain(self):
        for _ in range(3):
            self._selesai(layanan='express', berat='20.8')  # 249.600 -> 249 poin
        PoinLog.objects.filter(user=self.user).first().delete()  # 498 poin
        PoinLog.objects.create(user=self.user, jumlah=252, saldo=750, keterangan='Penyesuaian')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.context['saldo'], 750)
        self.assertEqual((r.context['target']['key'], r.context['target_persen']), ('voucher-10000', 75))
        self.assertEqual(r.context['jumlah_bisa'], 1)  # voucher 5.000 sudah bisa ditukar
        self.assertContains(r, 'Kurang 250 poin')
        self.assertContains(r, '250 poin lagi')

    def test_tab_bisa_ditukar_menyaring(self):
        PoinLog.objects.create(user=self.user, jumlah=600, saldo=600, keterangan='Penyesuaian')
        self.client.force_login(self.user)
        r = self.client.get(self.url, {'tab': 'bisa'})
        self.assertEqual([h['key'] for h in r.context['hadiah']], ['voucher-5000'])

    def test_semua_hadiah_bisa_saat_saldo_cukup(self):
        PoinLog.objects.create(user=self.user, jumlah=1200, saldo=1200, keterangan='Penyesuaian')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual((r.context['target']['key'], r.context['target_persen']), ('voucher-10000', 100))
        self.assertContains(r, 'sudah bisa ditukar')

    def test_riwayat_poin_menampilkan_resi_dan_saldo(self):
        b = self._selesai(layanan='express', berat='5')  # +60
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertContains(r, f'#{b.resi}')
        self.assertContains(r, '+60')

    def test_poin_menunggu_dari_pesanan_aktif(self):
        aktif = buat_booking(layanan='express', berat='5', status='diproses')
        Booking.objects.filter(pk=aktif.pk).update(user=self.user, asal='akun')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual(r.context['poin_menunggu'], 60)
        self.assertContains(r, '+60 poin menunggu')
        self.assertContains(r, f'#{aktif.resi}')

    def test_poin_pengguna_lain_tidak_bocor(self):
        lain = buat_user('lain@example.com')
        PoinLog.objects.create(user=lain, jumlah=900, saldo=900, keterangan='Penyesuaian')
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).context['saldo'], 0)

    def test_menu_sidebar_menuju_halaman_poin(self):
        self.client.force_login(self.user)
        self.assertContains(self.client.get(reverse('pesanan_saya')), f'href="{self.url}"')
        r = self.client.get(self.url)
        self.assertContains(r, f'href="{self.url}" aria-current="page"')


@FAST_HASH
class AdminPesananDetailTests(TestCase):
    def setUp(self):
        self.admin = buat_user('admin@example.com', role=Profile.Role.ADMIN, first_name='Admin', last_name='WuWashy')
        self.user = buat_user()
        self.b = buat_booking(layanan='express', berat='5', status='diproses')  # 60.000 -> 60 poin
        Booking.objects.filter(pk=self.b.pk).update(user=self.user, asal='akun')
        self.url = reverse('admin_pesanan_detail', args=[self.b.pk])

    def _ubah(self, status, **extra):
        return self.client.post(self.url, {'status': status}, **extra)

    def test_hanya_admin(self):
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self._ubah('selesai').status_code, 403)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'diproses')
        self.assertEqual(PoinLog.objects.count(), 0)

    def test_halaman_menampilkan_rincian(self):
        self.client.force_login(self.admin)
        r = self.client.get(self.url)
        self.assertContains(r, f'Pesanan {self.b.resi}')
        self.assertContains(r, 'Rp 60.000')
        self.assertContains(r, '5 pcs')
        self.assertContains(r, 'nadia@example.com')
        self.assertContains(r, 'Akan mendapat +60 poin saat pesanan selesai.')

    def test_pesanan_tidak_ada_404(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse('admin_pesanan_detail', args=[99999])).status_code, 404)

    def test_ubah_ke_selesai_menambah_poin_user(self):
        self.client.force_login(self.admin)
        r = self._ubah('selesai', follow=True)
        self.assertRedirects(r, self.url)
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'selesai')
        self.assertEqual(saldo_poin(self.user.pk), 60)
        self.assertContains(r, '+60 poin masuk ke nadia@example.com (saldo 60)')
        self.assertContains(r, 'Sudah diberikan: +60 poin')

    def test_poin_tampil_di_halaman_poin_hadiah_pelanggan(self):
        self.client.force_login(self.admin)
        self._ubah('selesai')
        self.client.force_login(self.user)
        r = self.client.get(reverse('poin_hadiah'))
        self.assertEqual(r.context['saldo'], 60)
        self.assertContains(r, f'#{self.b.resi}')
        self.assertEqual(self.client.get(reverse('pesanan_saya')).context['jumlah_aktif'], 0)

    def test_bolak_balik_status_tidak_menggandakan_poin(self):
        self.client.force_login(self.admin)
        self._ubah('selesai')
        self._ubah('diproses')
        r = self._ubah('selesai', follow=True)
        self.assertEqual(saldo_poin(self.user.pk), 60)
        self.assertEqual(PoinLog.objects.count(), 1)
        self.assertContains(r, 'sudah pernah diberikan')

    def test_status_selain_selesai_tidak_memberi_poin(self):
        self.client.force_login(self.admin)
        for status in ('menunggu', 'dijemput', 'siap', 'diantar', 'dibatalkan'):
            self._ubah(status)
        self.assertEqual(PoinLog.objects.count(), 0)

    def test_pesanan_tamu_selesai_tanpa_poin(self):
        tamu = buat_booking(status='diproses')
        self.client.force_login(self.admin)
        r = self.client.post(reverse('admin_pesanan_detail', args=[tamu.pk]), {'status': 'selesai'}, follow=True)
        self.assertContains(r, 'Pesanan tamu tanpa akun')
        self.assertEqual(PoinLog.objects.count(), 0)

    def test_status_tidak_dikenal_ditolak(self):
        self.client.force_login(self.admin)
        r = self._ubah('ngawur', follow=True)
        self.assertContains(r, 'Status tidak dikenal')
        self.b.refresh_from_db()
        self.assertEqual(self.b.status, 'diproses')

    def test_tanpa_csrf_ditolak(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        self.assertEqual(c.post(self.url, {'status': 'selesai'}).status_code, 403)

    def test_dasbor_menautkan_resi_ke_detail(self):
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin_dashboard')), f'href="{self.url}"')
