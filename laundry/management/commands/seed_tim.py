from django.core.management.base import BaseCommand

from laundry.models import AnggotaTim

# Data contoh sesuai desain "Anggota Tim". Hanya untuk pengembangan.
ANGGOTA = [
    ('Ayu Pratiwi', 'ayu@wuwashy.id', '0812-1100-1001', 'kasir'),
    ('Nadia Safitri', 'nadia@wuwashy.id', '0812-1100-1002', 'kasir'),
    ('Budi Santoso', 'budi@wuwashy.id', '0812-1100-1003', 'kasir'),
    ('Fajar Hidayat', 'fajar@wuwashy.id', '0812-1100-2001', 'kurir'),
    ('Rizky Pratama', 'rizky@wuwashy.id', '0812-1100-2002', 'kurir'),
    ('Andi Saputra', 'andi@wuwashy.id', '0812-1100-2003', 'kurir'),
]


class Command(BaseCommand):
    help = 'Membuat 6 anggota tim contoh (3 kasir, 3 kurir). Aman dijalankan berulang kali.'

    def handle(self, *args, **options):
        dibuat = 0
        for nama, email, telepon, peran in ANGGOTA:
            _, baru = AnggotaTim.objects.get_or_create(
                email=email, defaults={'nama': nama, 'telepon': telepon, 'peran': peran},
            )
            dibuat += baru
        self.stdout.write(self.style.SUCCESS(f'{dibuat} anggota baru dibuat, {len(ANGGOTA) - dibuat} sudah ada.'))
