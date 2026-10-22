"""Data ringkasan untuk dashboard admin (view tetap tipis, logika hitung di sini)."""
from datetime import date, datetime, time, timedelta
from urllib.parse import urlencode
import calendar

from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.db.models.functions import TruncDate
from django.utils import formats, timezone

from .models import Booking
from .services import normalisasi_wa, rupiah

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


# ─────────────────────────────────────── DAFTAR PESANAN ───────────────────────
PER_HALAMAN = 8

# Kelompok status untuk halaman filter (None = semua)
STATUS_HALAMAN = {
    'admin_pesanan':   None,
    'admin_menunggu':  ('menunggu',),
    'admin_diproses':  ('dijemput', 'diproses'),
    'admin_selesai':   ('selesai',),
    'admin_dibatalkan':('dibatalkan',),
}


def _baris(b):
    kunci, label = kelompok_status(b.status)
    return {
        'pk': b.pk, 'resi': b.resi, 'nama': b.nama, 'whatsapp': b.whatsapp,
        'tanggal': timezone.localtime(b.dibuat), 'layanan': b.nama_layanan,
        'total': rupiah(b.total), 'penyerahan': b.penyerahan,
        'status_key': kunci, 'status_label': label,
    }


def _tanggal(teks):
    try:
        return date.fromisoformat((teks or '').strip())
    except ValueError:
        return None


def label_periode(dari, sampai):
    if not dari or not sampai:
        return 'Semua waktu'
    if dari == sampai:
        return formats.date_format(dari, 'j F Y')
    if (dari.year, dari.month) == (sampai.year, sampai.month):
        return f'{dari.day}–{formats.date_format(sampai, "j F Y")}'
    if dari.year == sampai.year:
        return f'{formats.date_format(dari, "j F")} – {formats.date_format(sampai, "j F Y")}'
    return f'{formats.date_format(dari, "j F Y")} – {formats.date_format(sampai, "j F Y")}'


def _kandidat_wa(q):
    digit = ''.join(c for c in q if c.isdigit())
    if len(digit) < 3:
        return set()
    kandidat = {digit}
    if digit.startswith('0'):   kandidat.add('62' + digit[1:])
    elif digit.startswith('62'): kandidat.add('0' + digit[2:])
    elif digit.startswith('8'): kandidat.update({'0'+digit, '62'+digit})
    norm = normalisasi_wa(q)
    if norm: kandidat.update({norm, '0'+norm[2:]})
    return kandidat


def _qs(**kw):
    return urlencode({k: v for k, v in kw.items() if v})


def daftar_pesanan(params, url_name='admin_pesanan', sekarang=None):
    """Data halaman daftar pesanan.

    url_name menentukan filter status: None = semua, ('menunggu',) = hanya menunggu, dst.
    Bawaan periode: bulan berjalan. Tanggal rusak diabaikan.
    """
    sekarang  = timezone.localtime(sekarang or timezone.now())
    hari_ini  = sekarang.date()
    bulan_ini = hari_ini.replace(day=1)
    zona      = timezone.get_current_timezone()
    filter_status = STATUS_HALAMAN.get(url_name)

    q           = (params.get('q') or '').strip()[:100]
    semua_waktu = params.get('periode') == 'semua'
    dari_in     = _tanggal(params.get('dari'))
    sampai_in   = _tanggal(params.get('sampai'))

    if semua_waktu:
        dari = sampai = None
    else:
        dari, sampai = dari_in or bulan_ini, sampai_in or hari_ini
        if dari > sampai:
            dari, sampai = sampai, dari
    periode_kustom = semua_waktu or bool(dari_in or sampai_in)

    qs = Booking.objects.all()
    if filter_status:
        qs = qs.filter(status__in=filter_status)
    if dari:
        qs = qs.filter(dibuat__gte=timezone.make_aware(datetime.combine(dari, time.min), zona))
    if sampai:
        qs = qs.filter(dibuat__lt=timezone.make_aware(datetime.combine(sampai + timedelta(days=1), time.min), zona))
    if q:
        cocok = Q(resi__icontains=q) | Q(nama__icontains=q)
        for nomor in _kandidat_wa(q): cocok |= Q(whatsapp__contains=nomor)
        qs = qs.filter(cocok)
    qs = qs.order_by('-dibuat', '-id')

    halaman   = Paginator(qs, PER_HALAMAN).get_page(params.get('hal'))
    paginator = halaman.paginator

    dasar = {'q': q}
    if semua_waktu:       dasar['periode'] = 'semua'
    elif periode_kustom:  dasar.update(dari=dari.isoformat(), sampai=sampai.isoformat())

    nomor = []
    for n in paginator.get_elided_page_range(halaman.number, on_each_side=2, on_ends=1):
        if n == Paginator.ELLIPSIS: nomor.append({'titik': True})
        else: nomor.append({'n': n, 'url': '?'+_qs(**dasar, hal=n if n>1 else ''), 'aktif': n==halaman.number})

    return {
        'q': q, 'dari': dari, 'sampai': sampai, 'semua_waktu': semua_waktu,
        'label_periode': label_periode(dari, sampai),
        'filter_aktif': bool(q) or periode_kustom,
        'periode_hidden': [(k,v) for k,v in dasar.items() if k!='q'],
        'qs_bulan_ini':   _qs(q=q),
        'qs_semua_waktu': _qs(q=q, periode='semua'),
        'baris':  [_baris(b) for b in halaman.object_list],
        'halaman': halaman,
        'jumlah':  rupiah(paginator.count),
        'mulai':   halaman.start_index() if paginator.count else 0,
        'akhir':   halaman.end_index()   if paginator.count else 0,
        'nomor':   nomor,
        'url_sebelumnya': '?'+_qs(**dasar, hal=halaman.number-1 if halaman.number>2 else '') if halaman.has_previous() else '',
        'url_berikutnya': '?'+_qs(**dasar, hal=halaman.number+1) if halaman.has_next() else '',
        'sekarang': sekarang,
        'masuk_hari_ini': rupiah(Booking.objects.filter(
            dibuat__gte=timezone.make_aware(datetime.combine(hari_ini, time.min), zona)).count()),
    }


# ─────────────────────────────────────── LAPORAN TERSIMPAN ───────────────────

NAMA_BULAN_ID = {
    1: 'Januari', 2: 'Februari', 3: 'Maret', 4: 'April',
    5: 'Mei', 6: 'Juni', 7: 'Juli', 8: 'Agustus',
    9: 'September', 10: 'Oktober', 11: 'November', 12: 'Desember',
}
NAMA_BULAN_SINGKAT = {
    1: 'Jan', 2: 'Feb', 3: 'Mar', 4: 'Apr',
    5: 'Mei', 6: 'Jun', 7: 'Jul', 8: 'Agt',
    9: 'Sep', 10: 'Okt', 11: 'Nov', 12: 'Des',
}


def _fmt_tanggal(dt):
    """datetime → '11 Okt 2026 · 14.00'"""
    return f"{dt.day} {NAMA_BULAN_SINGKAT[dt.month]} {dt.year} · {dt.hour:02d}.{dt.minute:02d}"


def _fmt_periode_bulan(tahun, bulan, hari_akhir=None):
    """Kembalikan string '1–31 Agustus 2026' (atau sampai hari_akhir bila bulan berjalan)."""
    hari_maks = hari_akhir or calendar.monthrange(tahun, bulan)[1]
    return f"1–{hari_maks} {NAMA_BULAN_ID[bulan]} {tahun}"


def _fmt_periode_minggu(dari, sampai):
    """date, date → '28 Sep – 4 Okt 2026'"""
    if dari.month == sampai.month:
        return f"{dari.day}–{sampai.day} {NAMA_BULAN_SINGKAT[sampai.month]} {sampai.year}"
    return (
        f"{dari.day} {NAMA_BULAN_SINGKAT[dari.month]} – "
        f"{sampai.day} {NAMA_BULAN_SINGKAT[sampai.month]} {sampai.year}"
    )


def laporan_tersimpan(sekarang=None):
    """Data untuk halaman Laporan Tersimpan.

    Mengembalikan:
      - stat: dict dengan jumlah laporan, periode_terbaru, total_pesanan_periode
      - daftar: list laporan (urut terbaru → terlama)
    """
    sekarang = timezone.localtime(sekarang or timezone.now())
    hari_ini = sekarang.date()
    zona = timezone.get_current_timezone()

    semua = Booking.objects.all()
    total_semua = semua.count()

    # ── Bangun daftar laporan berdasarkan data yang tersedia ──────────────────
    # Cari bulan-bulan yang punya data pesanan
    bulan_ada = (
        semua
        .order_by()
        .values_list('dibuat__year', 'dibuat__month')
        .distinct()
        .order_by('-dibuat__year', '-dibuat__month')
    )
    bulan_unik = list(dict.fromkeys((y, m) for y, m in bulan_ada))[:12]

    daftar = []
    for tahun, bulan in bulan_unik:
        bulan_awal = timezone.make_aware(datetime(tahun, bulan, 1, 0, 0, 0), zona)
        if bulan == 12:
            bulan_akhir = timezone.make_aware(datetime(tahun + 1, 1, 1, 0, 0, 0), zona)
        else:
            bulan_akhir = timezone.make_aware(datetime(tahun, bulan + 1, 1, 0, 0, 0), zona)

        n = semua.filter(dibuat__gte=bulan_awal, dibuat__lt=bulan_akhir).count()
        if not n:
            continue

        # Apakah ini bulan berjalan?
        is_berjalan = (tahun == hari_ini.year and bulan == hari_ini.month)

        if is_berjalan:
            hari_akhir = hari_ini.day
            # Laporan "Ringkasan operasional" bulan berjalan dibuat "hari ini pukul sekarang"
            dibuat_ringkasan = sekarang
        else:
            hari_akhir = calendar.monthrange(tahun, bulan)[1]
            # Laporan bulan lalu dibuat tanggal 1 bulan berikutnya pukul 08.00
            if bulan == 12:
                tgl_buat = datetime(tahun + 1, 1, 1, 8, 0)
            else:
                tgl_buat = datetime(tahun, bulan + 1, 1, 8, 0)
            dibuat_ringkasan = timezone.make_aware(tgl_buat, zona)

        nama_bln = NAMA_BULAN_ID[bulan]
        periode_str = _fmt_periode_bulan(tahun, bulan, hari_akhir if is_berjalan else None)

        # Laporan Ringkasan Operasional
        daftar.append({
            'nama': f'Ringkasan operasional {nama_bln}',
            'sub': f'{rupiah(n)} pesanan · Dokumen PDF',
            'periode': periode_str,
            'dibuat': _fmt_tanggal(timezone.localtime(dibuat_ringkasan)),
            'dibuat_sort': dibuat_ringkasan,
        })

        # Laporan Pendapatan (hanya bulan selesai)
        if not is_berjalan:
            # total pendapatan = sum berat × harga
            from .services import LAYANAN
            pesanan_bln = semua.filter(dibuat__gte=bulan_awal, dibuat__lt=bulan_akhir)
            total_rp = sum(
                int(b.berat * LAYANAN.get(b.layanan, {}).get('harga', 0))
                for b in pesanan_bln.only('berat', 'layanan')
            )
            dibuat_pendapatan = timezone.make_aware(
                datetime(tahun, bulan + 1 if bulan < 12 else 1,
                         1, 8, 0) if bulan < 12
                else datetime(tahun + 1, 1, 1, 8, 0), zona
            )
            daftar.append({
                'nama': f'Pendapatan {nama_bln}',
                'sub': f'Rp {rupiah(total_rp)} · Dokumen PDF',
                'periode': periode_str,
                'dibuat': _fmt_tanggal(timezone.localtime(dibuat_pendapatan)),
                'dibuat_sort': dibuat_pendapatan,
            })

        # Laporan Rekap Pesanan (hanya bulan selesai)
        if not is_berjalan:
            dibuat_rekap = timezone.make_aware(
                datetime(tahun, bulan + 1 if bulan < 12 else 1, 1, 8, 0) if bulan < 12
                else datetime(tahun + 1, 1, 1, 8, 0), zona
            )
            daftar.append({
                'nama': f'Rekap pesanan {nama_bln}',
                'sub': f'{rupiah(n)} pesanan · Dokumen PDF',
                'periode': periode_str,
                'dibuat': _fmt_tanggal(timezone.localtime(dibuat_rekap)),
                'dibuat_sort': dibuat_rekap,
            })

    # Laporan mingguan: minggu-minggu 4 bulan ke belakang
    minggu_sudah = set()
    for delta_hari in range(7, 5 * 7 + 1, 7):
        senin = hari_ini - timedelta(days=hari_ini.weekday()) - timedelta(weeks=delta_hari // 7 - 1)
        minggu_ke = senin.isocalendar()[1]
        if minggu_ke in minggu_sudah:
            continue
        minggu_sudah.add(minggu_ke)
        minggu_akhir = senin + timedelta(days=6)
        if minggu_akhir > hari_ini:
            minggu_akhir = hari_ini

        awal_mg = timezone.make_aware(datetime.combine(senin, time.min), zona)
        akhir_mg = timezone.make_aware(
            datetime.combine(minggu_akhir + timedelta(days=1), time.min), zona
        )
        n_mg = semua.filter(dibuat__gte=awal_mg, dibuat__lt=akhir_mg).count()
        if not n_mg:
            continue

        # Tanggal pembuatan laporan: hari Senin pekan berikutnya pukul 08.00
        buat_senin = senin + timedelta(weeks=1)
        dibuat_mg = timezone.make_aware(
            datetime(buat_senin.year, buat_senin.month, buat_senin.day, 8, 0), zona
        )
        daftar.append({
            'nama': f'Kinerja layanan mingguan',
            'sub': f'{rupiah(n_mg)} pesanan · Dokumen PDF',
            'periode': _fmt_periode_minggu(senin, minggu_akhir),
            'dibuat': _fmt_tanggal(timezone.localtime(dibuat_mg)),
            'dibuat_sort': dibuat_mg,
        })

    # Urutkan: terbaru di atas
    daftar.sort(key=lambda x: x['dibuat_sort'], reverse=True)
    # Buang key internal
    for d in daftar:
        del d['dibuat_sort']

    # ── Stat cards ────────────────────────────────────────────────────────────
    # Bulan terbaru yang ada data
    if bulan_unik:
        thn_terbaru, bln_terbaru = bulan_unik[0]
        is_berjalan_terbaru = (
            thn_terbaru == hari_ini.year and bln_terbaru == hari_ini.month
        )
        hari_akhir_terbaru = hari_ini.day if is_berjalan_terbaru else calendar.monthrange(thn_terbaru, bln_terbaru)[1]

        periode_terbaru = _fmt_periode_bulan(
            thn_terbaru, bln_terbaru,
            hari_akhir_terbaru if is_berjalan_terbaru else None,
        )
        bulan_label_terbaru = NAMA_BULAN_ID[bln_terbaru]

        bulan_awal_t = timezone.make_aware(datetime(thn_terbaru, bln_terbaru, 1, 0, 0, 0), zona)
        if bln_terbaru == 12:
            bulan_akhir_t = timezone.make_aware(datetime(thn_terbaru + 1, 1, 1, 0, 0, 0), zona)
        else:
            bulan_akhir_t = timezone.make_aware(datetime(thn_terbaru, bln_terbaru + 1, 1, 0, 0, 0), zona)

        total_periode = semua.filter(dibuat__gte=bulan_awal_t, dibuat__lt=bulan_akhir_t).count()

        if is_berjalan_terbaru:
            dibuat_label = f'Dibuat hari ini pukul {sekarang.hour:02d}.{sekarang.minute:02d}'
        else:
            dibuat_label = f'Dibuat 1 {NAMA_BULAN_ID[bln_terbaru + 1 if bln_terbaru < 12 else 1]} {thn_terbaru if bln_terbaru < 12 else thn_terbaru + 1} pukul 08.00'
    else:
        thn_terbaru, bln_terbaru = hari_ini.year, hari_ini.month
        periode_terbaru = '-'
        bulan_label_terbaru = '-'
        total_periode = 0
        dibuat_label = '-'

    return {
        'sekarang': sekarang,
        'stat': {
            'jumlah_laporan': len(daftar),
            'periode_terbaru': periode_terbaru,
            'bulan_label': bulan_label_terbaru,
            'total_periode': rupiah(total_periode),
            'dibuat_label': dibuat_label,
        },
        'daftar': daftar,
        'ada_laporan': bool(daftar),
        'footer_jumlah': rupiah(len(daftar)),
    }
