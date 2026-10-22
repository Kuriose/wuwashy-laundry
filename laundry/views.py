from urllib.parse import quote

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, views as auth_views
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .decorators import admin_required
from .forms import (EMAIL_SUDAH_ADA, AlamatForm, AnggotaTimForm, BookingForm, EmailLoginForm,
                    NotifikasiForm, ProfilAkunForm, SignUpForm, TagihanForm, UbahKataSandiForm)
from . import panel, tim
from .pesanan import konteks_lacak_beranda, konteks_pesanan_saya
from .kotak_notifikasi import KotakNotifikasi
from .models import Alamat, AnggotaTim, Booking, Notifikasi, PoinLog, Profile, TagihanTerkunci
from .poin import konteks_poin_hadiah, pesanan_aktif, saldo_poin, tautkan_booking
from .riwayat import RiwayatPesanan
from .services import MAKS_ALAMAT, PROVINSI, SERVICES, WILAYAH, rupiah

KEUNGGULAN = [
    ('fitur-harga.jpg', 'Harga Transparan', 'Setiap timbangan disaksikan bersama dan tercatat detail di database sistem online.'),
    ('fitur-garansi.jpg', 'Garansi Bersih', 'Kurang puas dengan cucian kami? Kami cuci ulang gratis tanpa biaya tambahan.'),
    ('fitur-poin.jpg', 'Poin Royalti', 'Setiap cuci dapat poin! Kumpulkan transaksinya, tukarkan diskon spesial, dan nikmati keuntungan eksklusif.'),
    ('fitur-wangi.jpg', 'Pewangi Premium', 'Parfum khusus berlisensi aman yang tercium harum segar hingga 14 hari pengerjaan.'),
    ('fitur-tracking.jpg', 'Real-Time Tracking', 'Pantau pergerakan antaran cucian secara langsung di peta secara real-time hingga sampai di depan pintu.'),
    ('fitur-antar.jpg', 'Gratis Penjemputan', 'Tanpa minimum pesanan untuk radius 3km dari outlet terdekat kami.'),
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


def booking(request):
    if request.method == 'POST':
        form = BookingForm(request.POST)
        if form.is_valid():
            b = form.save(commit=False)
            tautkan_booking(b, request.user)
            b.save()
            pesan = (
                'Halo WuWashy Laundry! Saya ingin booking jemput cucian.\n\n'
                f'No. Resi: {b.resi}\n'
                f'Nama: {b.nama}\n'
                f'WhatsApp: {b.whatsapp}\n'
                f'Layanan: {b.get_layanan_display()}\n'
                f'Estimasi berat: {b.berat} kg\n'
                f'Alamat: {b.alamat}\n'
                f'Catatan: {b.catatan or "-"}'
            )
            return redirect(f'https://wa.me/{settings.WHATSAPP_ADMIN}?text={quote(pesan)}')
    else:
        awal = {}
        if request.GET.get('layanan'):
            awal['layanan'] = request.GET['layanan']
        if request.user.is_authenticated:  # pelanggan login: data dirinya terisi otomatis
            awal['nama'] = request.user.get_full_name().strip()
            profil = Profile.untuk(request.user)
            awal['whatsapp'] = profil.whatsapp
            utama = Alamat.utama_untuk(request.user)  # alamat utama dari halaman Alamat saya
            if utama:
                awal['alamat'] = utama.baris_alamat
        form = BookingForm(initial=awal or None)
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
        'notif_belum': Notifikasi.jumlah_belum_dibaca(user) if role != Profile.Role.ADMIN else 0,  # titik di lonceng
        'nama': nama,
        'nama_depan': nama_depan,
        'inisial': ''.join(kata[0] for kata in nama.split()[:2]).upper(),
        'profil': Profile.untuk(user),
        'alamat_utama': Alamat.utama_untuk(user),  # dipakai kartu alamat di beberapa halaman
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
        **konteks_lacak_beranda(request.user),  # kartu "Lacak cucianmu": pesanan aktif + bar progres
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


def _konteks_detail(request, b, tagihan_form):
    """Konteks halaman detail pesanan admin (dipakai saat tampil biasa dan saat form tagihan salah isi)."""
    log_poin = PoinLog.objects.filter(booking=b, jumlah__gt=0).first()
    return {
        **_konteks_panel(request),
        'b': b,
        'status_kunci': panel.kelompok_status(b.status)[0],
        'pilihan_status': Booking.STATUS,
        'log_poin': log_poin,
        'saldo_pelanggan': saldo_poin(b.user_id) if b.user_id else None,
        'tagihan_form': tagihan_form,
        'tagihan_terkunci': b.tagihan_terkunci,
    }


def _form_tagihan_awal(b):
    return TagihanForm(initial={
        'berat_final': b.berat_efektif,
        'koreksi_harga': b.koreksi_harga,
        'catatan_koreksi': b.catatan_koreksi,
    })


@admin_required
def admin_pesanan(request):
    """Daftar seluruh pesanan: pencarian, filter periode, dan pembagian halaman."""
    return render(request, 'laundry/admin_pesanan.html', {
        **_konteks_panel(request),
        **panel.daftar_pesanan(request.GET, 'admin_pesanan'),
        'judul': 'Semua Pesanan', 'subjudul': 'Kelola seluruh pesanan laundry dalam satu tempat.',
    })


@admin_required
def admin_menunggu(request):
    return render(request, 'laundry/admin_pesanan.html', {
        **_konteks_panel(request),
        **panel.daftar_pesanan(request.GET, 'admin_menunggu'),
        'judul': 'Menunggu',
        'subjudul': 'Pantau pesanan dengan status Menunggu.',
        'hint': 'Penyerahan dicatat saat laundry diterima pelanggan.',
    })


@admin_required
def admin_diproses(request):
    return render(request, 'laundry/admin_pesanan.html', {
        **_konteks_panel(request),
        **panel.daftar_pesanan(request.GET, 'admin_diproses'),
        'judul': 'Diproses',
        'subjudul': 'Pantau pesanan yang sedang dalam proses pencucian.',
    })


@admin_required
def admin_selesai(request):
    return render(request, 'laundry/admin_pesanan.html', {
        **_konteks_panel(request),
        **panel.daftar_pesanan(request.GET, 'admin_selesai'),
        'judul': 'Selesai',
        'subjudul': 'Daftar pesanan yang telah selesai dikerjakan.',
    })


@admin_required
def admin_dibatalkan(request):
    return render(request, 'laundry/admin_pesanan.html', {
        **_konteks_panel(request),
        **panel.daftar_pesanan(request.GET, 'admin_dibatalkan'),
        'judul': 'Dibatalkan',
        'subjudul': 'Daftar pesanan yang dibatalkan.',
    })


@admin_required
def admin_pesanan_detail(request, pk):
    """Detail satu pesanan + form ubah status + form tagihan (berat timbang & koreksi harga).

    Keduanya memakai .save() lewat model agar signal pemberi poin dan notifikasi ikut jalan.
    """
    b = get_object_or_404(Booking.objects.select_related('user'), pk=pk)

    if request.method == 'POST' and request.POST.get('aksi') == 'tagihan':
        form = TagihanForm(request.POST)
        if form.is_valid():
            sudah_dapat_poin = PoinLog.objects.filter(booking=b, jumlah__gt=0).exists()
            try:
                b.terapkan_tagihan(form.cleaned_data['berat_final'], form.cleaned_data['koreksi_harga'],
                                   form.cleaned_data['catatan_koreksi'].strip())
            except TagihanTerkunci as e:
                messages.error(request, str(e))
            else:
                pesan = f'Tagihan {b.resi} diperbarui: Rp {b.total_fmt}.'
                log = PoinLog.objects.filter(booking=b, jumlah__gt=0).first()
                if log and not sudah_dapat_poin:
                    pesan += f' +{log.jumlah} poin masuk ke {b.user.email}.'
                messages.success(request, pesan)
            return redirect('admin_pesanan_detail', pk=b.pk)
        return render(request, 'laundry/admin_pesanan_detail.html', _konteks_detail(request, b, form))

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

    return render(request, 'laundry/admin_pesanan_detail.html', _konteks_detail(request, b, _form_tagihan_awal(b)))


@admin_required
def admin_laporan(request):
    """Halaman Laporan Tersimpan."""
    return render(request, 'laundry/admin_laporan.html', {
        **_konteks_panel(request),
        **panel.laporan_tersimpan(),
    })


def _halaman_anggota(request, anggota=None):
    """Daftar anggota + form. Mode tambah bila `anggota` kosong, mode edit bila diisi."""
    edit_pk = anggota.pk if anggota else None
    edit_nama = anggota.nama if anggota else ''  # nama asli, sebelum form mengubah instance di memori
    awal = {f: getattr(anggota, f) for f in AnggotaTimForm.Meta.fields} if anggota else {}

    if request.method == 'POST':
        form = AnggotaTimForm(request.POST, instance=anggota)
        if form.is_valid():
            if anggota is None:
                baru = form.save()
                messages.success(request, f'{baru.nama} berhasil ditambahkan sebagai {baru.get_peran_display()}.')
            elif any(form.cleaned_data[f] != nilai for f, nilai in awal.items()):
                messages.success(request, f'Data {form.save().nama} berhasil diperbarui.')
            else:
                messages.info(request, f'Tidak ada perubahan pada data {edit_nama}.')
            return redirect('admin_anggota')
    else:
        form = AnggotaTimForm(instance=anggota)

    return render(request, 'laundry/admin_anggota.html', {
        **_konteks_panel(request),
        **tim.ringkasan_tim(),
        'form': form,
        'edit_pk': edit_pk, 'edit_nama': edit_nama,
        # form tampil bila diminta lewat "Tambah Anggota" / "Edit", atau bila ada galat validasi
        'form_terbuka': request.method == 'POST' or request.GET.get('tambah') == '1' or edit_pk is not None,
    })


@admin_required
def admin_anggota(request):
    """Anggota tim outlet (kasir & kurir): daftar + form tambah anggota."""
    return _halaman_anggota(request)


@admin_required
def admin_anggota_edit(request, pk):
    """Edit data anggota tim (nama, email, telepon, peran) memakai form yang sama dengan tambah anggota."""
    return _halaman_anggota(request, get_object_or_404(AnggotaTim, pk=pk))


@login_required
def akun_saya(request):
    """Halaman "Akun saya": lihat dan ubah data pribadi, kontak, dan alamat antar-jemput."""
    profil = Profile.untuk(request.user)
    if profil.is_admin:
        return redirect('admin_dashboard')

    form = ProfilAkunForm(request.POST if request.method == 'POST' else None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.simpan()
        messages.success(request, 'Perubahan tersimpan.')
        return redirect('akun_saya')

    poin = saldo_poin(request.user.pk)
    return render(request, 'laundry/akun_saya.html', {
        **_konteks_dasar(request.user, profil.role),
        'form': form,
        'poin': poin,
        'poin_persen': min(100, poin * 100 // POIN_TARGET),
        'poin_sisa': max(0, POIN_TARGET - poin),
        'poin_target': rupiah(POIN_TARGET),
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def cari_pesanan(request):
    """Pencarian nomor pesanan di header dashboard (hanya pesanan milik akun yang login, semua status)."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    q = request.GET.get('q', '').strip().lstrip('#').strip()
    hasil = []
    if q:
        hasil = list(Booking.objects.filter(user=request.user, resi__icontains=q).order_by('-dibuat', '-id')[:20])
    return render(request, 'laundry/cari_pesanan.html', {
        **_konteks_dasar(request.user, role),
        'q': q,
        'hasil': hasil,
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


def _ambil_alamat(queryset, mentah):
    """Alamat milik akun dengan id `mentah` (teks dari form/URL); None bila kosong, bukan angka, atau bukan miliknya."""
    try:
        return queryset.filter(pk=int(mentah)).first()
    except (TypeError, ValueError):
        return None


@login_required
def alamat_saya(request):
    """Halaman "Alamat saya": daftar alamat tersimpan + form tambah/ubah. Hanya menyentuh alamat milik akun sendiri."""
    profil = Profile.untuk(request.user)
    if profil.is_admin:
        return redirect('admin_dashboard')
    milik = Alamat.objects.filter(user=request.user)

    if request.method == 'POST':
        aksi = request.POST.get('aksi', 'simpan')
        id_mentah = request.POST.get('alamat_id', '')
        alamat = _ambil_alamat(milik, id_mentah)

        if aksi in ('utama', 'hapus') or id_mentah:
            if alamat is None:
                messages.error(request, 'Alamat tidak ditemukan.')
                return redirect('alamat_saya')
            if aksi == 'utama':
                alamat.jadikan_utama()
                messages.success(request, f'"{alamat.label}" sekarang menjadi alamat utama.')
                return redirect('alamat_saya')
            if aksi == 'hapus':
                label = alamat.label
                alamat.hapus_dan_pilih_pengganti()
                messages.success(request, f'Alamat "{label}" dihapus.')
                return redirect('alamat_saya')

        form = AlamatForm(request.POST, user=request.user, instance=alamat)
        if form.is_valid():
            form.simpan()
            messages.success(request, 'Alamat diperbarui.' if alamat else 'Alamat baru tersimpan.')
            return redirect('alamat_saya')
        sedang_ubah = alamat
    else:
        sedang_ubah = _ambil_alamat(milik, request.GET.get('ubah'))
        form = AlamatForm(user=request.user, instance=sedang_ubah)

    daftar = list(milik)
    return render(request, 'laundry/alamat_saya.html', {
        **_konteks_dasar(request.user, profil.role),
        'form': form,
        'sedang_ubah': sedang_ubah,
        'daftar_alamat': daftar,
        'jumlah_alamat': len(daftar),
        'maks_alamat': MAKS_ALAMAT,
        'wilayah': WILAYAH,
        'provinsi': PROVINSI,
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })


@login_required
def riwayat_pesanan(request):
    """Halaman "Riwayat pesanan": pesanan selesai/dibatalkan + ringkasan, filter, dan pembagian halaman."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    riwayat = RiwayatPesanan(request.user, request.GET)
    return render(request, 'laundry/riwayat_pesanan.html', {
        **_konteks_dasar(request.user, role),
        'riwayat': riwayat,
        'ringkasan': riwayat.ringkasan(),
        'halaman': riwayat.halaman(request.GET.get('page')),
    })


@login_required
def pengaturan(request):
    """Halaman \"Pengaturan\": ganti kata sandi dan preferensi notifikasi."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')

    aksi = request.POST.get('aksi') if request.method == 'POST' else None

    # Inisialisasi kedua form; hanya form yang disubmit yang diberi data POST
    form_sandi = UbahKataSandiForm(
        request.POST if aksi == 'ubah_sandi' else None,
        user=request.user,
    )
    form_notif = NotifikasiForm(
        request.POST if aksi == 'simpan_notif' else None,
        user=request.user,
    )

    if aksi == 'ubah_sandi' and form_sandi.is_valid():
        form_sandi.simpan()
        from django.contrib.auth import update_session_auth_hash
        update_session_auth_hash(request, request.user)
        messages.success(request, 'Kata sandi berhasil diubah.')
        return redirect('pengaturan')

    if aksi == 'simpan_notif' and form_notif.is_valid():
        form_notif.simpan()
        messages.success(request, 'Preferensi notifikasi diperbarui.')
        return redirect('pengaturan')

    x_forwarded = request.META.get('HTTP_X_FORWARDED_FOR')
    ip = x_forwarded.split(',')[0].strip() if x_forwarded else request.META.get('REMOTE_ADDR', '-')
    sesi_aktif = [{'perangkat': 'Sesi ini', 'ip': ip, 'waktu': request.user.last_login, 'aktif': True}]

    return render(request, 'laundry/pengaturan.html', {
        **_konteks_dasar(request.user, role),
        'form_sandi': form_sandi,
        'form_notif': form_notif,
        'sesi_aktif': sesi_aktif,
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })

@login_required
def notifikasi(request):
    """Halaman "Notifikasi": kabar pesanan, poin, dan hadiah milik pelanggan + filter dan tandai semua dibaca."""
    role = Profile.untuk(request.user).role
    if role == Profile.Role.ADMIN:
        return redirect('admin_dashboard')
    kotak = KotakNotifikasi(request.user, request.GET)
    if request.method == 'POST' and request.POST.get('aksi') == 'tandai_semua':
        jumlah = kotak.tandai_semua_dibaca()
        messages.success(request, f'{jumlah} notifikasi ditandai sudah dibaca.' if jumlah
                         else 'Semua notifikasi sudah dibaca.')
        return redirect(request.get_full_path())  # kembali ke halaman yang sama, filter tetap
    return render(request, 'laundry/notifikasi.html', {
        **_konteks_dasar(request.user, role),
        'kotak': kotak,
        'halaman': kotak.halaman(request.GET.get('page')),
        'whatsapp_admin': settings.WHATSAPP_ADMIN,
    })
