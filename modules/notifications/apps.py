from importlib import import_module

from django.apps import AppConfig


class NotificationsConfig(AppConfig):
    """Django-приложение модуля Notifications.

    Устройство то же, что у остальных модулей (`modules/README.md`).
    """

    name = "modules.notifications"
    label = "notifications"
    verbose_name = "Уведомления"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")

    def ready(self):
        # Админка лежит в `infrastructure/` — Django сам туда не заглянет.
        import_module(f"{self.name}.infrastructure.admin")
