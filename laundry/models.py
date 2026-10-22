import random
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.db.models import Q
from .services import CHOICES, LAYANAN, hitung_poin, normalisasi_wa, rupiah


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
    status = models.CharField(max_length=20, choices=STATUS, default='menunggu')
    dibuat = models.DateTimeField(auto_now_add=True)
    diperbarui = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-dibuat']

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
    def total(self):
        """Perkiraan tagihan (rupiah) = harga layanan x berat/jumlah."""
        harga = LAYANAN.get(self.layanan, {}).get('harga', 0)
        return int(Decimal(harga) * Decimal(str(self.berat)))

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

    def save(self, *args, **kwargs):
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
