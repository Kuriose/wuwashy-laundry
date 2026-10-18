from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from laundry.models import Profile

# Akun uji untuk pengembangan. JANGAN dipakai di server produksi.
AKUN_UJI = [
    {'email': 'nadia@example.com', 'first_name': 'Nadia', 'last_name': 'Aulia',
     'password': 'wuwashy-user-123', 'role': Profile.Role.USER, 'whatsapp': '081234567890'},
    {'email': 'admin@example.com', 'first_name': 'Admin', 'last_name': 'WuWashy',
     'password': 'wuwashy-admin-123', 'role': Profile.Role.ADMIN},
]


class Command(BaseCommand):
    help = 'Membuat akun uji: satu USER (pelanggan) dan satu ADMIN. Aman dijalankan berulang kali.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset-password', action='store_true',
            help='Kembalikan password akun uji yang sudah ada ke nilai bawaan.',
        )

    def handle(self, *args, **options):
        User = get_user_model()
        for akun in AKUN_UJI:
            user, dibuat = User.objects.get_or_create(
                username=akun['email'],
                defaults={'email': akun['email'], 'first_name': akun['first_name'], 'last_name': akun['last_name']},
            )
            if dibuat or options['reset_password']:
                user.set_password(akun['password'])
                user.save()
            profile = Profile.untuk(user)
            if profile.role != akun['role'] or (akun.get('whatsapp') and not profile.whatsapp):
                profile.role = akun['role']
                profile.whatsapp = profile.whatsapp or akun.get('whatsapp', '')
                profile.save()
            if dibuat or options['reset_password']:
                info = f"password: {akun['password']}  ({'dibuat' if dibuat else 'password direset'})"
            else:
                info = 'sudah ada, password tidak diubah'
            self.stdout.write(f"[{akun['role']:<5}] {akun['email']:<20} {info}")
        self.stdout.write(self.style.SUCCESS('Selesai. Login memakai email + password di atas.'))
