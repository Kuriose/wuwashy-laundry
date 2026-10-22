"""Data halaman "Notifikasi": semua kabar (pesanan, poin, hadiah) milik satu akun.

OOP - Enkapsulasi: seluruh logika halaman (membaca dan memvalidasi parameter filter, menyusun query,
menghitung jumlah, membagi halaman, menandai dibaca) dibungkus di kelas KotakNotifikasi. View cukup membuat
objeknya lalu memanggil halaman() atau tandai_semua_dibaca(); detail query dan atribut internal (_semua, ...)
tidak bocor ke luar.
OOP - Polimorfisme: ikon dan tautan tiap notifikasi ditanyakan ke kelas pembuatnya lewat pembuat_untuk(),
sehingga tidak ada if/else per jenis notifikasi di sini.
"""
from urllib.parse import urlencode

from django.core.paginator import Paginator
from django.db.models import Count, Q

from .models import Notifikasi
from .notifikasi import pembuat_untuk


class KotakNotifikasi:
    UKURAN_HALAMAN = 10
    FILTER = [('semua', 'Semua'), ('belum', 'Belum dibaca'), ('pesanan', 'Pesanan'), ('poin', 'Poin & hadiah')]

    def __init__(self, user, params):
        self._semua = Notifikasi.objects.filter(user=user).select_related('booking')
        self._jumlah = None  # cache hitungan, diisi saat pertama kali dibutuhkan
        # Parameter dari URL tidak dipercaya begitu saja: nilai yang tidak dikenal dikembalikan ke bawaan.
        pilihan = params.get('filter', '')
        self.pilihan = pilihan if pilihan in dict(self.FILTER) else 'semua'

    # ---------- hitungan ----------
    def _hitung(self):
        if self._jumlah is None:
            self._jumlah = self._semua.aggregate(semua=Count('id'), belum=Count('id', filter=Q(dibaca=False)))
        return self._jumlah

    @property
    def jumlah_semua(self):
        return self._hitung()['semua']

    @property
    def jumlah_belum(self):
        return self._hitung()['belum']

    @property
    def tab(self):
        """Daftar (kode, teks) untuk chip filter; Semua dan Belum dibaca menampilkan jumlahnya."""
        jumlah = {'semua': self.jumlah_semua, 'belum': self.jumlah_belum}
        return [(kode, f'{nama} ({jumlah[kode]})' if kode in jumlah else nama) for kode, nama in self.FILTER]

    # ---------- query ----------
    def _terfilter(self):
        qs = self._semua
        if self.pilihan == 'belum':
            qs = qs.filter(dibaca=False)
        elif self.pilihan == 'poin':
            qs = qs.filter(tipe__in=Notifikasi.TIPE_POIN)
        elif self.pilihan == 'pesanan':
            qs = qs.exclude(tipe__in=Notifikasi.TIPE_POIN)
        return qs  # urutan bawaan model: terbaru dulu

    # ---------- daftar ----------
    def halaman(self, nomor):
        """Satu halaman notifikasi; tiap notifikasi diberi atribut ikon dan tautan dari kelas pembuatnya."""
        hal = Paginator(self._terfilter(), self.UKURAN_HALAMAN).get_page(nomor)
        for n in hal:
            pembuat = pembuat_untuk(n.tipe)
            n.ikon, n.tautan = pembuat.ikon, pembuat.tautan(n)
        return hal

    def qs_halaman(self):
        """Awalan query untuk tautan halaman: mempertahankan filter. Contoh: 'filter=belum&'."""
        return urlencode({'filter': self.pilihan}) + '&' if self.pilihan != 'semua' else ''

    # ---------- aksi ----------
    def tandai_semua_dibaca(self):
        """Tandai SEMUA notifikasi akun ini sudah dibaca (tidak terbatas pada filter yang aktif). Mengembalikan jumlahnya."""
        jumlah = self._semua.filter(dibaca=False).update(dibaca=True)
        self._jumlah = None
        return jumlah
