"""Data untuk halaman "Anggota Tim" di panel admin."""
from .models import AnggotaTim


def ringkasan_tim():
    anggota = list(AnggotaTim.objects.all())
    aktif = [a for a in anggota if a.aktif]
    return {
        'anggota': anggota,
        'total': len(anggota),
        'total_aktif': len(aktif),
        'kasir_aktif': sum(1 for a in aktif if a.peran == AnggotaTim.Peran.KASIR),
        'kurir_aktif': sum(1 for a in aktif if a.peran == AnggotaTim.Peran.KURIR),
    }
