from django.apps import AppConfig


class ColetaConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "coleta"
    verbose_name = "coleta de dados"

    def ready(self):
        from . import signals  # noqa: F401
