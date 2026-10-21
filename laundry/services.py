SERVICES = [
    {'key': 'reguler', 'jam': 48, 'nama': 'Cuci Reguler', 'harga': 7000, 'satuan': 'pcs', 'badge': '',
     'desc': 'Cuci basah, pengeringan, lipat rapi, dan pewangi premium untuk pakaian sehari-hari.',
     'estimasi': 'Selesai dalam 2 hari', 'img': 'layanan-reguler.jpg'},
    {'key': 'express', 'jam': 6, 'nama': 'Cuci Express', 'harga': 12000, 'satuan': 'pcs', 'badge': 'TERPOPULER',
     'desc': 'Layanan kilat super cepat untuk kebutuhan mendadak Anda. Pakaian bersih wangi hari ini juga!',
     'estimasi': 'Selesai dalam 6 jam', 'img': None},
    {'key': 'dry', 'jam': 72, 'nama': 'Dry Cleaning', 'harga': 25000, 'satuan': 'pcs', 'badge': '',
     'desc': 'Perawatan khusus jas, kebaya, gaun, atau bahan sensitif lainnya dengan teknik profesional.',
     'estimasi': 'Selesai dalam 3 hari', 'img': None},
    {'key': 'setrika', 'jam': 24, 'nama': 'Setrika Saja', 'harga': 5000, 'satuan': 'pcs', 'badge': '',
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


# Katalog hadiah (sesuai desain "Poin & hadiah"). Urutkan dari poin terkecil.
HADIAH = [
    {'key': 'voucher-5000', 'nama': 'Voucher Rp 5.000', 'poin': 500, 'warna': 'biru',
     'syarat': 'Potongan Rp 5.000 untuk pesananmu berikutnya.'},
    {'key': 'voucher-10000', 'nama': 'Voucher Rp 10.000', 'poin': 1000, 'warna': 'lime',
     'syarat': 'Potongan Rp 10.000 untuk pesananmu berikutnya.'},
    {'key': 'gopay-10000', 'nama': 'Saldo GoPay Rp 10.000', 'poin': 1000, 'warna': 'biru',
     'syarat': 'Saldo dikirim ke GoPay dengan nomor yang sama dengan WhatsApp-mu.'},
    {'key': 'dana-10000', 'nama': 'Saldo DANA Rp 10.000', 'poin': 1000, 'warna': 'lime',
     'syarat': 'Saldo dikirim ke DANA dengan nomor yang sama dengan WhatsApp-mu.'},
    {'key': 'gratis-setrika', 'nama': '1x Gratis Setrika', 'poin': 1200, 'warna': 'biru',
     'syarat': 'Layanan Setrika Saja gratis, maksimal 10 pcs.'},
    {'key': 'gratis-cuci', 'nama': '1x Gratis Cuci Reguler', 'poin': 1500, 'warna': 'lime',
     'syarat': 'Layanan Cuci Reguler gratis, maksimal 10 pcs.'},
]
