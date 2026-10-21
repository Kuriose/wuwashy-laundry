from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .forms import EMAIL_SUDAH_ADA, BookingForm, EmailLoginForm, SignUpForm
from . import panel
from .pesanan import konteks_pesanan_saya
from .models import Booking, PoinLog, Profile
from .poin import konteks_poin_hadiah, pesanan_aktif, saldo_poin, tautkan_booking
from .poin import tukar_hadiah as proses_tukar
from .services import SERVICES, rupiah

KEUNGGULAN = [
    ('fitur-harga.jpg', 'Harga Transparan', 'Setiap hitungan pakaian disaksikan bersama dan tercatat detail di database sistem online.'),
    (None, 'Garansi Bersih', 'Kurang puas dengan cucian kami? Kami cuci ulang gratis tanpa biaya tambahan.'),
    ('fitur-poin.jpg', 'Poin Royalti', 'Setiap cuci dapat poin! Kumpulkan transaksinya, tukarkan diskon spesial, dan nikmati keuntungan eksklusif.'),
    ('fitur-wangi.jpg', 'Pewangi Premium', 'Parfum khusus berlisensi aman yang tercium harum segar hingga 14 hari pengerjaan.'),
    (None, 'Real-Time Tracking', 'Pantau pergerakan antaran cucian secara langsung di peta secara real-time hingga sampai di depan pintu.'),
    (None, 'Gratis Penjemputan', 'Tanpa minimum pesanan untuk radius 3km dari outlet terdekat kami.'),
]

TESTIMONI = [
    ('Kenzo West', 'Rapper', 'avatar-1.jpg', 'Wuwashy beneran ngebantu banget! Tinggal booking dari HP, baju kotor dijemput, baliknya udah wangi banget, rapi tinggal masuk lemari. Express-nya juara!'),
    ('Vito Corleone', 'Karyawan Swasta', 'avatar-2.jpg', 'Suka banget sama sistem poin setianya. Sambil nyuci tiap minggu dapet poin, tau-tau dapet jatah cuci gratis. Pewangi lavendernya enak sekali dan tahan lama.'),
    ('Jill Valentine', 'Mahasiswi', 'avatar-3.jpg', 'Harganya bersahabat buat kantong mahasiswa, trus ada pelacakan map real-time jadi gak tegang nungguin baju buat dipakai sidang besok.'),
]


def home(request):
    """Landing page satu halaman: Home, About, Services, dan Outlet Kami."""
    layanan = [{**s, 'harga_fmt': rupiah(s['harga'])} for s in SERVICES]
    return render(request, 'laundry/home.html', {
        'testimoni': TESTIMONI,
        'layanan': layanan,
        'keunggulan': KEUNGGULAN,
    })


def _ke_bagian(anchor):
    return redirect(f"{reverse('home')}#{anchor}")


# URL lama tetap hidup (bookmark / link lama) dan diarahkan ke bagian di landing page.
def about(request):
    return _ke_bagian('about')


def services(request):
    return _ke_bagian('services')


def _simpan_booking_dan_buka_wa(request, form):
    """Simpan pesanan (tertaut ke akun bila login) lalu arahkan ke WhatsApp admin."""
    b = form.save(commit=False)
    tautkan_booking(b, request.user)
    b.save()
    pesan = (
        'Halo WuWashy Laundry! Saya ingin booking jemput cucian.\n\n'
        f'No. Resi: {b.resi}\n'
        f'Nama: {b.nama}\n'
        f'WhatsApp: {b.whatsapp}\n'
        f'Layanan: {b.get_layanan_display()}\n'
        f'Jumlah pakaian: {int(b.berat)} pcs\n'
        f'Alamat: {b.alamat}\n'
        f'Catatan: {b.catatan or "-"}'
    )
    return redirect(f'https://wa.me/{settings.WHATSAPP_ADMIN}?text={quote(pesan)}')


def _form_booking_awal(request):
    awal = {}
    if request.GET.get('layanan'):
        awal['layanan'] = request.GET['layanan']
    if request.user.is_authenticated:  # pelanggan login: data dirinya terisi otomatis
        awal['nama'] = request.user.get_full_name().strip()
        awal['whatsapp'] = Profile.untuk(request.user).whatsapp
    return BookingForm(initial=awal or None)


def booking(request):
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            return _simpan_booking_dan_buka_wa(request, form)
    else:
        form = _form_booking_awal(request)
    return render(request, 'laundry/booking.html', {'form': form})


class LoginView(auth_views.LoginView):
    template_name = 'laundry/login.html'
    authentication_form = EmailLoginForm
    redirect_authenticated_user = True

    def form_valid(self, form):
        response = super().form_valid(form)
        if not form.cleaned_data.get('remember_me'):
            # sesi berakhir saat browser ditutup
            self.request.session.set_expiry(0)
        return response


def signup(request):
    """Daftar akun pelanggan baru, lalu langsung masuk ke dashboard."""
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignUpForm(request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and form.is_valid():
        try:
            with transaction.atomic():
                user = form.save()
        except IntegrityError:
            # dua pendaftaran dengan email sama pada saat bersamaan
            form.add_error('email', EMAIL_SUDAH_ADA)
        else:
            login(request, user, backend='laundry.backends.EmailBackend')
            return redirect('dashboard')
    return render(request, 'laundry/signup.html', {'form': form})


# Target poin untuk voucher (sesuai desain dashboard).
POIN_TARGET = 1000


def _konteks_dasar(user, role):
    nama = user.get_full_name().strip() or user.email.split('@')[0] or user.get_username()
    nama_depan = user.first_name.strip() or nama.split(' ')[0]
    return {
        'peran': role,
        'pesanan_aktif': pesanan_aktif(user).count() if role != Profile.Role.ADMIN else 0,  # lencana sidebar
        'nama': nama,
        'nama_depan': nama_depan,
        'inisial': ''.join(kata[0] for kata in nama.split()[:2]).upper(),
    }


@login_required
def dashboard(request):
    """Pintu masuk setelah login: USER melihat dashboard pelanggan, ADMIN diarahkan ke panel admin."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')

    poin = saldo_poin(request.user.pk)
    return render(request, 'laundry/dashboard.html', {
        **_konteks_dasar(request.user, role),
        'layanan': [{**s, 'harga_fmt': rupiah(s['harga'])} for s in SERVICES],
        'poin': poin,
        'poin_target': rupiah(POIN_TARGET),
        'poin_persen': min(100, poin * 100 // POIN_TARGET),
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def pesanan_saya(request):
    """Pesanan aktif milik pelanggan: tahap pengerjaan, estimasi selesai, alamat, dan calon poin."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    return render(request, 'laundry/pesanan_saya.html', {
        **_konteks_dasar(request.user, role),
        **konteks_pesanan_saya(request.user, request.GET.get('tab', '')),
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def poin_hadiah(request):
    """Saldo poin, progres menuju voucher, katalog hadiah, dan riwayat poin pelanggan."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    return render(request, 'laundry/poin_hadiah.html', {
        **_konteks_dasar(request.user, role),
        **konteks_poin_hadiah(request.user, request.GET.get('tab', '')),
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def pesan_laundry(request):
    """Form pesan laundry di dalam dashboard pelanggan, jadi tidak perlu pindah ke halaman website."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            return _simpan_booking_dan_buka_wa(request, form)
    else:
        form = _form_booking_awal(request)
    return render(request, 'laundry/pesan.html', {
        **_konteks_dasar(request.user, role), 'form': form, 'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
@require_POST
def tukar_hadiah(request, key):
    """Tukar poin dengan hadiah; admin menindaklanjuti lewat WhatsApp."""
    if Profile.untuk(request.user).role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    hadiah, galat = proses_tukar(request.user, key)
    if galat:
        messages.error(request, galat)
    else:
        messages.success(request, f"Berhasil menukar {hadiah['nama']}. Admin akan menghubungimu lewat WhatsApp untuk mengirim hadiahnya.")
    return redirect('poin_hadiah')


@login_required
def notifikasi(request):
    """Daftar notifikasi pelanggan (sementara masih kosong)."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    return render(request, 'laundry/notifikasi.html', {
        **_konteks_dasar(request.user, role), 'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def pengaturan(request):
    """Ringkasan akun pelanggan (sementara hanya baca)."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    return render(request, 'laundry/pengaturan.html', {
        **_konteks_dasar(request.user, role),
        'email': request.user.email,
        'whatsapp': Profile.untuk(request.user).whatsapp,
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@admin_required
def admin_dashboard(request):
    """Dasbor admin: ringkasan pesanan bulan berjalan (data dari model Booking)."""
    konteks = _konteks_dasar(request.user, Profile.Role.ADMIN)
    return render(request, 'laundry/admin_dashboard.html', {
        **konteks,
        **panel.ringkasan(),
        'email': request.user.email,
        'outlet_nama': settings.OUTLET_NAMA,
        'outlet_kota': settings.OUTLET_KOTA,
    })


def _konteks_panel(request):
    """Data yang dibutuhkan kerangka panel admin (sidebar, nama outlet, akun)."""
    return {
        **_konteks_dasar(request.user, Profile.Role.ADMIN),
        'sidebar': panel.hitung_sidebar(),
        'email': request.user.email,
        'outlet_nama': settings.OUTLET_NAMA,
        'outlet_kota': settings.OUTLET_KOTA,
    }


@admin_required
def admin_pesanan_detail(request, pk):
    """Detail satu pesanan + form ubah status. Memakai .save() agar signal pemberi poin ikut jalan."""
    b = get_object_or_404(Booking.objects.select_related('user'), pk=pk)

    if request.method == 'POST':
        baru = request.POST.get('status', '')
        if baru not in dict(Booking.STATUS):
            messages.error(request, 'Status tidak dikenal. Pilih salah satu dari daftar.')
        elif baru == b.status:
            messages.info(request, 'Status tidak berubah.')
        else:
            sudah_dapat_poin = PoinLog.objects.filter(booking=b, jumlah__gt=0).exists()
            b.status = baru
            b.save()
            pesan = f'Status pesanan {b.resi} diubah menjadi {b.get_status_display()}.'
            if baru == 'selesai':
                log = PoinLog.objects.filter(booking=b, jumlah__gt=0).first()
                if log and not sudah_dapat_poin:
                    pesan += f' +{log.jumlah} poin masuk ke {b.user.email} (saldo {log.saldo}).'
                elif log:
                    pesan += ' Poin pesanan ini sudah pernah diberikan, tidak ditambah lagi.'
                elif b.user_id:
                    pesan += ' Total pesanan terlalu kecil untuk mendapat poin.'
                else:
                    pesan += ' Pesanan tamu tanpa akun, tidak ada poin yang diberikan.'
            messages.success(request, pesan)
        return redirect('admin_pesanan_detail', pk=b.pk)

    log_poin = PoinLog.objects.filter(booking=b, jumlah__gt=0).first()
    return render(request, 'laundry/admin_pesanan_detail.html', {
        **_konteks_panel(request),
        'b': b,
        'status_kunci': panel.kelompok_status(b.status)[0],
        'pilihan_status': Booking.STATUS,
        'log_poin': log_poin,
        'saldo_pelanggan': saldo_poin(b.user_id) if b.user_id else None,
    })
