from django.apps import AppConfig


class LaundryConfig(AppConfig):
    name = 'laundry'

    def ready(self):
        from . import signals  # noqa: F401  (mendaftarkan signal)
