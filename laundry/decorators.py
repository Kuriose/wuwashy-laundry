from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.urls import reverse

from .models import Profile


def admin_required(view):
    """Hanya role ADMIN. Anonim -> halaman login admin; USER biasa -> 403."""

    @wraps(view)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse('login'))
        if not Profile.untuk(request.user).is_admin:
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapper
