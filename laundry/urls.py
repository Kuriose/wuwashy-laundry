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
    path('pesanan/', views.pesanan_saya, name='pesanan_saya'),
    path('poin/', views.poin_hadiah, name='poin_hadiah'),
    path('panel/', views.admin_dashboard, name='admin_dashboard'),
    path('panel/pesanan/<int:pk>/', views.admin_pesanan_detail, name='admin_pesanan_detail'),
    path('logout/', LogoutView.as_view(), name='logout'),
]
