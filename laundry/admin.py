from django.contrib import admin
from .models import Booking, PoinLog, Profile


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('resi', 'nama', 'whatsapp', 'layanan', 'berat', 'status', 'user', 'asal', 'dibuat')
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
