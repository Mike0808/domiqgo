from importlib import import_module

from django.apps import AppConfig


class PaymentsConfig(AppConfig):
    """Django-приложение модуля Payments.

    Устройство то же, что у остальных модулей (`modules/README.md`, «Модуль
    как Django-приложение»). Метка «payments» свободна с рождения — в отличие
    от Billing, которому придётся ждать переименования легаси (этап H).
    """

    name = "modules.payments"
    label = "payments"
    verbose_name = "Платежи"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")
