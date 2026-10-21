from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from .models import Booking, Profile
from .services import normalisasi_wa


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
            'berat': forms.NumberInput(attrs={'placeholder': 'Masukkan jumlah pakaian (misal: 5)', 'step': '1', 'min': '1'}),
            'alamat': forms.TextInput(attrs={'placeholder': 'Tulis alamat lengkap penjemputan di sini...'}),
            'catatan': forms.TextInput(attrs={'placeholder': 'Contoh: Jangan pakai pewangi, saya alergi'}),
        }
        labels = {
            'nama': 'Nama Lengkap',
            'whatsapp': 'Nomor WhatsApp',
            'layanan': 'Pilihan Layanan',
            'berat': 'Jumlah Pakaian (pcs)',
            'alamat': 'Alamat Penjemputan',
            'catatan': 'Catatan Khusus',
        }

    def clean_berat(self):
        jumlah = self.cleaned_data['berat']
        if jumlah != jumlah.to_integral_value():
            raise forms.ValidationError('Jumlah pakaian harus bilangan bulat (pcs).')
        return jumlah

    def clean_whatsapp(self):
        nomor = ''.join(c for c in self.cleaned_data['whatsapp'] if c.isdigit())
        if len(nomor) < 9:
            raise forms.ValidationError('Nomor WhatsApp tidak valid. Contoh: 08123456789')
        return nomor


class EmailLoginForm(AuthenticationForm):
    username = forms.EmailField(
        label='Alamat email',
        widget=forms.EmailInput(attrs={
            'placeholder': 'Masukkan alamat emailmu',
            'autocomplete': 'email',
            'autofocus': True,
        }),
        error_messages={
            'required': 'Masukkan alamat emailmu.',
            'invalid': 'Masukkan alamat email yang valid.',
        },
    )
    password = forms.CharField(
        label='Kata sandi',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Masukkan kata sandimu',
            'autocomplete': 'current-password',
        }),
        error_messages={'required': 'Masukkan kata sandimu.'},
    )
    remember_me = forms.BooleanField(label='Ingat saya', required=False, initial=True)

    error_messages = {
        'invalid_login': 'Email atau kata sandi salah. Silakan coba lagi.',
        'inactive': 'Akun ini tidak aktif.',
    }


EMAIL_SUDAH_ADA = 'Email ini sudah terdaftar. Coba masuk saja.'


class SignUpForm(forms.Form):
    """Pendaftaran pelanggan. Role TIDAK bisa diisi dari form: akun baru selalu USER."""

    full_name = forms.CharField(
        label='Nama lengkap',
        max_length=100,
        widget=forms.TextInput(attrs={
            'placeholder': 'Masukkan nama lengkapmu',
            'autocomplete': 'name',
            'autofocus': True,
        }),
        error_messages={'required': 'Masukkan nama lengkapmu.'},
    )
    email = forms.EmailField(
        label='Alamat email',
        max_length=150,
        widget=forms.EmailInput(attrs={
            'placeholder': 'Masukkan alamat emailmu',
            'autocomplete': 'email',
        }),
        error_messages={
            'required': 'Masukkan alamat emailmu.',
            'invalid': 'Masukkan alamat email yang valid.',
        },
    )
    whatsapp = forms.CharField(
        label='Nomor WhatsApp',
        max_length=20,
        widget=forms.TextInput(attrs={
            'placeholder': 'cth. 08123456789',
            'inputmode': 'tel',
            'autocomplete': 'tel',
        }),
        error_messages={'required': 'Masukkan nomor WhatsAppmu.'},
    )
    password1 = forms.CharField(
        label='Kata sandi',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Buat kata sandi',
            'autocomplete': 'new-password',
        }),
        error_messages={'required': 'Buat kata sandimu.'},
    )
    password2 = forms.CharField(
        label='Konfirmasi kata sandi',
        strip=False,
        widget=forms.PasswordInput(attrs={
            'placeholder': 'Ulangi kata sandimu',
            'autocomplete': 'new-password',
        }),
        error_messages={'required': 'Konfirmasi kata sandimu.'},
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
            raise ValidationError('Masukkan nomor WhatsApp yang valid, cth. 08123456789.')
        # satu nomor = satu akun, supaya pesanan tamu tidak salah tertaut
        if Profile.objects.filter(whatsapp=nomor).exists():
            raise ValidationError('Nomor WhatsApp ini sudah dipakai akun lain.')
        return nomor

    def clean(self):
        data = super().clean()
        pw1, pw2 = data.get('password1'), data.get('password2')
        if pw1 and pw2 and pw1 != pw2:
            self.add_error('password2', 'Kedua kata sandi tidak sama.')
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
