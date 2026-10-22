import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models, transaction
from django.db.models import Q
from django.template.defaultfilters import date as format_tanggal
from django.utils import timezone
from .services import CHOICES, LAYANAN, PROVINSI, hitung_poin, normalisasi_wa, rupiah, wa_lokal


class TagihanTerkunci(Exception):
    """Dilempar saat tagihan diubah padahal poin pesanan sudah diberikan.

    OOP - Pewarisan: kelas pengecualian sendiri yang mewarisi Exception, agar view bisa
    menangkap kasus ini secara spesifik (bukan lewat pengecekan teks error).
    """


class Booking(models.Model):
    STATUS = [
        ('menunggu', 'Menunggu penjemputan'),
        ('dijemput', 'Pakaian dijemput'),
        ('diproses', 'Sedang dicuci'),
        ('siap', 'Siap diambil'),
        ('diantar', 'Sedang diantar'),
        ('selesai', 'Selesai'),
        ('dibatalkan', 'Dibatalkan'),
    ]
    # Urutan tahap pesanan yang berjalan normal (untuk pelacakan). 'dibatalkan' di luar alur.
    ALUR = ('menunggu', 'dijemput', 'diproses', 'siap', 'diantar', 'selesai')

    # Dari mana pesanan ini terhubung ke akun (berguna untuk analitik admin).
    ASAL = [
        ('akun', 'Login saat memesan'),
        ('whatsapp', 'Dicocokkan lewat nomor WhatsApp'),
        ('tamu', 'Tamu (tanpa akun)'),
    ]

    resi = models.CharField(max_length=20, unique=True, editable=False)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL,
                             related_name='pesanan')
    asal = models.CharField(max_length=10, choices=ASAL, default='tamu')
    nama = models.CharField(max_length=100)
    whatsapp = models.CharField(max_length=20)
    layanan = models.CharField(max_length=20, choices=CHOICES, default='reguler')
    berat = models.DecimalField(max_digits=5, decimal_places=1)
    alamat = models.TextField()
    catatan = models.TextField(blank=True)
    # Tagihan: diisi admin setelah cucian ditimbang. Kosong/0 = pakai estimasi pelanggan.
    berat_final = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True,
                                      help_text='Berat/jumlah hasil timbang. Kosong = pakai estimasi pelanggan.')
    koreksi_harga = models.IntegerField(default=0, help_text='Penyesuaian harga (Rp). Positif = tambah, negatif = potongan.')
    catatan_koreksi = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default='menunggu')
    dibuat = models.DateTimeField(auto_now_add=True)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-dibuat']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Enkapsulasi: status awal disimpan di atribut internal (_status_awal) agar signal bisa
        # mendeteksi perubahan status tanpa query tambahan. Pihak luar cukup memakai `status_berubah`.
        self._status_awal = self.__dict__.get('status')

    @property
    def status_berubah(self):
        return self.status != self._status_awal

    def save(self, *args, **kwargs):
        if not self.resi:
            while True:
                kode = f'WWSH-{random.randint(10000, 99999)}'
                if not Booking.objects.filter(resi=kode).exists():
                    self.resi = kode
                    break
        super().save(*args, **kwargs)

    @property
    def langkah(self):
        if self.status not in self.ALUR:  # dibatalkan: tidak ada pelacakan
            return []
        label = dict(self.STATUS)
        idx = self.ALUR.index(self.status)
        return [{'label': label[k], 'done': i <= idx, 'now': i == idx} for i, k in enumerate(self.ALUR)]

    @property
    def nama_layanan(self):
        return LAYANAN.get(self.layanan, {}).get('nama', self.layanan)

    @property
    def berat_efektif(self):
        """Berat yang dipakai menghitung tagihan: hasil timbang bila sudah ada, kalau belum estimasi pelanggan."""
        return self.berat_final if self.berat_final is not None else self.berat

    @property
    def dasar(self):
        """Harga layanan x berat (belum termasuk koreksi)."""
        harga = LAYANAN.get(self.layanan, {}).get('harga', 0)
        return int(Decimal(harga) * Decimal(str(self.berat_efektif)))

    @property
    def total(self):
        """Tagihan akhir = dasar + koreksi, tidak pernah di bawah nol."""
        return max(0, self.dasar + int(self.koreksi_harga or 0))

    @property
    def dasar_fmt(self):
        return rupiah(self.dasar)

    @property
    def koreksi_fmt(self):
        n = int(self.koreksi_harga or 0)
        return f"{'+' if n >= 0 else '-'}Rp {rupiah(abs(n))}"

    @property
    def tagihan_terkunci(self):
        """True bila poin pesanan sudah diberikan: tagihan tidak boleh diubah lagi agar buku poin tetap sesuai."""
        return self.pk is not None and self.poin_log.filter(jumlah__gt=0).exists()

    def terapkan_tagihan(self, berat_final, koreksi_harga=0, catatan_koreksi=''):
        """Isi berat timbang dan koreksi harga, lalu simpan.

        Enkapsulasi: aturan "tagihan dikunci setelah poin diberikan" ada di dalam model, jadi view/form
        tidak perlu tahu detailnya; mereka cukup memanggil method ini dan menangkap TagihanTerkunci.
        """
        if self.tagihan_terkunci:
            raise TagihanTerkunci('Poin pesanan ini sudah diberikan, tagihan tidak bisa diubah lagi.')
        self.berat_final = berat_final
        self.koreksi_harga = int(koreksi_harga or 0)
        self.catatan_koreksi = catatan_koreksi or ''
        self.save()

    @property
    def total_fmt(self):
        return rupiah(self.total)

    @property
    def harga_satuan_fmt(self):
        return rupiah(LAYANAN.get(self.layanan, {}).get('harga', 0))

    @property
    def satuan(self):
        return LAYANAN.get(self.layanan, {}).get('satuan', 'kg')

    @property
    def estimasi_selesai(self):
        """Perkiraan waktu selesai = waktu pesan + lama pengerjaan layanan."""
        return self.dibuat + timedelta(hours=LAYANAN.get(self.layanan, {}).get('jam', 48))

    @property
    def poin(self):
        """Poin yang akan didapat pemilik akun begitu pesanan selesai."""
        return hitung_poin(self.total)

    @property
    def penyerahan(self):
        # Form booking saat ini hanya menyediakan penjemputan (alamat wajib diisi).
        return 'Jemput & antar'

    def __str__(self):
        return f'{self.resi} - {self.nama}'


class Profile(models.Model):
    """Profil tambahan untuk tiap akun. Menyimpan role: pelanggan (USER) atau admin usaha (ADMIN)."""

    class Role(models.TextChoices):
        USER = 'USER', 'Pelanggan'
        ADMIN = 'ADMIN', 'Admin'

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)
    # Disimpan dalam bentuk 62812xxxx (lihat services.normalisasi_wa) agar bisa dicocokkan dengan booking tamu.
    whatsapp = models.CharField(max_length=20, blank=True, db_index=True)
    # Data halaman "Akun saya" (alamat ada di model Alamat).
    nama_panggilan = models.CharField(max_length=50, blank=True)
    tanggal_lahir = models.DateField(null=True, blank=True)
    # Preferensi notifikasi (halaman "Pengaturan").
    notif_status_pesanan = models.BooleanField(default=True)
    notif_whatsapp = models.BooleanField(default=True)
    notif_email = models.BooleanField(default=False)
    notif_poin = models.BooleanField(default=True)
    notif_promo = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        # Enkapsulasi: normalisasi nomor WA dijaga di dalam model, apa pun sumber datanya.
        self.whatsapp = normalisasi_wa(self.whatsapp)
        super().save(*args, **kwargs)

    @classmethod
    def untuk(cls, user):
        """Ambil profil user; dibuat otomatis bila belum ada (superuser otomatis ADMIN)."""
        role = cls.Role.ADMIN if user.is_superuser else cls.Role.USER
        profile, _ = cls.objects.get_or_create(user=user, defaults={'role': role})
        return profile

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN

    @property
    def whatsapp_tampil(self):
        """Nomor WA untuk ditampilkan: 6281234567890 -> 0812 3456 7890."""
        return wa_lokal(self.whatsapp)

    def __str__(self):
        return f'{self.user} ({self.role})'


class PoinLog(models.Model):
    """Buku besar poin pelanggan: +poin dari pesanan selesai, -poin saat ditukar hadiah."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='poin_log')
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name='poin_log')
    jumlah = models.IntegerField(help_text='Positif = poin masuk, negatif = poin dipakai.')
    saldo = models.IntegerField(help_text='Saldo poin sesudah transaksi ini.')
    keterangan = models.CharField(max_length=100)
    dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dibuat', '-id']
        constraints = [
            # satu pesanan hanya boleh memberi poin satu kali, walau status disimpan berulang
            models.UniqueConstraint(fields=['booking'], condition=Q(jumlah__gt=0), name='poin_masuk_unik_per_pesanan'),
        ]

    def __str__(self):
        return f'{self.user} {self.jumlah:+d} (saldo {self.saldo})'


class Notifikasi(models.Model):
    """Pemberitahuan untuk pelanggan, dibuat otomatis saat status pesanannya berubah (lihat notifikasi.py)."""

    # Tipe yang masuk kategori "Poin & hadiah"; tipe lain (status pesanan) masuk kategori "Pesanan".
    TIPE_POIN = ('poin', 'hadiah')

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='notifikasi')
    booking = models.ForeignKey(Booking, null=True, blank=True, on_delete=models.SET_NULL, related_name='notifikasi')
    # Kode kejadian pembuatnya: status pesanan ('diproses', ...), 'poin', atau 'hadiah'. Dipakai memilih ikon dan tautan.
    tipe = models.CharField(max_length=20, blank=True)
    judul = models.CharField(max_length=100)
    isi = models.CharField(max_length=255)
    dibaca = models.BooleanField(default=False)
    dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-dibuat', '-id']
        indexes = [models.Index(fields=['user', 'dibaca'])]

    @classmethod
    def jumlah_belum_dibaca(cls, user):
        return cls.objects.filter(user=user, dibaca=False).count()

    @property
    def kategori(self):
        return 'Poin & hadiah' if self.tipe in self.TIPE_POIN else 'Pesanan'

    @property
    def waktu_tampil(self):
        """'Hari ini · 10.45', 'Kemarin · 16.30', atau '2 Oktober 2026 · 16.30' (jam lokal)."""
        lokal = timezone.localtime(self.dibuat)
        hari = (timezone.localtime().date() - lokal.date()).days
        tanggal = {0: 'Hari ini', 1: 'Kemarin'}.get(hari) or format_tanggal(lokal, 'j F Y')
        return f"{tanggal} \u00b7 {format_tanggal(lokal, 'H.i')}"

    def __str__(self):
        return f'{self.user} - {self.judul}'


class Alamat(models.Model):
    """Alamat antar-jemput milik pelanggan. Satu akun boleh punya banyak alamat, tetapi hanya SATU yang utama.

    OOP - Enkapsulasi: aturan "hanya satu alamat utama" dan "alamat pertama otomatis jadi utama" dijaga
    di dalam model (jadikan_utama, hapus_dan_pilih_pengganti, save), bukan tersebar di view/form.
    Database juga menjaganya lewat UniqueConstraint di bawah.
    """

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='alamat')
    label = models.CharField(max_length=30)
    nama_penerima = models.CharField(max_length=100)
    whatsapp = models.CharField(max_length=20)
    alamat_lengkap = models.CharField(max_length=255)
    kecamatan = models.CharField(max_length=60, blank=True)
    kota = models.CharField(max_length=60, default='Samarinda')
    kode_pos = models.CharField(max_length=5, blank=True)
    provinsi = models.CharField(max_length=60, default=PROVINSI)
    catatan_kurir = models.CharField(max_length=200, blank=True)
    utama = models.BooleanField(default=False)
    dibuat = models.DateTimeField(auto_now_add=True)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-utama', '-dibuat', '-id']
        verbose_name_plural = 'Alamat'
        constraints = [
            models.UniqueConstraint(fields=['user'], condition=models.Q(utama=True), name='satu_alamat_utama_per_akun'),
        ]

    def __str__(self):
        return f'{self.user} - {self.label}'

    def save(self, *args, **kwargs):
        self.whatsapp = normalisasi_wa(self.whatsapp) or self.whatsapp
        # alamat pertama milik akun otomatis menjadi alamat utama
        if self._state.adding and not Alamat.objects.filter(user_id=self.user_id).exists():
            self.utama = True
        super().save(*args, **kwargs)

    @classmethod
    def utama_untuk(cls, user):
        """Alamat utama akun (atau alamat terbaru bila entah kenapa belum ada yang utama); None bila belum punya."""
        return cls.objects.filter(user=user).order_by('-utama', '-dibuat', '-id').first()

    @property
    def whatsapp_tampil(self):
        return wa_lokal(self.whatsapp)

    @property
    def baris_alamat(self):
        """Satu baris alamat: 'Jl. Pramuka No. 12, Samarinda Ulu, Samarinda'."""
        return ', '.join(bagian for bagian in (self.alamat_lengkap, self.kecamatan, self.kota) if bagian)

    @transaction.atomic
    def jadikan_utama(self):
        Alamat.objects.filter(user_id=self.user_id, utama=True).exclude(pk=self.pk).update(utama=False)
        Alamat.objects.filter(pk=self.pk).update(utama=True)
        self.utama = True

    @transaction.atomic
    def hapus_dan_pilih_pengganti(self):
        """Hapus alamat ini; bila tadinya utama, alamat terbaru lainnya otomatis menjadi utama."""
        user_id, tadinya_utama = self.user_id, self.utama
        self.delete()
        if tadinya_utama:
            pengganti = Alamat.objects.filter(user_id=user_id).order_by('-dibuat', '-id').first()
            if pengganti:
                pengganti.jadikan_utama()


class AnggotaTim(models.Model):
    """Anggota tim outlet (kasir / kurir) untuk menu "Anggota Tim" di panel admin.

    Untuk saat ini hanya daftar data: anggota belum punya akun login sendiri.
    """

    class Peran(models.TextChoices):
        KASIR = 'kasir', 'Kasir'
        KURIR = 'kurir', 'Kurir'

    nama = models.CharField(max_length=100)
    email = models.EmailField(max_length=150, unique=True,
                              error_messages={'unique': 'Email ini sudah terdaftar sebagai anggota tim.'})
    # Disimpan dalam bentuk 62812xxxx (lihat services.normalisasi_wa); tampilannya lewat telepon_fmt.
    telepon = models.CharField(max_length=20, unique=True,
                               error_messages={'unique': 'Nomor telepon ini sudah dipakai anggota lain.'})
    peran = models.CharField(max_length=10, choices=Peran.choices, default=Peran.KASIR)
    aktif = models.BooleanField(default=True)
    dibuat = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['peran', 'id']  # kasir dulu, lalu kurir; di dalam peran urut sesuai waktu ditambahkan
        verbose_name = 'anggota tim'
        verbose_name_plural = 'anggota tim'

    def save(self, *args, **kwargs):
        self.email = self.email.strip().lower()
        self.telepon = normalisasi_wa(self.telepon) or self.telepon
        super().save(*args, **kwargs)

    @property
    def inisial(self):
        return ''.join(kata[0] for kata in self.nama.split()[:2]).upper()

    @property
    def telepon_fmt(self):
        """'6281211001001' -> '0812-1100-1001'."""
        nomor = '0' + self.telepon[2:] if self.telepon.startswith('62') else self.telepon
        return '-'.join(nomor[i:i + 4] for i in range(0, len(nomor), 4))

    def __str__(self):
        return f'{self.nama} ({self.get_peran_display()})'
