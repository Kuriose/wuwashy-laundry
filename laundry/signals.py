from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Booking, Profile
from .notifikasi import kirim_notifikasi_poin, kirim_notifikasi_status
from .poin import catat_poin_pesanan


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def buat_profile(sender, instance, created, **kwargs):
    """Setiap akun baru otomatis punya profil dengan role USER (superuser: ADMIN)."""
    if created:
        Profile.untuk(instance)


@receiver(post_save, sender=Booking)
def beri_poin_saat_selesai(sender, instance, **kwargs):
    """Admin mengubah status ke 'selesai' (di /admin atau panel) -> poin masuk otomatis ke pemilik akun."""
    catat_poin_pesanan(instance)


@receiver(post_save, sender=Booking)
def beri_notifikasi_pesanan(sender, instance, created, **kwargs):
    """Pesanan baru atau status berubah -> pelanggan pemilik akun mendapat notifikasi.

    Dijalankan SESUDAH beri_poin_saat_selesai (urutan receiver), jadi notifikasi 'selesai' bisa menyebut poin.
    Notifikasi poin/hadiah dicek di setiap simpan karena poin bisa masuk belakangan (mis. tagihan dikoreksi
    sesudah selesai); kirim_notifikasi_poin aman dipanggil berulang.
    """
    if created or instance.status_berubah:
        kirim_notifikasi_status(instance)
    kirim_notifikasi_poin(instance)
    instance._status_awal = instance.status
