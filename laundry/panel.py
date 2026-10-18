"""Data ringkasan untuk dashboard admin (view tetap tipis, logika hitung di sini)."""
from datetime import date

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Booking
from .services import rupiah

# (kunci, label, status Booking yang masuk kelompok, warna di donut)
KELOMPOK = (
    ('menunggu', 'Menunggu', ('menunggu',), '#0b1230'),
    ('diproses', 'Diproses', ('dijemput', 'diproses'), '#1e96fc'),
    ('siap', 'Siap Diambil', ('siap', 'diantar'), '#2fc4a8'),
    ('selesai', 'Selesai', ('selesai',), '#ccff48'),
    ('dibatalkan', 'Dibatalkan', ('dibatalkan',), '#9aa4bd'),
)
_KELOMPOK_DARI_STATUS = {s: (key, label) for key, label, statuses, _ in KELOMPOK for s in statuses}
_LANGKAH_SKALA = (1, 2, 5, 10, 20, 25, 40, 50, 100, 200, 250, 400, 500, 1000, 2000, 5000)


def kelompok_status(status):
    """Status Booking -> (kunci, label) kelompok dashboard."""
    return _KELOMPOK_DARI_STATUS.get(status, ('menunggu', 'Menunggu'))


def _hitung_kelompok(qs):
    mentah = {r['status']: r['n'] for r in qs.order_by().values('status').annotate(n=Count('id'))}
    return {key: sum(mentah.get(s, 0) for s in statuses) for key, _, statuses, _ in KELOMPOK}


def skala_sumbu(maks):
    """Tinggi sumbu Y yang 'rapi': 4 interval, mis. maks 160 -> [160, 120, 80, 40, 0]."""
    langkah = next((s for s in _LANGKAH_SKALA if s * 4 >= maks), None)
    if langkah is None:
        langkah = -(-maks // 4)  # pembulatan ke atas
    return [langkah * i for i in range(4, -1, -1)]


def _desimal(angka, digit=1):
    return f'{angka:.{digit}f}'.replace('.', ',')


def _gradien_donut(jumlah, total):
    if not total:
        return 'conic-gradient(#e3e8f3 0 100%)'
    potongan, awal = [], 0.0
    for key, _, _, warna in KELOMPOK:
        n = jumlah[key]
        if not n:
            continue
        akhir = awal + n * 100 / total
        potongan.append(f'{warna} {awal:.2f}% {akhir:.2f}%')
        awal = akhir
    return f"conic-gradient({', '.join(potongan)})"


def hitung_sidebar():
    """Angka di sidebar admin (seluruh waktu), dipakai semua halaman panel."""
    jumlah = _hitung_kelompok(Booking.objects.all())
    return {'semua': rupiah(sum(jumlah.values())), **{k: rupiah(v) for k, v in jumlah.items()}}


def ringkasan(sekarang=None):
    sekarang = timezone.localtime(sekarang or timezone.now())
    awal_hari = sekarang.replace(hour=0, minute=0, second=0, microsecond=0)
    awal_bulan = awal_hari.replace(day=1)

    semua = Booking.objects.all()
    bulan = semua.filter(dibuat__gte=awal_bulan)

    # --- kartu statistik, grafik, donut: periode bulan berjalan ---
    jml = _hitung_kelompok(bulan)
    total = sum(jml.values())
    aktif = jml['menunggu'] + jml['diproses'] + jml['siap']
    tingkat = jml['selesai'] * 100 / total if total else 0

    # --- grafik volume harian (tanggal 1 s.d. hari ini) ---
    per_hari = {
        r['hari']: r['n']
        for r in bulan.annotate(hari=TruncDate('dibuat')).order_by().values('hari').annotate(n=Count('id'))
    }
    tanggal = [date(sekarang.year, sekarang.month, d) for d in range(1, sekarang.day + 1)]
    nilai = [per_hari.get(t, 0) for t in tanggal]
    sumbu = skala_sumbu(max(nilai))
    puncak = sumbu[0] or 1
    batang = [
        {'tanggal': t, 'jumlah': n, 'persen': round(n * 100 / puncak), 'label': i % 2 == 0}
        for i, (t, n) in enumerate(zip(tanggal, nilai))
    ]

    # --- sidebar: seluruh waktu ---
    semua_jml = _hitung_kelompok(semua)

    terbaru = [
        {
            'pk': b.pk, 'resi': b.resi, 'nama': b.nama, 'whatsapp': b.whatsapp,
            'tanggal': timezone.localtime(b.dibuat), 'layanan': b.nama_layanan,
            'total': rupiah(b.total), 'penyerahan': b.penyerahan,
            'status_key': kelompok_status(b.status)[0], 'status_label': kelompok_status(b.status)[1],
        }
        for b in semua.order_by('-dibuat', '-id')[:5]
    ]

    return {
        'sekarang': sekarang,
        'awal_bulan': awal_bulan,
        'stat': {
            'total': rupiah(total),
            'masuk_hari_ini': rupiah(bulan.filter(dibuat__gte=awal_hari).count()),
            'aktif': rupiah(aktif),
            'selesai': rupiah(jml['selesai']),
            'selesai_hari_ini': rupiah(semua.filter(status='selesai', diperbarui__gte=awal_hari).count()),
            'tingkat': _desimal(tingkat),
        },
        'jml': {k: rupiah(v) for k, v in jml.items()},
        'jumlah_siap': jml['siap'],
        'donut': {
            'gradien': _gradien_donut(jml, total),
            'legenda': [
                {'label': label, 'jumlah': rupiah(jml[key]), 'warna': warna}
                for key, label, _, warna in KELOMPOK
            ],
        },
        'batang': batang,
        'sumbu': sumbu,
        'sidebar': {'semua': rupiah(sum(semua_jml.values())), **{k: rupiah(v) for k, v in semua_jml.items()}},
        'terbaru': terbaru,
        'jumlah_terbaru': len(terbaru),
        'jumlah_semua': rupiah(sum(semua_jml.values())),
    }
