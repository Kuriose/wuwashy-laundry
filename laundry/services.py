SERVICES = [
    {'key': 'reguler', 'jam': 48, 'nama': 'Cuci Reguler', 'harga': 7000, 'satuan': 'kg', 'badge': '',
     'desc': 'Cuci basah, pengeringan, lipat rapi, dan pewangi premium untuk pakaian sehari-hari.',
     'estimasi': 'Selesai dalam 2 hari', 'img': 'layanan-reguler.jpg'},
    {'key': 'express', 'jam': 6, 'nama': 'Cuci Express', 'harga': 12000, 'satuan': 'kg', 'badge': 'TERPOPULER',
     'desc': 'Layanan kilat super cepat untuk kebutuhan mendadak Anda. Pakaian bersih wangi hari ini juga!',
     'estimasi': 'Selesai dalam 6 jam', 'img': 'layanan-express.jpg'},
    {'key': 'dry', 'jam': 72, 'nama': 'Dry Cleaning', 'harga': 25000, 'satuan': 'pcs', 'badge': '',
     'desc': 'Perawatan khusus jas, kebaya, gaun, atau bahan sensitif lainnya dengan teknik profesional.',
     'estimasi': 'Selesai dalam 3 hari', 'img': 'layanan-dry.jpg'},
    {'key': 'setrika', 'jam': 24, 'nama': 'Setrika Saja', 'harga': 5000, 'satuan': 'kg', 'badge': '',
     'desc': 'Pakaian kusut Anda akan langsung licin rapi dengan setrika uap modern kami.',
     'estimasi': 'Selesai dalam 1 hari', 'img': 'layanan-setrika.jpg'},
]


LAYANAN = {s['key']: s for s in SERVICES}


def rupiah(n):
    return f'{n:,}'.replace(',', '.')


CHOICES = [(s['key'], f"{s['nama']} (Rp {rupiah(s['harga'])}/{s['satuan']})") for s in SERVICES]


# Setiap kelipatan Rp1.000 dari total pesanan yang selesai = 1 poin (sesuai desain "Poin & hadiah").
RUPIAH_PER_POIN = 1000


def hitung_poin(total):
    return int(total) // RUPIAH_PER_POIN


def normalisasi_wa(nomor):
    """'0812-3456-7890', '+62 812 3456 7890', '62812...' -> '6281234567890' (digit saja, awalan 62).

    Mengembalikan '' bila bukan nomor yang masuk akal, supaya tidak pernah dipakai untuk mencocokkan akun.
    """
    digit = ''.join(c for c in str(nomor or '') if c.isdigit())
    if digit.startswith('0'):
        digit = '62' + digit[1:]
    elif digit.startswith('8'):
        digit = '62' + digit
    return digit if digit.startswith('62') and 10 <= len(digit) <= 16 else ''


def wa_lokal(nomor):
    """Nomor tersimpan -> tampilan lokal: 6281234567890 -> 0812 3456 7890."""
    n = str(nomor or '')
    if n.startswith('62'):
        n = '0' + n[2:]
    return ' '.join(bagian for bagian in (n[:4], n[4:8], n[8:]) if bagian)


# Wilayah untuk form alamat (kota -> daftar kecamatan). Tambah kota baru cukup dengan menambah baris di sini.
PROVINSI = 'Kalimantan Timur'
WILAYAH = {
    'Samarinda': ['Loa Janan Ilir', 'Palaran', 'Samarinda Ilir', 'Samarinda Kota', 'Samarinda Seberang',
                  'Samarinda Ulu', 'Samarinda Utara', 'Sambutan', 'Sungai Kunjang', 'Sungai Pinang'],
    'Balikpapan': ['Balikpapan Barat', 'Balikpapan Kota', 'Balikpapan Selatan', 'Balikpapan Tengah',
                   'Balikpapan Timur', 'Balikpapan Utara'],
    'Bontang': ['Bontang Barat', 'Bontang Selatan', 'Bontang Utara'],
}
MAKS_ALAMAT = 10  # batas alamat tersimpan per akun


# Katalog hadiah (sesuai desain "Poin & hadiah"). Urutkan dari poin terkecil.
HADIAH = [
    {'key': 'voucher-5000', 'nama': 'Voucher Rp 5.000', 'poin': 500, 'warna': 'biru'},
    {'key': 'voucher-10000', 'nama': 'Voucher Rp 10.000', 'poin': 1000, 'warna': 'lime'},
]
