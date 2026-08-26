from importlib import import_module

from django.apps import AppConfig


class PropertiesConfig(AppConfig):
    """Django-приложение модуля Properties.

    Устройство то же, что у Tariffs и Metering (`modules/README.md`, «Модуль
    как Django-приложение»). Админки у модуля нет: карточка объекта показывает
    поля, которые ему не принадлежат — арендную ставку Tenancy и политику
    округления Billing, — и разделить экран можно будет только после того, как
    эти поля разъедутся по владельцам.
    """

    name = "modules.properties"
    label = "properties"
    verbose_name = "Объекты"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")
