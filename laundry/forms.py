from datetime import date
from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import transaction

from .models import Alamat, AnggotaTim, Booking, Profile
from .services import MAKS_ALAMAT, PROVINSI, WILAYAH, normalisasi_wa


class BookingForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)

    class Meta:
        model = Booking
        fields = ['nama', 'whatsapp', 'layanan', 'berat', 'alamat', 'catatan']
        widgets = {
            'nama': forms.TextInput(attrs={'placeholder': 'Masukkan nama Anda...'}),
            'whatsapp': forms.TextInput(attrs={'placeholder': 'Contoh: 08123456xxx', 'inputmode': 'tel'}),
            'berat': forms.NumberInput(attrs={'placeholder': 'Contoh: 4', 'step': '0.5', 'min': '1'}),
            'alamat': forms.TextInput(attrs={'placeholder': 'Tulis alamat lengkap penjemputan disini...'}),
            'catatan': forms.TextInput(attrs={'placeholder': 'Contoh: Jangan pakai pewangi, saya alergi'}),
        }
        labels = {
            'nama': 'Nama Lengkap',
            'whatsapp': 'Nomor WhatsApp',
            'layanan': 'Pilihan Layanan',
            'berat': 'Estimasi Berat (kg)',
            'alamat': 'Alamat Penjemputan',
            'catatan': 'Catatan Khusus',
        }

    def clean_whatsapp(self):
        nomor = ''.join(c for c in self.cleaned_data['whatsapp'] if c.isdigit())
        if len(nomor) < 9:
            raise forms.ValidationError('Nomor WhatsApp tidak valid. Contoh: 08123456789')
        return nomor


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Email address',
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
            'autofocus': True,
        }),
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.',
        },
    )
    password = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Enter your password',
            'autocomplete': 'current-password',
        }),
        error_messages={'required': 'Please enter your password.'},
    )
    remember_me = forms.BooleanField(label='Remember me', required=False, initial=True)

    error_messages = {
        'invalid_login': 'Incorrect email or password. Please try again.',
        'inactive': 'This account is inactive.',
    }


EMAIL_SUDAH_ADA = 'An account with this email already exists. Try logging in instead.'


class SignUpForm(forms.Form):
    """Pendaftaran pelanggan. Role TIDAK bisa diisi dari form: akun baru selalu USER."""

    full_name = forms.CharField(
        label='Full name',
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Enter your full name',
            'autocomplete': 'name',
            'autofocus': True,
        }),
        error_messages={'required': 'Please enter your full name.'},
    )
    email = forms.EmailField(
        label='Email address',
        max_length=150,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Enter your email address',
            'autocomplete': 'email',
        }),
        error_messages={
            'required': 'Please enter your email address.',
            'invalid': 'Please enter a valid email address.',
        },
    )
    whatsapp = forms.CharField(
        label='WhatsApp number',
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. 08123456789',
            'inputmode': 'tel',
            'autocomplete': 'tel',
        }),
        error_messages={'required': 'Please enter your WhatsApp number.'},
    )
    password1 = forms.CharField(
        label='Password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Create a password',
            'autocomplete': 'new-password',
        }),
        error_messages={'required': 'Please create a password.'},
    )
    password2 = forms.CharField(
        label='Confirm password',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Re-enter your password',
            'autocomplete': 'new-password',
        }),
        error_messages={'required': 'Please confirm your password.'},
    )

    def clean_full_name(self):
        return ' '.join(self.cleaned_data['full_name'].split())

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if get_user_model()._default_manager.filter(email__iexact=email).exists():
            raise ValidationError(EMAIL_SUDAH_ADA)
        return email

    def clean_whatsapp(self):
        nomor = normalisasi_wa(self.cleaned_data['whatsapp'])
        if not nomor:
            raise ValidationError('Please enter a valid WhatsApp number, e.g. 08123456789.')
        # satu nomor = satu akun, supaya pesanan tamu tidak salah tertaut
        if Profile.objects.filter(whatsapp=nomor).exists():
            raise ValidationError('This WhatsApp number is already used by another account.')
        return nomor

    def clean(self):
        data = super().clean()
        pw1, pw2 = data.get('password1'), data.get('password2')
        if pw1 and pw2 and pw1 != pw2:
            self.add_error('password2', "The two passwords don't match.")
        elif pw1:
            # user sementara agar validator "password mirip data diri" ikut bekerja
            nama_depan = (data.get('full_name') or '').split(' ')[0]
            sementara = get_user_model()(
                username=data.get('email', ''), email=data.get('email', ''), first_name=nama_depan,
            )
            try:
                validate_password(pw1, user=sementara)
            except ValidationError as e:
                self.add_error('password1', e)
        return data

    def save(self):
        """Buat akun pelanggan. Profil dengan role USER dibuat otomatis oleh signal."""
        nama_depan, _, nama_belakang = self.cleaned_data['full_name'].partition(' ')
        email = self.cleaned_data['email']
        user = get_user_model().objects.create_user(
            username=email,
            email=email,
            password=self.cleaned_data['password1'],
            first_name=nama_depan,
            last_name=nama_belakang,
        )
        Profile.objects.filter(user=user).update(whatsapp=self.cleaned_data['whatsapp'])
        return user


class FormDasar(forms.Form):
    """Kelas dasar untuk form non-model di halaman dashboard.

    OOP - Pewarisan: ProfilAkunForm dan TagihanForm mewarisi kelas ini, jadi aturan umum
    (label tanpa titik dua) ditulis satu kali saja.
    """

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)


class FormProfil(FormDasar):
    """Dasar form yang mengubah data milik SATU akun (User + Profile).

    OOP - Pewarisan: ProfilAkunForm mewarisi kelas ini, jadi pengambilan user/profil dan nilai awal form
    ditulis di satu tempat.
    OOP - Enkapsulasi: user dan profil disimpan di atribut internal (_user, _profile).
    OOP - Polimorfisme: view cukup memanggil is_valid() lalu simpan() pada form mana pun; tiap subkelas
    menyimpan bagian datanya sendiri.
    """

    def __init__(self, data=None, *, user, **kwargs):
        self._user = user
        self._profile = Profile.untuk(user)
        kwargs.setdefault('initial', self._nilai_awal())
        super().__init__(data, **kwargs)

    def _nilai_awal(self):
        return {}

    def simpan(self):
        raise NotImplementedError('Subkelas harus mengimplementasikan simpan().')


class ProfilAkunForm(FormProfil):
    """Form halaman "Akun saya": data pribadi dan kontak. Alamat diurus di halaman "Alamat saya".

    Email sengaja TIDAK ada di form ini: email dipakai untuk login, jadi hanya bisa dibaca.
    """

    nama_lengkap = forms.CharField(label='Nama lengkap', max_length=100,
                                   error_messages={'required': 'Nama lengkap wajib diisi.'})
    nama_panggilan = forms.CharField(label='Nama panggilan', max_length=50, required=False)
    whatsapp = forms.CharField(label='Nomor WhatsApp', max_length=20,
                               widget=forms.TextInput(attrs={'inputmode': 'tel'}),
                               error_messages={'required': 'Nomor WhatsApp wajib diisi.'})
    tanggal_lahir = forms.DateField(label='Tanggal lahir', required=False,
                                    widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
                                    error_messages={'invalid': 'Tanggal lahir tidak valid.'})

    def _nilai_awal(self):
        u, p = self._user, self._profile
        return {
            'nama_lengkap': u.get_full_name().strip(),
            'nama_panggilan': p.nama_panggilan,
            'whatsapp': p.whatsapp_tampil,
            'tanggal_lahir': p.tanggal_lahir,
        }

    def clean_nama_lengkap(self):
        return ' '.join(self.cleaned_data['nama_lengkap'].split())

    def clean_nama_panggilan(self):
        return ' '.join(self.cleaned_data['nama_panggilan'].split())

    def clean_whatsapp(self):
        nomor = normalisasi_wa(self.cleaned_data['whatsapp'])
        if not nomor:
            raise ValidationError('Nomor WhatsApp tidak valid. Contoh: 08123456789')
        # satu nomor = satu akun (agar pesanan tamu tidak salah tertaut), kecuali milik akun ini sendiri
        if Profile.objects.filter(whatsapp=nomor).exclude(pk=self._profile.pk).exists():
            raise ValidationError('Nomor ini sudah dipakai akun lain.')
        return nomor

    def clean_tanggal_lahir(self):
        tgl = self.cleaned_data['tanggal_lahir']
        if tgl and (tgl > date.today() or tgl.year < 1900):
            raise ValidationError('Tanggal lahir tidak valid.')
        return tgl

    def simpan(self):
        d = self.cleaned_data
        depan, _, belakang = d['nama_lengkap'].partition(' ')
        self._user.first_name, self._user.last_name = depan, belakang
        self._user.save(update_fields=['first_name', 'last_name'])
        p = self._profile
        p.nama_panggilan, p.whatsapp, p.tanggal_lahir = d['nama_panggilan'], d['whatsapp'], d['tanggal_lahir']
        p.save()
        return self._user


class AlamatForm(forms.ModelForm):
    """Form tambah/ubah satu alamat antar-jemput (halaman "Alamat saya").

    OOP - Pewarisan: mewarisi ModelForm bawaan Django (validasi dan pemetaan field ke model Alamat gratis),
    lalu menambah aturan khusus: kecamatan harus milik kota yang dipilih, kode pos 5 angka, dan batas jumlah alamat.
    OOP - Enkapsulasi: akun pemilik disimpan di atribut internal _user, dan seluruh proses penyimpanan
    (termasuk memindahkan status "alamat utama") dibungkus method simpan().
    """

    kota = forms.ChoiceField(label='Kota', choices=[(k, k) for k in WILAYAH])
    kecamatan = forms.ChoiceField(label='Kecamatan',
                                  error_messages={'invalid_choice': 'Pilih kecamatan yang sesuai dengan kota.',
                                                  'required': 'Pilih kecamatan.'})
    utama = forms.BooleanField(label='Jadikan sebagai alamat utama', required=False)  # bukan field Meta: diproses manual

    class Meta:
        model = Alamat
        fields = ['label', 'nama_penerima', 'whatsapp', 'alamat_lengkap', 'kecamatan', 'kota', 'kode_pos', 'catatan_kurir']
        labels = {'label': 'Label alamat', 'nama_penerima': 'Nama penerima', 'whatsapp': 'Nomor WhatsApp',
                  'alamat_lengkap': 'Alamat lengkap', 'kode_pos': 'Kode pos', 'catatan_kurir': 'Catatan untuk kurir'}
        widgets = {
            'label': forms.TextInput(attrs={'placeholder': 'Contoh: Rumah, Kantor, Kos', 'maxlength': 30}),
            'nama_penerima': forms.TextInput(attrs={'autocomplete': 'name'}),
            'whatsapp': forms.TextInput(attrs={'inputmode': 'tel'}),
            'alamat_lengkap': forms.TextInput(attrs={'placeholder': 'Jalan, nomor rumah, RT/RW'}),
            'kode_pos': forms.TextInput(attrs={'inputmode': 'numeric', 'maxlength': 5}),
            'catatan_kurir': forms.Textarea(attrs={'rows': 3, 'placeholder': 'Contoh: Bangunan kedua, pagar abu-abu'}),
        }
        error_messages = {
            'label': {'required': 'Label alamat wajib diisi.'},
            'nama_penerima': {'required': 'Nama penerima wajib diisi.'},
            'whatsapp': {'required': 'Nomor WhatsApp wajib diisi.'},
            'alamat_lengkap': {'required': 'Alamat lengkap wajib diisi.'},
        }

    def __init__(self, *args, user, **kwargs):
        self._user = user
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)
        self.fields['kode_pos'].required = False
        self.fields['catatan_kurir'].required = False
        if not self.instance.pk:  # alamat baru: isi nama dan WhatsApp dari akun sebagai saran
            self.initial.setdefault('nama_penerima', user.get_full_name().strip())
            self.initial.setdefault('whatsapp', Profile.untuk(user).whatsapp_tampil)
            self.initial.setdefault('kota', next(iter(WILAYAH)))
        else:
            self.initial['whatsapp'] = self.instance.whatsapp_tampil
            self.initial['utama'] = self.instance.utama
        # pilihan kecamatan mengikuti kota yang sedang dipilih (data terkirim, alamat yang diubah, atau bawaan)
        kota = self.data.get('kota') if self.is_bound else self.initial.get('kota')
        self.fields['kecamatan'].choices = [('', 'Pilih kecamatan')] + [(k, k) for k in WILAYAH.get(kota, [])]

    def clean_label(self):
        return ' '.join(self.cleaned_data['label'].split())

    def clean_nama_penerima(self):
        return ' '.join(self.cleaned_data['nama_penerima'].split())

    def clean_whatsapp(self):
        nomor = normalisasi_wa(self.cleaned_data['whatsapp'])
        if not nomor:
            raise ValidationError('Nomor WhatsApp tidak valid. Contoh: 08123456789')
        return nomor

    def clean_alamat_lengkap(self):
        alamat = ' '.join(self.cleaned_data['alamat_lengkap'].split())
        if len(alamat) < 8:
            raise ValidationError('Tulis alamat selengkap mungkin (jalan dan nomor).')
        return alamat

    def clean_kode_pos(self):
        kode = self.cleaned_data['kode_pos'].strip()
        if kode and not (kode.isdigit() and len(kode) == 5):
            raise ValidationError('Kode pos terdiri dari 5 angka.')
        return kode

    def clean(self):
        data = super().clean()
        if not self.instance.pk and Alamat.objects.filter(user=self._user).count() >= MAKS_ALAMAT:
            raise ValidationError(f'Alamat tersimpan sudah mencapai batas {MAKS_ALAMAT}. Hapus salah satu dulu.')
        return data

    @transaction.atomic
    def simpan(self):
        alamat = super().save(commit=False)
        alamat.user = self._user
        alamat.provinsi = PROVINSI
        alamat.save()
        if self.cleaned_data.get('utama'):
            alamat.jadikan_utama()
        return alamat


class TagihanForm(FormDasar):
    """Form admin: berat hasil timbang dan koreksi harga satu pesanan."""

    berat_final = forms.DecimalField(label='Berat/jumlah hasil timbang', max_digits=5, decimal_places=1,
                                     min_value=Decimal('0.1'),
                                     widget=forms.NumberInput(attrs={'step': '0.1', 'min': '0.1'}),
                                     error_messages={'required': 'Isi berat/jumlah hasil timbang.',
                                                     'min_value': 'Berat minimal 0,1.', 'invalid': 'Angka tidak valid.'})
    koreksi_harga = forms.IntegerField(label='Koreksi harga (Rp)', required=False, min_value=-10_000_000,
                                       max_value=10_000_000, initial=0,
                                       widget=forms.NumberInput(attrs={'step': '500'}),
                                       error_messages={'invalid': 'Angka tidak valid.'})
    catatan_koreksi = forms.CharField(label='Alasan koreksi', max_length=120, required=False,
                                      widget=forms.TextInput(attrs={'placeholder': 'Contoh: Noda membandel, biaya tambahan'}))

    def clean_koreksi_harga(self):
        return self.cleaned_data.get('koreksi_harga') or 0

    def clean(self):
        data = super().clean()
        if data.get('koreksi_harga') and not (data.get('catatan_koreksi') or '').strip():
            self.add_error('catatan_koreksi', 'Isi alasan koreksi harga.')
        return data


class UbahKataSandiForm(FormProfil):
    """Form ganti kata sandi di halaman \"Pengaturan\".

    OOP - Pewarisan: mewarisi FormProfil agar pola pengambilan user/profil seragam.
    """

    kata_sandi_lama = forms.CharField(
        label='Kata sandi saat ini',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'current-password', 'placeholder': 'Masukkan kata sandi saat ini'}),
        error_messages={'required': 'Kata sandi saat ini wajib diisi.'},
    )
    kata_sandi_baru = forms.CharField(
        label='Kata sandi baru',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Minimal 8 karakter'}),
        error_messages={'required': 'Kata sandi baru wajib diisi.'},
    )
    konfirmasi_sandi = forms.CharField(
        label='Konfirmasi kata sandi baru',
        strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'placeholder': 'Ulangi kata sandi baru'}),
        error_messages={'required': 'Konfirmasi kata sandi wajib diisi.'},
    )

    def clean_kata_sandi_lama(self):
        lama = self.cleaned_data['kata_sandi_lama']
        if not self._user.check_password(lama):
            raise ValidationError('Kata sandi saat ini tidak cocok.')
        return lama

    def clean(self):
        data = super().clean()
        baru = data.get('kata_sandi_baru')
        konfirmasi = data.get('konfirmasi_sandi')
        if baru and konfirmasi and baru != konfirmasi:
            self.add_error('konfirmasi_sandi', 'Konfirmasi kata sandi tidak cocok.')
        elif baru:
            try:
                validate_password(baru, user=self._user)
            except ValidationError as e:
                self.add_error('kata_sandi_baru', e)
        return data

    def simpan(self):
        self._user.set_password(self.cleaned_data['kata_sandi_baru'])
        self._user.save(update_fields=['password'])
        return self._user


class NotifikasiForm(FormProfil):
    """Form preferensi notifikasi di halaman \"Pengaturan\".

    OOP - Pewarisan: mewarisi FormProfil agar pola pengambilan user/profil seragam.
    """

    notif_status_pesanan = forms.BooleanField(label='Update status pesanan', required=False)
    notif_whatsapp = forms.BooleanField(label='Notifikasi WhatsApp', required=False)
    notif_email = forms.BooleanField(label='Notifikasi Email', required=False)
    notif_poin = forms.BooleanField(label='Info poin & hadiah', required=False)
    notif_promo = forms.BooleanField(label='Promo & penawaran', required=False)

    def _nilai_awal(self):
        p = self._profile
        return {
            'notif_status_pesanan': p.notif_status_pesanan,
            'notif_whatsapp': p.notif_whatsapp,
            'notif_email': p.notif_email,
            'notif_poin': p.notif_poin,
            'notif_promo': p.notif_promo,
        }

    def simpan(self):
        d = self.cleaned_data
        p = self._profile
        p.notif_status_pesanan = d['notif_status_pesanan']
        p.notif_whatsapp = d['notif_whatsapp']
        p.notif_email = d['notif_email']
        p.notif_poin = d['notif_poin']
        p.notif_promo = d['notif_promo']
        p.save(update_fields=['notif_status_pesanan', 'notif_whatsapp', 'notif_email', 'notif_poin', 'notif_promo'])
        return p


class AnggotaTimForm(forms.ModelForm):
    """Form tambah dan edit anggota di panel admin (menu Anggota Tim)."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault('label_suffix', '')
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.is_bound:
            self.initial['telepon'] = self.instance.telepon_fmt  # tampil 0812-1100-1001, bukan 62812...

    class Meta:
        model = AnggotaTim
        fields = ['nama', 'email', 'telepon', 'peran']
        widgets = {
            'nama': forms.TextInput(attrs={'placeholder': 'Masukkan nama lengkap', 'autocomplete': 'off'}),
            'email': forms.EmailInput(attrs={'placeholder': 'nama@wuwashy.id', 'autocomplete': 'off'}),
            'telepon': forms.TextInput(attrs={'placeholder': 'cth. 0812-1100-0000', 'inputmode': 'tel',
                                              'autocomplete': 'off'}),
            'peran': forms.RadioSelect,
        }
        error_messages = {
            'nama': {'required': 'Masukkan nama lengkap anggota.'},
            'email': {'required': 'Masukkan alamat email anggota.', 'invalid': 'Masukkan alamat email yang valid.'},
            'telepon': {'required': 'Masukkan nomor telepon anggota.'},
            'peran': {'required': 'Pilih peran anggota.', 'invalid_choice': 'Pilih salah satu: Kasir atau Kurir.'},
        }

    def full_clean(self):
        super().full_clean()
        # tandai kolom bermasalah untuk pembaca layar (dipakai juga oleh CSS)
        for nama in self.errors:
            if nama in self.fields:
                self.fields[nama].widget.attrs.update({'aria-invalid': 'true', 'aria-describedby': f'err-{nama}'})

    def clean_nama(self):
        return ' '.join(self.cleaned_data['nama'].split())

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()

    def clean_telepon(self):
        nomor = normalisasi_wa(self.cleaned_data['telepon'])
        if not nomor:
            raise ValidationError('Masukkan nomor telepon yang valid, cth. 0812-1100-1001.')
        return nomor
