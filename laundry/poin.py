"""Logika poin & penautan pesanan ke akun (view dan signal tetap tipis)."""
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Sum

from .models import Booking, PoinLog, Profile
from .services import HADIAH, hitung_poin, normalisasi_wa, rupiah


def saldo_poin(user_id):
    return PoinLog.objects.filter(user_id=user_id).aggregate(total=Sum('jumlah'))['total'] or 0


def cari_akun_dari_wa(whatsapp):
    """Akun pelanggan yang nomor WhatsApp-nya cocok. Hanya bila cocok TEPAT satu akun; selain itu None."""
    nomor = normalisasi_wa(whatsapp)
    if not nomor:
        return None
    ids = list(
        Profile.objects.filter(whatsapp=nomor, role=Profile.Role.USER, user__is_active=True)
        .values_list('user_id', flat=True)[:2]
    )
    if len(ids) != 1:
        return None  # tidak ada, atau ambigu -> jangan menebak
    return get_user_model()._default_manager.get(pk=ids[0])


def tautkan_booking(booking, user=None):
    """Isi booking.user dan booking.asal (belum menyimpan). Urutan: akun yang login > cocok WhatsApp > tamu."""
    if user is not None and user.is_authenticated:
        booking.user, booking.asal = user, 'akun'
        return
    pemilik = cari_akun_dari_wa(booking.whatsapp)
    if pemilik:
        booking.user, booking.asal = pemilik, 'whatsapp'
    else:
        booking.user, booking.asal = None, 'tamu'


def catat_poin_pesanan(booking):
    """Beri poin saat pesanan selesai. Aman dipanggil berulang: satu pesanan hanya memberi poin sekali."""
    if booking.status != 'selesai' or not booking.user_id:
        return None
    jumlah = hitung_poin(booking.total)
    if jumlah <= 0:
        return None
    try:
        with transaction.atomic():
            if PoinLog.objects.filter(booking=booking, jumlah__gt=0).exists():
                return None
            return PoinLog.objects.create(
                user_id=booking.user_id, booking=booking, jumlah=jumlah,
                saldo=saldo_poin(booking.user_id) + jumlah,
                keterangan='Pesanan selesai',
            )
    except IntegrityError:  # dua proses menyimpan bersamaan; yang kedua dibatalkan oleh constraint
        return None


def pesanan_aktif(user):
    return Booking.objects.filter(user=user).exclude(status__in=('selesai', 'dibatalkan'))


def konteks_poin_hadiah(user, tab=''):
    saldo = saldo_poin(user.pk)
    hadiah = [
        {**h, 'poin_fmt': rupiah(h['poin']), 'bisa': saldo >= h['poin'], 'kurang': max(0, h['poin'] - saldo)}
        for h in HADIAH
    ]
    bisa = [h for h in hadiah if h['bisa']]
    tab = 'bisa' if tab == 'bisa' else 'semua'
    target = next((h for h in hadiah if not h['bisa']), hadiah[-1])  # hadiah terdekat yang belum tercapai
    menunggu = list(pesanan_aktif(user).order_by('-dibuat', '-id'))
    return {
        'saldo': saldo,
        'tab': tab,
        'hadiah': bisa if tab == 'bisa' else hadiah,
        'jumlah_bisa': len(bisa),
        'target': target,
        'target_persen': min(100, saldo * 100 // target['poin']),
        'saldo_fmt': rupiah(saldo),
        'poin_menunggu': sum(b.poin for b in menunggu),
        'pesanan_menunggu': menunggu[0] if menunggu else None,
        'riwayat': list(PoinLog.objects.filter(user=user).select_related('booking')[:20]),
    }
