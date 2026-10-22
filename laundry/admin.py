from django.contrib import admin
from .models import Alamat, AnggotaTim, Booking, Notifikasi, PoinLog, Profile


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('resi', 'nama', 'whatsapp', 'layanan', 'berat', 'berat_final', 'koreksi_harga', 'status', 'user', 'asal', 'dibuat')
    list_editable = ('status',)
    list_filter = ('status', 'layanan', 'asal', 'dibuat')
    search_fields = ('resi', 'nama', 'whatsapp', 'alamat', 'user__email')
    autocomplete_fields = ('user',)


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'role', 'whatsapp')
    list_editable = ('role',)
    list_filter = ('role',)
    search_fields = ('user__username', 'user__email', 'user__first_name', 'user__last_name', 'whatsapp')


@admin.register(PoinLog)
class PoinLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'jumlah', 'saldo', 'keterangan', 'booking', 'dibuat')
    list_filter = ('dibuat',)
    search_fields = ('user__email', 'booking__resi')
    readonly_fields = ('dibuat',)


@admin.register(Notifikasi)
class NotifikasiAdmin(admin.ModelAdmin):
    list_display = ('user', 'judul', 'booking', 'dibaca', 'dibuat')
    list_filter = ('dibaca', 'dibuat')
    search_fields = ('user__email', 'judul', 'booking__resi')


@admin.register(Alamat)
class AlamatAdmin(admin.ModelAdmin):
    list_display = ('user', 'label', 'nama_penerima', 'kecamatan', 'kota', 'utama', 'dibuat')
    list_filter = ('utama', 'kota')
    search_fields = ('user__email', 'nama_penerima', 'alamat_lengkap')


@admin.register(AnggotaTim)
class AnggotaTimAdmin(admin.ModelAdmin):
    list_display = ('nama', 'peran', 'email', 'telepon', 'aktif', 'dibuat')
    list_editable = ('aktif',)
    list_filter = ('peran', 'aktif')
    search_fields = ('nama', 'email', 'telepon')
