import io
import zipfile
from datetime import date

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from .models import Booking, Profile
from .tests import FAST_HASH, buat_user


@FAST_HASH
class UnduhLaporanTests(TestCase):
    def setUp(self):
        self.admin = buat_user('admin@example.com', role=Profile.Role.ADMIN)
        call_command('seed_laporan', verbosity=0)

    def _url(self, **q):
        q = {'jenis': 'rekap', 'dari': '2000-01-01', 'sampai': '2100-01-01', **q}
        return reverse('admin_laporan_unduh') + '?' + '&'.join(f'{k}={v}' for k, v in q.items())

    def test_seed_membuat_data_dan_bisa_dihapus(self):
        self.assertTrue(Booking.objects.filter(catatan='[data-uji-laporan]').exists())
        call_command('seed_laporan', '--hapus', verbosity=0)
        self.assertFalse(Booking.objects.exists())

    def test_hanya_admin(self):
        self.assertEqual(self.client.get(self._url()).status_code, 302)
        buat_user('u@example.com')
        self.client.login(username='u@example.com', password='rahasia-123')
        self.assertNotEqual(self.client.get(self._url()).status_code, 200)

    def test_semua_jenis_menghasilkan_xlsx_valid(self):
        self.client.login(username='admin@example.com', password='rahasia-123')
        for jenis in ('ringkasan', 'pendapatan', 'rekap', 'mingguan'):
            r = self.client.get(self._url(jenis=jenis))
            self.assertEqual(r.status_code, 200)
            self.assertIn('spreadsheetml.sheet', r['Content-Type'])
            self.assertIn('.xlsx', r['Content-Disposition'])
            self.assertIn('xl/workbook.xml', zipfile.ZipFile(io.BytesIO(r.content)).namelist())

    def test_parameter_buruk_404(self):
        self.client.login(username='admin@example.com', password='rahasia-123')
        for q in ({'jenis': 'xx'}, {'dari': 'bukan-tanggal'}, {'dari': '2026-02-01', 'sampai': '2026-01-01'}):
            self.assertEqual(self.client.get(self._url(**q)).status_code, 404)

    def test_halaman_laporan_punya_tautan_unduh(self):
        self.client.login(username='admin@example.com', password='rahasia-123')
        html = self.client.get(reverse('admin_laporan')).content.decode()
        self.assertIn(reverse('admin_laporan_unduh'), html)
        self.assertNotIn('disabled', html.split('lp-table')[1])
