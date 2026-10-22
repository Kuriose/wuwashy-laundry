"""Pembuat notifikasi pesanan.

Penerapan 4 pilar OOP di file ini:
  1. Abstraksi    : PembuatNotifikasi adalah kelas abstrak (ABC). Pemanggil hanya tahu `buat()`;
                    cara menyusun isi pesan diserahkan ke subkelas lewat method abstrak `isi()`.
  2. Pewarisan    : NotifBerbasisTeks mewarisi PembuatNotifikasi, lalu NotifDiterima, NotifDijemput, dst.
                    mewarisi NotifBerbasisTeks. NotifSelesai menimpa (override) `isi()` untuk menambah info poin.
  3. Polimorfisme : `kirim_notifikasi_status()` memanggil `.buat()` pada kelas apa pun dari DAFTAR tanpa
                    if/else per status; tiap kelas menghasilkan isi pesannya sendiri.
  4. Enkapsulasi  : data pesanan disimpan di atribut internal `_booking`, dan detail pencarian poin
                    disembunyikan di method internal `_teks_poin()`.

Halaman "Notifikasi" juga memanfaatkan polimorfisme: tiap kelas pembuat tahu `tipe`, `ikon`, dan tautan
(`tautan()`) notifikasinya sendiri, sehingga halaman cukup memanggil `pembuat_untuk(tipe)` tanpa if/else per jenis.
"""
from abc import ABC, abstractmethod

from django.urls import reverse

from .models import Notifikasi, PoinLog
from .services import HADIAH


class PembuatNotifikasi(ABC):
    """Kelas dasar abstrak: tidak bisa dibuat langsung, harus lewat subkelas yang mengimplementasikan isi()."""

    judul = ''
    tipe = ''                             # disimpan di Notifikasi.tipe (kode kejadian)
    ikon = 'i-bell'                       # id simbol SVG di dashboard_base.html
    teks_tautan = 'Lihat detail pesanan'  # teks tautan di halaman Notifikasi

    def __init__(self, booking):
        self._booking = booking  # Enkapsulasi: atribut internal, tidak diakses dari luar kelas

    @abstractmethod
    def isi(self) -> str:
        """Teks isi notifikasi. Wajib diimplementasikan subkelas."""

    def buat(self):
        b = self._booking
        if not b.user_id:  # pesanan tamu tanpa akun: tidak ada penerima
            return None
        return Notifikasi.objects.create(user_id=b.user_id, booking=b, tipe=self.tipe, judul=self.judul, isi=self.isi())

    @classmethod
    def tautan(cls, notif):
        """(teks, url) tautan di halaman Notifikasi; None bila notifikasi tidak terkait pesanan. Boleh di-override."""
        if not notif.booking_id:
            return None
        return cls.teks_tautan, f"{reverse('cari_pesanan')}?q={notif.booking.resi}"


class NotifBerbasisTeks(PembuatNotifikasi):
    """Perantara: isi pesan disusun dari templat teks milik subkelas (cukup isi `judul` dan `templat`)."""

    templat = ''

    def isi(self):
        b = self._booking
        return self.templat.format(resi=b.resi, layanan=b.nama_layanan)


class NotifDiterima(NotifBerbasisTeks):
    """Dikirim saat pesanan baru dibuat (status 'menunggu'). Sengaja TIDAK menyebut penjemputan sebagai
    sesuatu yang sedang terjadi: itu baru benar saat status berubah menjadi 'dijemput' (NotifDijemput)."""

    tipe, ikon = 'menunggu', 'i-clock'
    judul = 'Pesanan dibuat'
    templat = 'Pesanan #{resi} ({layanan}) berhasil dibuat. Status: menunggu penjemputan.'


class NotifDijemput(NotifBerbasisTeks):
    tipe, ikon = 'dijemput', 'i-truck'
    judul = 'Pakaian sudah dijemput'
    templat = 'Pakaian untuk pesanan #{resi} sudah kami jemput dan sedang menuju outlet.'


class NotifDiproses(NotifBerbasisTeks):
    tipe, ikon = 'diproses', 'i-iron'
    judul = 'Cucian sedang diproses'
    templat = 'Pesanan #{resi} ({layanan}) sedang kami cuci dan rapikan.'


class NotifSiap(NotifBerbasisTeks):
    tipe, ikon = 'siap', 'i-check'
    judul = 'Cucian siap diambil'
    templat = 'Pesanan #{resi} sudah bersih dan siap diambil atau diantar.'


class NotifDiantar(NotifBerbasisTeks):
    tipe, ikon = 'diantar', 'i-truck'
    judul = 'Cucian sedang diantar'
    templat = 'Kurir sedang mengantar pesanan #{resi}. Mohon siapkan penerima di alamat tujuan.'


class NotifDibatalkan(NotifBerbasisTeks):
    tipe, ikon = 'dibatalkan', 'i-x'
    judul = 'Pesanan dibatalkan'
    templat = 'Pesanan #{resi} dibatalkan. Hubungi kami via WhatsApp bila ini tidak sesuai.'


class NotifSelesai(NotifBerbasisTeks):
    tipe, ikon, teks_tautan = 'selesai', 'i-check', 'Pesan lagi'
    judul = 'Pesanan selesai'
    templat = 'Pesanan #{resi} sudah selesai. Terima kasih sudah memilih WuWashy!'

    def isi(self):  # Pewarisan: override isi() agar pesan selesai ikut menyebut poin
        return super().isi() + self._teks_poin()

    def _teks_poin(self):
        """Enkapsulasi: detail pencarian poin disembunyikan di sini."""
        log = PoinLog.objects.filter(booking=self._booking, jumlah__gt=0).first()
        return f' Kamu mendapat +{log.jumlah} poin.' if log else ''

    @classmethod
    def tautan(cls, notif):  # Pewarisan: pesanan selesai mengajak pelanggan memesan lagi layanan yang sama
        if not notif.booking_id:
            return None
        return cls.teks_tautan, f"{reverse('booking')}?layanan={notif.booking.layanan}"


class NotifPoinMasuk(PembuatNotifikasi):
    """Poin baru masuk ke saldo (kategori "Poin & hadiah"). Judul dan isinya bergantung pada baris PoinLog."""

    tipe, ikon, teks_tautan = 'poin', 'i-sparkles', 'Lihat riwayat poin'

    def __init__(self, booking, log):
        super().__init__(booking)
        self._log = log

    @property
    def judul(self):  # Polimorfisme: subkelas boleh mengganti atribut kelas dengan property
        return f'+{self._log.jumlah} poin masuk ke akunmu'

    def isi(self):
        return f'Pesanan #{self._booking.resi} sudah selesai. Saldo poinmu sekarang {self._log.saldo} poin.'

    @classmethod
    def tautan(cls, notif):
        return cls.teks_tautan, reverse('poin_hadiah')


class NotifHadiah(PembuatNotifikasi):
    """Saldo poin baru saja cukup untuk menukar hadiah."""

    tipe, ikon, teks_tautan = 'hadiah', 'i-gift', 'Lihat hadiah'
    judul = 'Hadiah kecil menantimu!'

    def __init__(self, booking, hadiah, saldo):
        super().__init__(booking)
        self._hadiah, self._saldo = hadiah, saldo

    def isi(self):
        nama = self._hadiah['nama']
        teks = f"Saldo {self._saldo} poinmu cukup untuk {nama[:1].lower()}{nama[1:]} ({self._hadiah['poin']} poin)."
        berikut = next((h for h in HADIAH if h['poin'] > self._saldo), None)
        if berikut:
            teks += f" {berikut['nama']} perlu {berikut['poin'] - self._saldo} poin lagi."
        return teks

    @classmethod
    def tautan(cls, notif):
        return cls.teks_tautan, reverse('poin_hadiah')


# Status Booking -> kelas pembuat notifikasinya
DAFTAR = {
    'menunggu': NotifDiterima,
    'dijemput': NotifDijemput,
    'diproses': NotifDiproses,
    'siap': NotifSiap,
    'diantar': NotifDiantar,
    'selesai': NotifSelesai,
    'dibatalkan': NotifDibatalkan,
}


# Tipe notifikasi -> kelas pembuatnya (dipakai halaman Notifikasi untuk menentukan ikon dan tautan)
PEMBUAT_PER_TIPE = {kelas.tipe: kelas for kelas in (*DAFTAR.values(), NotifPoinMasuk, NotifHadiah)}


def pembuat_untuk(tipe):
    """Kelas pembuat untuk `tipe`; notifikasi lama/tanpa tipe memakai bawaan kelas dasar (ikon lonceng)."""
    return PEMBUAT_PER_TIPE.get(tipe, PembuatNotifikasi)


def kirim_notifikasi_status(booking):
    """Polimorfisme: satu pemanggilan `.buat()` untuk semua status; hasilnya berbeda sesuai kelasnya."""
    kelas = DAFTAR.get(booking.status)
    return kelas(booking).buat() if kelas else None


def kirim_notifikasi_poin(booking):
    """Poin pesanan sudah masuk -> notifikasi poin; plus notifikasi hadiah bila saldo baru melewati batas hadiah.

    Aman dipanggil berulang: satu pesanan hanya menghasilkan notifikasi poin satu kali.
    """
    if booking.status != 'selesai' or not booking.user_id:
        return []
    log = PoinLog.objects.filter(booking=booking, jumlah__gt=0).first()
    if log is None or Notifikasi.objects.filter(booking=booking, tipe=NotifPoinMasuk.tipe).exists():
        return []
    dibuat = [NotifPoinMasuk(booking, log).buat()]
    sebelum = log.saldo - log.jumlah
    tercapai = [h for h in HADIAH if sebelum < h['poin'] <= log.saldo]
    if tercapai:
        dibuat.append(NotifHadiah(booking, tercapai[-1], log.saldo).buat())
    return dibuat
