"""Data halaman "Riwayat pesanan": pesanan yang sudah berakhir (selesai atau dibatalkan) milik satu akun.

OOP - Enkapsulasi: seluruh logika halaman (membaca dan memvalidasi parameter filter, menyusun query,
menghitung ringkasan, membagi halaman) dibungkus di kelas RiwayatPesanan. View cukup membuat objeknya
dan memanggil ringkasan() dan halaman(); detail query dan atribut internal (_user, _semua, ...) tidak bocor ke luar.
"""
from datetime import timedelta
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Q, Sum
from django.template.defaultfilters import date as format_tanggal
from django.utils import timezone

from .models import Booking, PoinLog
from .services import LAYANAN, rupiah


class RiwayatPesanan:
    STATUS_RIWAYAT = ('selesai', 'dibatalkan')
    UKURAN_HALAMAN = 10
    PERIODE = [('semua', 'Semua tanggal'), ('30', '30 hari terakhir'), ('90', '3 bulan terakhir'), ('tahun', 'Tahun ini')]

    def __init__(self, user, params):
        self._user = user
        self._semua = Booking.objects.filter(user=user, status__in=self.STATUS_RIWAYAT)
        # Parameter dari URL tidak dipercaya begitu saja: nilai yang tidak dikenal dikembalikan ke bawaan.
        self.cari = params.get('cari', '').strip().lstrip('#').strip()[:50]
        periode = params.get('periode', '')
        self.periode = periode if periode in dict(self.PERIODE) else 'semua'
        layanan = params.get('layanan', '')
        self.layanan = layanan if layanan in LAYANAN else ''

    @property
    def pilihan_layanan(self):
        return [(kode, s['nama']) for kode, s in LAYANAN.items()]

    @property
    def ada_filter(self):
        return bool(self.cari or self.layanan or self.periode != 'semua')

    # ---------- query ----------
    def _terfilter(self):
        qs = self._semua
        if self.cari:
            kode_cocok = [kode for kode, s in LAYANAN.items() if self.cari.lower() in s['nama'].lower()]
            qs = qs.filter(Q(resi__icontains=self.cari) | Q(layanan__in=kode_cocok))
        if self.layanan:
            qs = qs.filter(layanan=self.layanan)
        mulai = self._batas_awal()
        if mulai:
            qs = qs.filter(dibuat__gte=mulai)
        return qs.order_by('-dibuat', '-id')

    def _batas_awal(self):
        sekarang = timezone.now()
        if self.periode == '30':
            return sekarang - timedelta(days=30)
        if self.periode == '90':
            return sekarang - timedelta(days=90)
        if self.periode == 'tahun':
            return timezone.localtime(sekarang).replace(month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        return None

    # ---------- ringkasan (tiga kartu di atas; selalu dari SEMUA pesanan selesai, tidak ikut filter) ----------
    def ringkasan(self):
        selesai = list(self._semua.filter(status='selesai'))
        poin = PoinLog.objects.filter(user=self._user, jumlah__gt=0).aggregate(n=Sum('jumlah'))['n'] or 0
        return {
            'jumlah': len(selesai),
            'rentang': self._rentang(selesai),
            'total': rupiah(sum(b.total for b in selesai)),
            'poin': poin,
        }

    @staticmethod
    def _rentang(selesai):
        if not selesai:
            return 'Belum ada pesanan selesai'
        awal = timezone.localtime(min(b.dibuat for b in selesai))
        akhir = timezone.localtime(max(b.dibuat for b in selesai))
        if (awal.year, awal.month) == (akhir.year, akhir.month):
            return format_tanggal(awal, 'F Y')
        if awal.year == akhir.year:
            return f"{format_tanggal(awal, 'F')} \u2013 {format_tanggal(akhir, 'F Y')}"
        return f"{format_tanggal(awal, 'M Y')} \u2013 {format_tanggal(akhir, 'M Y')}"

    # ---------- tabel ----------
    def halaman(self, nomor):
        """Satu halaman pesanan; tiap pesanan diberi atribut poin_didapat (poin yang benar-benar masuk)."""
        hal = Paginator(self._terfilter(), self.UKURAN_HALAMAN).get_page(nomor)
        poin = dict(PoinLog.objects.filter(booking__in=list(hal), jumlah__gt=0).values_list('booking_id', 'jumlah'))
        for b in hal:
            b.poin_didapat = poin.get(b.pk, 0)
        return hal

    def qs_halaman(self):
        """Awalan query untuk tautan halaman: mempertahankan filter. Contoh: 'cari=reguler&periode=30&'."""
        data = {k: v for k, v in (('cari', self.cari), ('periode', self.periode if self.periode != 'semua' else ''),
                                  ('layanan', self.layanan)) if v}
        return urlencode(data) + '&' if data else ''
