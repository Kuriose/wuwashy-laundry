from datetime import date, timedelta
from decimal import Decimal
from io import StringIO

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from . import panel
from .models import AnggotaTim, Booking, PoinLog, Profile
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
        self.assertContains(r, 'Masukkan alamat emailmu')

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
        self.assertContains(self._post(username='bukan-email'), 'alamat email yang valid')

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
        self.assertContains(r, 'Konfirmasi kata sandi')

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
        self.assertContains(r, "Kedua kata sandi tidak sama")
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
        self.assertContains(r, 'Masukkan nama lengkapmu.')
        self.assertContains(r, 'Masukkan alamat emailmu.')
        self.assertContains(r, 'Buat kata sandimu.')
        self.assertContains(r, 'Masukkan nomor WhatsAppmu.')
        self.assertContains(self._post(email='bukan-email'), 'alamat email yang valid')

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


class PanelNavTests(TestCase):
    """Overview dan Semua Pesanan di sidebar; Menunggu / Diproses / Selesai / Dibatalkan."""

    def setUp(self):
        self.admin = buat_user('ayu@wuwashy.id', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')
        self.client.force_login(self.admin)

    # ── Overview ───────────────────────────────────────────────────────────────
    def test_overview_aktif_di_dasbor(self):
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, 'is-active" href="/panel/"')
        self.assertContains(r, '<strong aria-current="page">Overview</strong>')

    def test_overview_tidak_aktif_di_halaman_lain(self):
        for url in ['admin_pesanan','admin_menunggu','admin_diproses','admin_selesai','admin_dibatalkan']:
            r = self.client.get(reverse(url))
            self.assertNotContains(r, 'is-active" href="/panel/"', msg_prefix=url)

    # ── Semua Pesanan ──────────────────────────────────────────────────────────
    def test_semua_pesanan_hanya_admin(self):
        self.client.logout()
        self.assertRedirects(self.client.get(reverse('admin_pesanan')),
                             f"{reverse('login')}?next={reverse('admin_pesanan')}")

    def test_semua_pesanan_aktif_di_sidebar(self):
        r = self.client.get(reverse('admin_pesanan'))
        self.assertContains(r, 'is-active" href="/panel/pesanan/"')
        self.assertContains(r, '<strong aria-current="page">Semua Pesanan</strong>')

    def test_semua_pesanan_semua_status_tampil(self):
        for st in ('menunggu','diproses','selesai','dibatalkan'):
            buat_booking(status=st)
        r = self.client.get(reverse('admin_pesanan'), {'periode': 'semua'})
        self.assertEqual(len(r.context['baris']), 4)

    # ── Menunggu ───────────────────────────────────────────────────────────────
    def test_menunggu_hanya_status_menunggu(self):
        buat_booking(status='menunggu')
        buat_booking(status='diproses')
        buat_booking(status='selesai')
        r = self.client.get(reverse('admin_menunggu'), {'periode': 'semua'})
        self.assertEqual(len(r.context['baris']), 1)
        self.assertEqual(r.context['baris'][0]['status_key'], 'menunggu')

    def test_menunggu_aktif_di_sidebar(self):
        r = self.client.get(reverse('admin_menunggu'))
        self.assertContains(r, 'is-active" href="/panel/pesanan/menunggu/"')
        self.assertContains(r, '<strong aria-current="page">Menunggu</strong>')

    # ── Diproses ───────────────────────────────────────────────────────────────
    def test_diproses_mencakup_dijemput_dan_diproses(self):
        buat_booking(status='dijemput')
        buat_booking(status='diproses')
        buat_booking(status='menunggu')
        r = self.client.get(reverse('admin_diproses'), {'periode': 'semua'})
        self.assertEqual(len(r.context['baris']), 2)

    # ── Selesai ────────────────────────────────────────────────────────────────
    def test_selesai_hanya_status_selesai(self):
        buat_booking(status='selesai')
        buat_booking(status='dibatalkan')
        r = self.client.get(reverse('admin_selesai'), {'periode': 'semua'})
        self.assertEqual(len(r.context['baris']), 1)
        self.assertEqual(r.context['baris'][0]['status_key'], 'selesai')

    # ── Dibatalkan ─────────────────────────────────────────────────────────────
    def test_dibatalkan_hanya_status_dibatalkan(self):
        buat_booking(status='dibatalkan')
        buat_booking(status='selesai')
        r = self.client.get(reverse('admin_dibatalkan'), {'periode': 'semua'})
        self.assertEqual(len(r.context['baris']), 1)
        self.assertEqual(r.context['baris'][0]['status_key'], 'dibatalkan')

    # ── Pencarian & pager ──────────────────────────────────────────────────────
    def test_pencarian_nama_dan_telepon(self):
        buat_booking(nama='Rina Sari')   # whatsapp=081234567890
        buat_booking(nama='Budi Santoso')   # <<< fix: buat_booking selalu 081234567890, ganti pakai whatsapp lain
        from laundry.models import Booking; Booking.objects.filter(nama='Budi Santoso').update(whatsapp='085599887766')
        r = self.client.get(reverse('admin_pesanan'), {'q':'rina','periode':'semua'})
        self.assertEqual(len(r.context['baris']), 1)
        self.assertEqual(r.context['baris'][0]['nama'], 'Rina Sari')
        r2 = self.client.get(reverse('admin_pesanan'), {'q':'0812-3456-7890','periode':'semua'})
        self.assertEqual(len(r2.context['baris']), 1)

    def test_paginasi_8_per_halaman(self):
        for i in range(9): buat_booking(nama=f'P{i}')
        r = self.client.get(reverse('admin_pesanan'))
        self.assertEqual(len(r.context['baris']), 8)
        r2 = self.client.get(reverse('admin_pesanan'), {'hal': 2})
        self.assertEqual(len(r2.context['baris']), 1)

    def test_hint_menunggu_tampil(self):
        buat_booking(status='menunggu')
        r = self.client.get(reverse('admin_menunggu'))
        self.assertContains(r, 'Penyerahan dicatat saat laundry diterima pelanggan.')

    def test_overview_link_ke_semua_pesanan(self):
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, f'href="{reverse('admin_pesanan')}"')


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
        return Booking.objects.get(pk=b.pk)

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
        PoinLog.objects.create(user=self.user, jumlah=1500, saldo=1500, keterangan='Penyesuaian')
        self.client.force_login(self.user)
        r = self.client.get(self.url)
        self.assertEqual((r.context['target']['key'], r.context['target_persen']), ('gratis-cuci', 100))
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


@FAST_HASH
class DashboardLanjutanTests(TestCase):
    DATA = {'nama': 'Nadia Aulia', 'whatsapp': '081234567890', 'layanan': 'reguler', 'berat': '5',
            'alamat': 'Jl. Pramuka No. 12, Samarinda', 'catatan': ''}

    def setUp(self):
        self.user = buat_user()
        self.client.force_login(self.user)

    def test_halaman_baru_bisa_dibuka(self):
        for name in ('pesan_laundry', 'notifikasi', 'pengaturan'):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200, name)

    def test_pesan_dari_dashboard_tertaut_ke_akun_dan_buka_whatsapp(self):
        r = self.client.post(reverse('pesan_laundry'), self.DATA)
        self.assertEqual(r.status_code, 302)
        self.assertIn('wa.me', r['Location'])
        b = Booking.objects.get()
        self.assertEqual((b.user, b.asal), (self.user, 'akun'))

    def test_jumlah_pakaian_harus_bilangan_bulat(self):
        r = self.client.post(reverse('pesan_laundry'), {**self.DATA, 'berat': '2.5'})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'bilangan bulat')
        self.assertFalse(Booking.objects.exists())

    def test_tukar_hadiah_mengurangi_saldo(self):
        PoinLog.objects.create(user=self.user, jumlah=1000, saldo=1000, keterangan='Penyesuaian')
        r = self.client.post(reverse('tukar_hadiah', args=['voucher-5000']))
        self.assertRedirects(r, reverse('poin_hadiah'))
        self.assertEqual(saldo_poin(self.user.pk), 500)

    def test_tukar_hadiah_saldo_kurang_ditolak(self):
        PoinLog.objects.create(user=self.user, jumlah=100, saldo=100, keterangan='Penyesuaian')
        self.client.post(reverse('tukar_hadiah', args=['voucher-5000']))
        self.assertEqual(saldo_poin(self.user.pk), 100)
        self.assertEqual(PoinLog.objects.count(), 1)

    def test_tukar_hadiah_tidak_dikenal_dan_hanya_post(self):
        PoinLog.objects.create(user=self.user, jumlah=1000, saldo=1000, keterangan='Penyesuaian')
        self.client.post(reverse('tukar_hadiah', args=['tidak-ada']))
        self.assertEqual(saldo_poin(self.user.pk), 1000)
        self.assertEqual(self.client.get(reverse('tukar_hadiah', args=['voucher-5000'])).status_code, 405)


def buat_anggota(nama='Dimas Setiawan', email='dimas@wuwashy.id', telepon='0812-1100-2004', peran='kurir', aktif=True):
    return AnggotaTim.objects.create(nama=nama, email=email, telepon=telepon, peran=peran, aktif=aktif)


class AnggotaTimModelTests(TestCase):
    def test_telepon_dinormalisasi_dan_ditampilkan_berformat(self):
        a = buat_anggota('Ayu Pratiwi', telepon='0812-1100-1001')
        self.assertEqual(a.telepon, '6281211001001')
        self.assertEqual(a.telepon_fmt, '0812-1100-1001')

    def test_inisial(self):
        self.assertEqual(buat_anggota('Ayu Pratiwi').inisial, 'AP')
        self.assertEqual(buat_anggota('Budi', email='b@wuwashy.id', telepon='081211009999').inisial, 'B')

    def test_email_disimpan_huruf_kecil(self):
        a = buat_anggota(email='  Dimas@WuWashy.ID ')
        a.refresh_from_db()
        self.assertEqual(a.email, 'dimas@wuwashy.id')

    def test_urutan_kasir_dulu_lalu_kurir(self):
        buat_anggota('Kurir Satu', 'k1@wuwashy.id', '081211000001', 'kurir')
        buat_anggota('Kasir Satu', 's1@wuwashy.id', '081211000002', 'kasir')
        buat_anggota('Kurir Dua', 'k2@wuwashy.id', '081211000003', 'kurir')
        self.assertEqual([a.nama for a in AnggotaTim.objects.all()], ['Kasir Satu', 'Kurir Satu', 'Kurir Dua'])


@FAST_HASH
class AnggotaTimViewTests(TestCase):
    DATA = {'nama': 'Dimas Setiawan', 'email': 'dimas@wuwashy.id', 'telepon': '0812-1100-2004', 'peran': 'kurir'}

    def setUp(self):
        self.url = reverse('admin_anggota')
        self.admin = buat_user('ayu@wuwashy.id', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')
        self.client.force_login(self.admin)

    # ── akses ──────────────────────────────────────────────────────────────────
    def test_anonim_diarahkan_ke_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_user_biasa_ditolak_baik_lihat_maupun_tambah(self):
        self.client.force_login(buat_user('nadia@example.com'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.DATA).status_code, 403)
        self.assertEqual(AnggotaTim.objects.count(), 0)

    # ── tampilan ───────────────────────────────────────────────────────────────
    def test_daftar_dan_ringkasan_sesuai_desain(self):
        call_command('seed_tim', stdout=StringIO())
        r = self.client.get(self.url)
        self.assertContains(r, '<h1>Anggota tim</h1>')
        self.assertContains(r, '6 anggota aktif &middot; 3 kasir dan 3 kurir di Cabang Utama.')
        self.assertContains(r, 'Menampilkan seluruh 6 anggota.')
        self.assertContains(r, 'Akses sesuai peran masing-masing anggota.')
        for teks in ('Ayu Pratiwi', 'ayu@wuwashy.id', '0812-1100-1001', 'Fajar Hidayat', 'Andi Saputra'):
            self.assertContains(r, teks)
        html = r.content.decode()
        self.assertLess(html.index('Budi Santoso'), html.index('Fajar Hidayat'))  # kasir sebelum kurir

    def test_anggota_nonaktif_tampil_tapi_tidak_dihitung(self):
        buat_anggota('Aktif Kasir', 'a@wuwashy.id', '081211000001', 'kasir')
        buat_anggota('Libur Kurir', 'l@wuwashy.id', '081211000002', 'kurir', aktif=False)
        r = self.client.get(self.url)
        self.assertContains(r, '1 anggota aktif &middot; 1 kasir dan 0 kurir di Cabang Utama.')
        self.assertContains(r, 'Nonaktif')
        self.assertContains(r, 'Menampilkan seluruh 2 anggota.')

    def test_daftar_kosong(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'Belum ada anggota aktif di Cabang Utama.')
        self.assertContains(r, 'Belum ada anggota tim.')

    def test_sidebar_dan_breadcrumb(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'is-active" href="/panel/anggota/"')
        self.assertContains(r, '<strong aria-current="page">Anggota Tim</strong>')
        self.assertNotContains(self.client.get(reverse('admin_pesanan')), 'is-active" href="/panel/anggota/"')

    def test_form_tertutup_bawaan_dan_terbuka_lewat_parameter(self):
        self.assertContains(self.client.get(self.url), 'id="form-anggota" hidden')
        r = self.client.get(self.url + '?tambah=1')
        self.assertNotContains(r, 'id="form-anggota" hidden')
        self.assertContains(r, 'Tambah anggota')
        self.assertContains(r, 'Kasir mencatat pesanan dan pembayaran. Kurir menangani penjemputan dan pengantaran.')

    # ── tambah anggota ─────────────────────────────────────────────────────────
    def test_tambah_anggota_berhasil(self):
        r = self.client.post(self.url, {**self.DATA, 'email': 'Dimas@WuWashy.id'}, follow=True)
        self.assertRedirects(r, self.url)
        a = AnggotaTim.objects.get()
        self.assertEqual((a.nama, a.email, a.telepon, a.peran, a.aktif),
                         ('Dimas Setiawan', 'dimas@wuwashy.id', '6281211002004', 'kurir', True))
        self.assertContains(r, 'Dimas Setiawan berhasil ditambahkan sebagai Kurir.')
        self.assertContains(r, 'id="form-anggota" hidden')  # form menutup lagi setelah tersimpan

    def test_peran_bawaan_kasir(self):
        html = self.client.get(self.url + '?tambah=1').content.decode()
        self.assertRegex(html, r'<input[^>]*value="kasir"[^>]*checked')
        self.assertNotRegex(html, r'<input[^>]*value="kurir"[^>]*checked')

    def test_semua_kolom_wajib(self):
        r = self.client.post(self.url, {})
        self.assertEqual(r.status_code, 200)
        for pesan in ('Masukkan nama lengkap anggota.', 'Masukkan alamat email anggota.',
                      'Masukkan nomor telepon anggota.', 'Pilih peran anggota.'):
            self.assertContains(r, pesan)
        self.assertNotContains(r, 'id="form-anggota" hidden')  # form tetap terbuka agar galat terlihat
        self.assertContains(r, 'aria-invalid="true"')
        self.assertEqual(AnggotaTim.objects.count(), 0)

    def test_email_tidak_valid(self):
        self.assertContains(self.client.post(self.url, {**self.DATA, 'email': 'bukan-email'}),
                            'Masukkan alamat email yang valid.')

    def test_email_ganda_tidak_peka_huruf(self):
        buat_anggota()
        r = self.client.post(self.url, {**self.DATA, 'email': 'DIMAS@wuwashy.id', 'telepon': '081299990000'})
        self.assertContains(r, 'Email ini sudah terdaftar sebagai anggota tim.')
        self.assertEqual(AnggotaTim.objects.count(), 1)

    def test_telepon_ganda_walau_beda_format(self):
        buat_anggota()
        r = self.client.post(self.url, {**self.DATA, 'email': 'lain@wuwashy.id', 'telepon': '+62 812-1100-2004'})
        self.assertContains(r, 'Nomor telepon ini sudah dipakai anggota lain.')
        self.assertEqual(AnggotaTim.objects.count(), 1)

    def test_telepon_tidak_valid(self):
        r = self.client.post(self.url, {**self.DATA, 'telepon': '123'})
        self.assertContains(r, 'Masukkan nomor telepon yang valid')

    def test_peran_tidak_dikenal_ditolak(self):
        r = self.client.post(self.url, {**self.DATA, 'peran': 'admin'})
        self.assertContains(r, 'Pilih salah satu: Kasir atau Kurir.')
        self.assertEqual(AnggotaTim.objects.count(), 0)

    def test_nama_terlalu_panjang(self):
        r = self.client.post(self.url, {**self.DATA, 'nama': 'A' * 101})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AnggotaTim.objects.count(), 0)

    def test_nama_dirapikan_dan_di_escape_saat_tampil(self):
        self.client.post(self.url, {**self.DATA, 'nama': '  <b>Dimas</b>   Setiawan '})
        self.assertEqual(AnggotaTim.objects.get().nama, '<b>Dimas</b> Setiawan')
        r = self.client.get(self.url)
        self.assertContains(r, '&lt;b&gt;Dimas&lt;/b&gt; Setiawan')
        self.assertNotContains(r, '<b>Dimas</b>')

    def test_tambah_tanpa_csrf_ditolak(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        self.assertEqual(c.post(self.url, self.DATA).status_code, 403)
        self.assertEqual(AnggotaTim.objects.count(), 0)


class SeedTimTests(TestCase):
    def test_aman_dijalankan_berulang(self):
        out = StringIO()
        call_command('seed_tim', stdout=out)
        self.assertIn('6 anggota baru dibuat', out.getvalue())
        out = StringIO()
        call_command('seed_tim', stdout=out)
        self.assertIn('0 anggota baru dibuat, 6 sudah ada', out.getvalue())
        self.assertEqual(AnggotaTim.objects.count(), 6)
        self.assertEqual(AnggotaTim.objects.filter(peran='kasir').count(), 3)


@FAST_HASH
class AnggotaTimEditTests(TestCase):
    """Edit data anggota: form yang sama dengan tambah anggota (nama, email, telepon, peran)."""

    def setUp(self):
        self.admin = buat_user('ayu@wuwashy.id', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')
        self.client.force_login(self.admin)
        self.a = buat_anggota()  # Dimas Setiawan, kurir, 0812-1100-2004
        self.url = reverse('admin_anggota_edit', args=[self.a.pk])
        self.daftar = reverse('admin_anggota')
        self.DATA = {'nama': 'Dimas S. Setiawan', 'email': 'dimas.s@wuwashy.id',
                     'telepon': '0812-1100-9999', 'peran': 'kasir'}

    def _tetap_utuh(self):
        self.a.refresh_from_db()
        self.assertEqual((self.a.nama, self.a.email, self.a.telepon, self.a.peran, self.a.aktif),
                         ('Dimas Setiawan', 'dimas@wuwashy.id', '6281211002004', 'kurir', True))

    # ── akses ──────────────────────────────────────────────────────────────────
    def test_url(self):
        self.assertEqual(self.url, f'/panel/anggota/{self.a.pk}/edit/')

    def test_anonim_diarahkan_ke_login(self):
        self.client.logout()
        self.assertRedirects(self.client.get(self.url), f"{reverse('login')}?next={self.url}")

    def test_user_biasa_ditolak_dan_data_tidak_berubah(self):
        self.client.force_login(buat_user('nadia@example.com'))
        self.assertEqual(self.client.get(self.url).status_code, 403)
        self.assertEqual(self.client.post(self.url, self.DATA).status_code, 403)
        self._tetap_utuh()

    def test_anggota_tidak_ada_404(self):
        self.assertEqual(self.client.get(reverse('admin_anggota_edit', args=[9999])).status_code, 404)
        self.assertEqual(self.client.post(reverse('admin_anggota_edit', args=[9999]), self.DATA).status_code, 404)

    def test_tanpa_csrf_ditolak(self):
        from django.test import Client
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.admin)
        self.assertEqual(c.post(self.url, self.DATA).status_code, 403)
        self._tetap_utuh()

    # ── tampilan ───────────────────────────────────────────────────────────────
    def test_setiap_baris_punya_tombol_edit(self):
        b = buat_anggota('Budi Santoso', 'budi@wuwashy.id', '081211001003', 'kasir')
        r = self.client.get(self.daftar)
        for anggota in (self.a, b):
            self.assertContains(r, f'href="/panel/anggota/{anggota.pk}/edit/"')
            self.assertContains(r, f'aria-label="Edit data {anggota.nama}"')

    def test_form_terisi_data_anggota(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'Edit anggota')
        self.assertContains(r, 'Ubah data Dimas Setiawan.')
        self.assertContains(r, 'value="Dimas Setiawan"')
        self.assertContains(r, 'value="dimas@wuwashy.id"')
        self.assertContains(r, 'value="0812-1100-2004"')  # berformat, bukan 62812...
        html = r.content.decode()
        self.assertRegex(html, r'<input[^>]*value="kurir"[^>]*checked')
        self.assertNotRegex(html, r'<input[^>]*value="kasir"[^>]*checked')

    def test_form_terbuka_dan_mengarah_ke_url_edit(self):
        r = self.client.get(self.url)
        self.assertNotContains(r, 'id="form-anggota" hidden')
        self.assertContains(r, f'action="{self.url}"')
        self.assertContains(r, 'data-mode="edit"')
        self.assertContains(r, 'Simpan Perubahan')
        self.assertNotContains(r, 'Simpan Anggota')
        self.assertContains(r, 'is-editing')

    def test_tombol_tambah_di_halaman_edit_menuju_mode_tambah(self):
        self.assertContains(self.client.get(self.url), 'href="/panel/anggota/?tambah=1#form-anggota"')

    def test_mode_tambah_tetap_seperti_semula(self):
        r = self.client.get(self.daftar + '?tambah=1')
        self.assertContains(r, 'Simpan Anggota')
        self.assertContains(r, 'data-mode="tambah"')
        self.assertNotContains(r, 'is-editing')

    def test_sidebar_dan_breadcrumb_tetap_anggota_tim(self):
        r = self.client.get(self.url)
        self.assertContains(r, 'is-active" href="/panel/anggota/"')
        self.assertContains(r, '<strong aria-current="page">Anggota Tim</strong>')

    # ── simpan perubahan ───────────────────────────────────────────────────────
    def test_edit_semua_kolom_berhasil(self):
        r = self.client.post(self.url, self.DATA, follow=True)
        self.assertRedirects(r, self.daftar)
        self.a.refresh_from_db()
        self.assertEqual((self.a.nama, self.a.email, self.a.telepon, self.a.peran),
                         ('Dimas S. Setiawan', 'dimas.s@wuwashy.id', '6281211009999', 'kasir'))
        self.assertEqual(AnggotaTim.objects.count(), 1)  # mengubah, bukan menambah
        self.assertContains(r, 'Data Dimas S. Setiawan berhasil diperbarui.')
        self.assertContains(r, 'id="form-anggota" hidden')

    def test_edit_satu_kolom_saja(self):
        self.client.post(self.url, {'nama': 'Dimas Setiawan', 'email': 'dimas@wuwashy.id',
                                    'telepon': '0812-1100-2004', 'peran': 'kasir'})
        self.a.refresh_from_db()
        self.assertEqual((self.a.peran, self.a.email, self.a.nama), ('kasir', 'dimas@wuwashy.id', 'Dimas Setiawan'))

    def test_edit_peran_memperbarui_ringkasan(self):
        r = self.client.get(self.daftar)
        self.assertContains(r, '1 anggota aktif &middot; 0 kasir dan 1 kurir di Cabang Utama.')
        self.client.post(self.url, {**self.DATA, 'email': 'dimas@wuwashy.id', 'telepon': '0812-1100-2004'})
        self.assertContains(self.client.get(self.daftar), '1 anggota aktif &middot; 1 kasir dan 0 kurir di Cabang Utama.')

    def test_email_dan_telepon_dirapikan_seperti_saat_tambah(self):
        self.client.post(self.url, {**self.DATA, 'email': ' Dimas.S@WuWashy.ID ', 'telepon': '+62 812-1100-9999'})
        self.a.refresh_from_db()
        self.assertEqual((self.a.email, self.a.telepon), ('dimas.s@wuwashy.id', '6281211009999'))

    def test_tanpa_perubahan_diberi_tahu_dan_tidak_disimpan(self):
        r = self.client.post(self.url, {'nama': 'Dimas Setiawan', 'email': 'DIMAS@wuwashy.id',
                                        'telepon': '+62 812-1100-2004', 'peran': 'kurir'}, follow=True)
        self.assertRedirects(r, self.daftar)
        self.assertContains(r, 'Tidak ada perubahan pada data Dimas Setiawan.')
        self.assertNotContains(r, 'berhasil diperbarui')

    def test_boleh_menyimpan_email_dan_telepon_milik_sendiri(self):
        self.client.post(self.url, {**self.DATA, 'email': 'dimas@wuwashy.id', 'telepon': '0812-1100-2004'})
        self.a.refresh_from_db()
        self.assertEqual((self.a.email, self.a.telepon, self.a.peran), ('dimas@wuwashy.id', '6281211002004', 'kasir'))

    def test_status_aktif_tidak_ikut_berubah(self):
        libur = buat_anggota('Libur Kasir', 'libur@wuwashy.id', '081211000009', 'kasir', aktif=False)
        url = reverse('admin_anggota_edit', args=[libur.pk])
        self.client.post(url, {'nama': 'Libur Kasir Baru', 'email': 'libur@wuwashy.id',
                               'telepon': '081211000009', 'peran': 'kasir', 'aktif': 'on'})
        libur.refresh_from_db()
        self.assertEqual((libur.nama, libur.aktif), ('Libur Kasir Baru', False))

    # ── validasi ───────────────────────────────────────────────────────────────
    def test_kolom_wajib_diisi(self):
        r = self.client.post(self.url, {})
        self.assertEqual(r.status_code, 200)
        for pesan in ('Masukkan nama lengkap anggota.', 'Masukkan alamat email anggota.',
                      'Masukkan nomor telepon anggota.', 'Pilih peran anggota.'):
            self.assertContains(r, pesan)
        self.assertNotContains(r, 'id="form-anggota" hidden')
        self._tetap_utuh()

    def test_email_milik_anggota_lain_ditolak(self):
        buat_anggota('Budi Santoso', 'budi@wuwashy.id', '081211001003', 'kasir')
        r = self.client.post(self.url, {**self.DATA, 'email': 'BUDI@wuwashy.id'})
        self.assertContains(r, 'Email ini sudah terdaftar sebagai anggota tim.')
        self._tetap_utuh()

    def test_telepon_milik_anggota_lain_ditolak_walau_beda_format(self):
        buat_anggota('Budi Santoso', 'budi@wuwashy.id', '081211001003', 'kasir')
        r = self.client.post(self.url, {**self.DATA, 'telepon': '+62 812-1100-1003'})
        self.assertContains(r, 'Nomor telepon ini sudah dipakai anggota lain.')
        self._tetap_utuh()

    def test_telepon_tidak_valid_dan_peran_tidak_dikenal(self):
        self.assertContains(self.client.post(self.url, {**self.DATA, 'telepon': '123'}),
                            'Masukkan nomor telepon yang valid')
        self.assertContains(self.client.post(self.url, {**self.DATA, 'peran': 'admin'}),
                            'Pilih salah satu: Kasir atau Kurir.')
        self._tetap_utuh()

    def test_galat_tetap_di_mode_edit_dengan_isian_pengguna_dan_nama_asli(self):
        r = self.client.post(self.url, {**self.DATA, 'email': 'bukan-email'})
        self.assertContains(r, 'Masukkan alamat email yang valid.')
        self.assertContains(r, 'Ubah data Dimas Setiawan.')       # judul memakai nama asli, bukan yang diketik
        self.assertContains(r, 'value="Dimas S. Setiawan"')        # isian pengguna dipertahankan
        self.assertContains(r, 'Simpan Perubahan')
        self.assertContains(r, 'data-mode="edit"')
        # daftar di sebelah kiri tetap menampilkan data tersimpan, bukan isian yang gagal
        self.assertContains(r, '<strong>Dimas Setiawan</strong>')
        self._tetap_utuh()

    def test_nama_di_escape(self):
        self.client.post(self.url, {**self.DATA, 'nama': '<b>Dimas</b>'})
        r = self.client.get(self.daftar)
        self.assertContains(r, '&lt;b&gt;Dimas&lt;/b&gt;')
        self.assertNotContains(r, '<b>Dimas</b>')


@FAST_HASH
class GabunganLaporanAnggotaTests(TestCase):
    """Memastikan fitur Laporan Tersimpan dan Anggota Tim berjalan berdampingan di panel yang sama."""

    def setUp(self):
        self.admin = buat_user('admin@example.com', role=Profile.Role.ADMIN, first_name='Ayu', last_name='Pratiwi')
        self.client.force_login(self.admin)

    def test_sidebar_memuat_kedua_menu_sebagai_tautan(self):
        r = self.client.get(reverse('admin_dashboard'))
        self.assertContains(r, f'href="{reverse("admin_laporan")}"')
        self.assertContains(r, f'href="{reverse("admin_anggota")}"')

    def test_menu_aktif_hanya_pada_halaman_yang_dibuka(self):
        laporan = self.client.get(reverse('admin_laporan'))
        self.assertContains(laporan, f'href="{reverse("admin_laporan")}" aria-current="page"')
        self.assertNotContains(laporan, f'href="{reverse("admin_anggota")}" aria-current="page"')
        anggota = self.client.get(reverse('admin_anggota'))
        self.assertContains(anggota, f'href="{reverse("admin_anggota")}" aria-current="page"')
        self.assertNotContains(anggota, f'href="{reverse("admin_laporan")}" aria-current="page"')

    def test_menu_anggota_tetap_aktif_saat_edit(self):
        a = buat_anggota()
        r = self.client.get(reverse('admin_anggota_edit', args=[a.pk]))
        self.assertContains(r, f'href="{reverse("admin_anggota")}" aria-current="page"')

    def test_halaman_laporan_menampilkan_laporan_dari_pesanan(self):
        buat_booking()
        r = self.client.get(reverse('admin_laporan'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Ringkasan operasional')
        self.assertGreaterEqual(r.context['stat']['jumlah_laporan'], 1)

    def test_halaman_laporan_kosong_tidak_error(self):
        r = self.client.get(reverse('admin_laporan'))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Belum ada laporan tersimpan')

    def test_hanya_admin_boleh_membuka_laporan_dan_anggota(self):
        self.client.logout()
        for nama in ('admin_laporan', 'admin_anggota'):
            self.assertRedirects(self.client.get(reverse(nama)), f"{reverse('login')}?next={reverse(nama)}")
        self.client.force_login(buat_user('pelanggan@example.com'))
        for nama in ('admin_laporan', 'admin_anggota'):
            self.assertEqual(self.client.get(reverse(nama)).status_code, 403)

    def test_tambah_anggota_tidak_mengubah_laporan(self):
        buat_booking()
        sebelum = self.client.get(reverse('admin_laporan')).context['stat']['jumlah_laporan']
        self.client.post(reverse('admin_anggota'), {
            'nama': 'Dimas Setiawan', 'email': 'dimas@wuwashy.id', 'telepon': '0812-1100-2004', 'peran': 'kurir'})
        self.assertEqual(AnggotaTim.objects.count(), 1)
        self.assertEqual(self.client.get(reverse('admin_laporan')).context['stat']['jumlah_laporan'], sebelum)
