"""Isi laporan Excel untuk halaman Laporan Tersimpan.

OOP:
- Abstraksi + pewarisan: `Laporan` adalah kerangka (abstrak); tiap jenis laporan (Ringkasan, Pendapatan, Rekap,
  Mingguan) mewarisinya dan hanya mengisi `isi()`.
- Polimorfisme: `buat_laporan(jenis, ...)` memanggil `laporan.bangun()` tanpa peduli jenis aslinya; tiap kelas
  menyusun lembarnya sendiri (sama seperti DAFTAR/pembuat_untuk di notifikasi).
- Enkapsulasi: urusan format .xlsx ada di `ekspor.py`; di sini hanya soal "apa isi laporannya".

Kelas bekerja pada objek mirip Booking (resi, dibuat, status, total, berat_efektif, ...), jadi bisa diuji tanpa
database.
"""
from abc import ABC, abstractmethod
from collections import OrderedDict
from datetime import date, datetime, timedelta

from django.utils import timezone

from .ekspor import BukuKerja, Gaya, Sel
from .services import SERVICES

NAMA_BULAN = ('', 'Januari', 'Februari', 'Maret', 'April', 'Mei', 'Juni', 'Juli', 'Agustus',
              'September', 'Oktober', 'November', 'Desember')
STATUS = {
    'menunggu': 'Menunggu penjemputan', 'dijemput': 'Pakaian dijemput', 'diproses': 'Sedang dicuci',
    'siap': 'Siap diambil', 'diantar': 'Sedang diantar', 'selesai': 'Selesai', 'dibatalkan': 'Dibatalkan',
}


def tgl_id(d):
    return f'{d.day} {NAMA_BULAN[d.month]} {d.year}'


def _lokal(dt):
    """datetime berzona waktu -> waktu lokal tanpa zona (aman ditulis ke Excel)."""
    if timezone.is_aware(dt):
        dt = timezone.localtime(dt)
    return dt.replace(tzinfo=None)


def _tgl(b):
    return _lokal(b.dibuat).date()


class Laporan(ABC):
    """Kerangka satu laporan: satu berkas .xlsx berisi satu atau beberapa sheet."""

    jenis = ''
    judul = ''

    def __init__(self, pesanan, dari, sampai, outlet='WuWashy Laundry', dibuat=None):
        self.pesanan = list(pesanan)
        self.dari, self.sampai = dari, sampai
        self.outlet = outlet
        self.dibuat = dibuat or datetime.now()

    # ---- bahan hitung bersama ----
    @property
    def sah(self):
        """Pesanan yang menghasilkan pendapatan: yang sudah selesai."""
        return [b for b in self.pesanan if b.status == 'selesai']

    @property
    def periode_teks(self):
        if self.dari == self.sampai:
            return tgl_id(self.dari)
        return f'{tgl_id(self.dari)} – {tgl_id(self.sampai)}'

    @property
    def nama_berkas(self):
        return f'wuwashy-{self.jenis}-{self.dari.isoformat()}_{self.sampai.isoformat()}.xlsx'

    def hari(self):
        """Semua tanggal dalam periode (berurutan)."""
        n = (self.sampai - self.dari).days + 1
        return [self.dari + timedelta(days=i) for i in range(max(n, 0))]

    def per_layanan(self):
        """[(nama layanan, jumlah pesanan, total berat, pendapatan)] untuk semua layanan."""
        hasil = OrderedDict((s['key'], [s['nama'], 0, 0.0, 0]) for s in SERVICES)
        for b in self.pesanan:
            r = hasil.setdefault(b.layanan, [b.nama_layanan, 0, 0.0, 0])
            r[1] += 1
            r[2] += float(b.berat_efektif)
            if b.status == 'selesai':
                r[3] += b.total
        return [tuple(r) for r in hasil.values()]

    def per_status(self):
        hasil = OrderedDict((k, 0) for k in STATUS)
        for b in self.pesanan:
            hasil[b.status] = hasil.get(b.status, 0) + 1
        return [(STATUS.get(k, k), n) for k, n in hasil.items()]

    def per_hari(self):
        """{tanggal: [pesanan masuk, pesanan selesai, pendapatan]}."""
        hasil = OrderedDict((d, [0, 0, 0]) for d in self.hari())
        for b in self.pesanan:
            r = hasil.setdefault(_tgl(b), [0, 0, 0])
            r[0] += 1
            if b.status == 'selesai':
                r[1] += 1
                r[2] += b.total
        return hasil

    # ---- potongan lembar yang dipakai ulang ----
    def kepala(self, lembar, judul, kolom):
        lembar.tambah([judul], Gaya.JUDUL)
        lembar.tambah([f'{self.outlet} · Periode {self.periode_teks}'], Gaya.KETERANGAN)
        lembar.tambah([f'Dibuat {tgl_id(self.dibuat)} pukul {self.dibuat:%H.%M}'], Gaya.KETERANGAN)
        lembar.kosong()

    @staticmethod
    def tabel(lembar, header, baris, gaya_kolom, total=None):
        """Header + baris data (+ baris total). `gaya_kolom`: gaya per kolom. Mengembalikan nomor baris header."""
        lembar.tambah(header, Gaya.HEADER)
        nomor_header = lembar.jumlah_baris
        for r in baris:
            lembar.tambah([Sel(v, g) for v, g in zip(r, gaya_kolom)])
        if total is not None:
            lembar.tambah([Sel(v, g) for v, g in total])
        return nomor_header

    @abstractmethod
    def isi(self, buku):
        """Isi `buku` (BukuKerja) dengan sheet milik laporan ini."""

    def bangun(self):
        buku = BukuKerja()
        self.isi(buku)
        return buku.simpan()


class LaporanRingkasan(Laporan):
    jenis, judul = 'ringkasan', 'Ringkasan operasional'

    def isi(self, buku):
        l = buku.lembar('Ringkasan').lebar_kolom(30, 18, 16, 20)
        self.kepala(l, self.judul, 4)
        total = len(self.pesanan)
        sah = self.sah
        batal = sum(1 for b in self.pesanan if b.status == 'dibatalkan')
        l.tambah(['Indikator', 'Nilai'], Gaya.HEADER)
        for nama, nilai, g in (
            ('Total pesanan masuk', total, Gaya.ANGKA),
            ('Pesanan selesai', len(sah), Gaya.ANGKA),
            ('Pesanan dibatalkan', batal, Gaya.ANGKA),
            ('Pesanan masih berjalan', total - len(sah) - batal, Gaya.ANGKA),
            ('Total berat/jumlah cucian', sum(float(b.berat_efektif) for b in self.pesanan), Gaya.DESIMAL),
            ('Pendapatan (pesanan selesai)', sum(b.total for b in sah), Gaya.RUPIAH),
            ('Rata-rata nilai pesanan selesai', round(sum(b.total for b in sah) / len(sah)) if sah else 0, Gaya.RUPIAH),
            ('Tingkat penyelesaian', (len(sah) / total) if total else 0, Gaya.PERSEN),
        ):
            l.tambah([nama, Sel(nilai, g)])
        l.kosong()
        l.tambah(['Pesanan menurut status', 'Jumlah'], Gaya.HEADER)
        for nama, n in self.per_status():
            l.tambah([nama, Sel(n, Gaya.ANGKA)])
        l.kosong()
        layanan = self.per_layanan()
        self.tabel(l, ['Layanan', 'Pesanan', 'Berat/Jumlah', 'Pendapatan'], layanan,
                   (Gaya.BIASA, Gaya.ANGKA, Gaya.DESIMAL, Gaya.RUPIAH),
                   total=[('Total', Gaya.TEBAL), (sum(r[1] for r in layanan), Gaya.TOTAL_ANGKA),
                          (sum(r[2] for r in layanan), Gaya.TOTAL_ANGKA), (sum(r[3] for r in layanan), Gaya.TOTAL_RUPIAH)])


class LaporanPendapatan(Laporan):
    jenis, judul = 'pendapatan', 'Laporan pendapatan'

    def isi(self, buku):
        l = buku.lembar('Pendapatan').lebar_kolom(18, 16, 20)
        self.kepala(l, self.judul, 3)
        l.tambah([Sel('Pendapatan dihitung dari pesanan berstatus Selesai (berat hasil timbang + koreksi harga).', Gaya.KETERANGAN)])
        l.kosong()
        hari = [(d, r[1], r[2]) for d, r in self.per_hari().items()]
        self.tabel(l, ['Tanggal', 'Pesanan selesai', 'Pendapatan'], hari, (Gaya.TANGGAL, Gaya.ANGKA, Gaya.RUPIAH),
                   total=[('Total', Gaya.TEBAL), (sum(r[1] for r in hari), Gaya.TOTAL_ANGKA), (sum(r[2] for r in hari), Gaya.TOTAL_RUPIAH)])
        k = buku.lembar('Per layanan').lebar_kolom(26, 14, 16, 20)
        self.kepala(k, 'Pendapatan per layanan', 4)
        layanan = self.per_layanan()
        jumlah = sum(r[3] for r in layanan)
        self.tabel(k, ['Layanan', 'Pesanan', 'Berat/Jumlah', 'Pendapatan'], layanan,
                   (Gaya.BIASA, Gaya.ANGKA, Gaya.DESIMAL, Gaya.RUPIAH),
                   total=[('Total', Gaya.TEBAL), (sum(r[1] for r in layanan), Gaya.TOTAL_ANGKA),
                          (sum(r[2] for r in layanan), Gaya.TOTAL_ANGKA), (jumlah, Gaya.TOTAL_RUPIAH)])


class LaporanRekap(Laporan):
    jenis, judul = 'rekap', 'Rekap pesanan'

    def isi(self, buku):
        l = buku.lembar('Rekap pesanan').lebar_kolom(14, 18, 22, 16, 18, 12, 14, 22, 18, 40)
        self.kepala(l, self.judul, 10)
        header = ['No. Resi', 'Tanggal pesan', 'Pelanggan', 'WhatsApp', 'Layanan', 'Berat/Jumlah', 'Total', 'Status', 'Asal pesanan', 'Alamat']
        baris = sorted(self.pesanan, key=lambda b: _lokal(b.dibuat))
        l.tambah(header, Gaya.HEADER)
        nomor_header = l.jumlah_baris
        for b in baris:
            l.tambah([b.resi, Sel(_lokal(b.dibuat), Gaya.WAKTU), b.nama, b.whatsapp, b.nama_layanan,
                      Sel(float(b.berat_efektif), Gaya.DESIMAL), Sel(b.total, Gaya.RUPIAH),
                      STATUS.get(b.status, b.status), getattr(b, 'asal', ''), (b.alamat or '').replace('\n', ' ')])
        if baris:
            l.filter_otomatis(nomor_header, len(header), l.jumlah_baris)
            l.tambah([Sel('Total', Gaya.TEBAL)] + [''] * 4 + [Sel(sum(float(b.berat_efektif) for b in baris), Gaya.TOTAL_ANGKA),
                      Sel(sum(b.total for b in baris if b.status == 'selesai'), Gaya.TOTAL_RUPIAH)])
            l.tambah([Sel('Total hanya menjumlah pesanan berstatus Selesai.', Gaya.KETERANGAN)])
        l.bekukan(nomor_header, 1)


class LaporanMingguan(Laporan):
    jenis, judul = 'mingguan', 'Kinerja layanan mingguan'

    def isi(self, buku):
        l = buku.lembar('Kinerja mingguan').lebar_kolom(26, 16, 18, 20)
        self.kepala(l, self.judul, 4)
        layanan = self.per_layanan()
        total = sum(r[1] for r in layanan)
        baris = [(r[0], r[1], (r[1] / total) if total else 0, r[3]) for r in layanan]
        self.tabel(l, ['Layanan', 'Pesanan', 'Porsi pesanan', 'Pendapatan'], baris,
                   (Gaya.BIASA, Gaya.ANGKA, Gaya.PERSEN, Gaya.RUPIAH),
                   total=[('Total', Gaya.TEBAL), (total, Gaya.TOTAL_ANGKA), ('', Gaya.TEBAL), (sum(r[3] for r in layanan), Gaya.TOTAL_RUPIAH)])
        l.kosong()
        hari = [(d, r[0], r[1], r[2]) for d, r in self.per_hari().items()]
        self.tabel(l, ['Tanggal', 'Pesanan masuk', 'Pesanan selesai', 'Pendapatan'], hari,
                   (Gaya.TANGGAL, Gaya.ANGKA, Gaya.ANGKA, Gaya.RUPIAH))


DAFTAR = {k.jenis: k for k in (LaporanRingkasan, LaporanPendapatan, LaporanRekap, LaporanMingguan)}


def buat_laporan(jenis, pesanan, dari, sampai, **kw):
    """Polimorfisme: pilih kelas dari `jenis`. Jenis tak dikenal -> KeyError."""
    return DAFTAR[jenis](pesanan, dari, sampai, **kw)


def pesanan_periode(qs, dari, sampai):
    """Filter queryset Booking ke rentang tanggal lokal [dari, sampai] (inklusif)."""
    zona = timezone.get_current_timezone()
    awal = timezone.make_aware(datetime.combine(dari, datetime.min.time()), zona)
    akhir = timezone.make_aware(datetime.combine(sampai + timedelta(days=1), datetime.min.time()), zona)
    return qs.filter(dibuat__gte=awal, dibuat__lt=akhir).order_by('dibuat')
