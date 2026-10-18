from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend


class EmailBackend(ModelBackend):
    """Login memakai alamat email (tidak peka huruf besar/kecil).

    ModelBackend (login dengan username) tetap aktif di settings, jadi
    superuser masih bisa masuk ke /admin/ memakai username.
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username or not password:
            return None
        User = get_user_model()
        try:
            user = User._default_manager.get(email__iexact=username.strip())
        except User.DoesNotExist:
            # samakan waktu respons agar keberadaan email tidak bisa ditebak
            User().set_password(password)
            return None
        except User.MultipleObjectsReturned:
            # email yang dipakai lebih dari satu akun -> ambigu, tolak
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
