from importlib import import_module

from django.apps import AppConfig


class IdentityConfig(AppConfig):
    """Django-приложение модуля Identity.

    Устройство то же, что у остальных модулей (`modules/README.md`).
    """

    name = "modules.identity"
    label = "identity"
    verbose_name = "Учётные записи"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")
