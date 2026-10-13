from django.apps import AppConfig


class StoreConfig(AppConfig):
    name = "store"
    verbose_name = "Магазин"

    def ready(self):
        from . import signals  # noqa: F401
