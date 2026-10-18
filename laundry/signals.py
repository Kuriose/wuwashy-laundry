from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Booking, Profile
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
