from importlib import import_module

from django.apps import AppConfig


class TenancyConfig(AppConfig):
    """Django-приложение модуля Tenancy.

    Устройство то же, что у остальных модулей (`modules/README.md`).
    Единственное отличие — `ready` подписывает модуль на события Properties:
    первый подписчик в системе.
    """

    name = "modules.tenancy"
    label = "tenancy"
    verbose_name = "Договоры"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")

    def ready(self):
        from .application import subscriptions
        from .infrastructure import repository

        subscriptions.wire(repository)
