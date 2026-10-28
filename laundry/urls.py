from django.contrib.auth.views import LogoutView
from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('about/', views.about, name='about'),
    path('services/', views.services, name='services'),
    path('booking/', views.booking, name='booking'),
    path('login/', views.LoginView.as_view(), name='login'),
    path('signup/', views.signup, name='signup'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('akun/', views.akun_saya, name='akun_saya'),
    path('alamat/', views.alamat_saya, name='alamat_saya'),
    path('pesanan/', views.pesanan_saya, name='pesanan_saya'),
    path('cari/', views.cari_pesanan, name='cari_pesanan'),
    path('riwayat/', views.riwayat_pesanan, name='riwayat_pesanan'),
    path('notifikasi/', views.notifikasi, name='notifikasi'),
    path('poin/', views.poin_hadiah, name='poin_hadiah'),
    path('pengaturan/', views.pengaturan, name='pengaturan'),
    path('panel/', views.admin_dashboard, name='admin_dashboard'),
    path('panel/pesanan/', views.admin_pesanan, name='admin_pesanan'),
    path('panel/pesanan/menunggu/', views.admin_menunggu, name='admin_menunggu'),
    path('panel/pesanan/diproses/', views.admin_diproses, name='admin_diproses'),
    path('panel/pesanan/selesai/', views.admin_selesai, name='admin_selesai'),
    path('panel/pesanan/dibatalkan/', views.admin_dibatalkan, name='admin_dibatalkan'),
    path('panel/pesanan/<int:pk>/', views.admin_pesanan_detail, name='admin_pesanan_detail'),
    path('panel/laporan/', views.admin_laporan, name='admin_laporan'),
    path('panel/laporan/unduh/', views.admin_laporan_unduh, name='admin_laporan_unduh'),
    path('panel/anggota/', views.admin_anggota, name='admin_anggota'),
    path('panel/anggota/<int:pk>/edit/', views.admin_anggota_edit, name='admin_anggota_edit'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
