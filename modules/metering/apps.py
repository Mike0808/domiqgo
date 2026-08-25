from importlib import import_module

from django.apps import AppConfig


class MeteringConfig(AppConfig):
    """Django-приложение модуля Metering.

    Устройство то же, что у Tariffs (`modules/README.md`, «Модуль как
    Django-приложение»): метка задана явно, модели лежат в `infrastructure/`
    (правило 3.3) и подставляются переопределённым `import_models`, миграции —
    в `infrastructure/migrations/` через `MIGRATION_MODULES`.
    """

    name = "modules.metering"
    label = "metering"
    verbose_name = "Учёт показаний"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")

    # `ready()` не импортирует админку, в отличие от Tariffs: её у модуля нет.
    # Списки приборов и показаний показывают квартиру по названию, а название
    # принадлежит Properties — обратиться к ней Metering не вправе (лист графа,
    # матрица §2). Админка осталась в `billing/admin.py` как интерфейсный слой,
    # которому видны оба модуля; перенести её, не потеряв название квартиры,
    # можно будет только вместе с отдельным слоем сборки экранов.
