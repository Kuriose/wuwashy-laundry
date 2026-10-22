"""Data untuk halaman "Pesanan saya" (hanya pesanan milik akun yang login)."""
from .poin import pesanan_aktif
from .services import rupiah


def konteks_pesanan_saya(user, tab=''):
    aktif = list(pesanan_aktif(user).order_by('-dibuat', '-id'))
    menunggu = [b for b in aktif if b.status == 'menunggu']
    tab = 'menunggu' if tab == 'menunggu' else 'aktif'
    return {
        'tab': tab,
        'pesanan': menunggu if tab == 'menunggu' else aktif,
        'jumlah_aktif': len(aktif),
        'jumlah_menunggu': len(menunggu),
        'utama': aktif[0] if aktif else None,  # alamat & catatan di kolom kanan
        'estimasi_terdekat': min((b.estimasi_selesai for b in aktif), default=None),
        'total_aktif': rupiah(sum(b.total for b in aktif)),
    }


def konteks_lacak_beranda(user, batas=3):
    """Pesanan aktif terbaru untuk kartu "Lacak cucianmu" di Beranda (maksimal `batas`; sisanya hanya dihitung).

    "Aktif" = semua tahap sebelum selesai/dibatalkan, jadi bar progres sudah tampil sejak pesanan dibuat
    (status 'menunggu'), bukan baru setelah dijemput.
    """
    aktif = pesanan_aktif(user).order_by('-dibuat', '-id')
    jumlah = aktif.count()
    return {
        'lacak': list(aktif[:batas]),
        'jumlah_aktif': jumlah,
        'lacak_sisa': max(0, jumlah - batas),
    }
