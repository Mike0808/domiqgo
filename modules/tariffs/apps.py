from importlib import import_module

from django.apps import AppConfig


class TariffsConfig(AppConfig):
    """Django-приложение модуля Tariffs.

    `label` задан явно: по умолчанию Django взял бы последний сегмент имени, и
    это сработало бы, но полагаться на совпадение не стоит — `modules.billing`
    в своё время столкнётся с меткой существующего `billing` (см.
    `modules/README.md`), и привычка объявлять метку должна появиться раньше
    этого столкновения.

    `import_models` переопределён, потому что модели живут в
    `infrastructure/models.py` (правило 3.3), а Django ищет их в
    `<приложение>.models`. Альтернатива — файл-пустышка `models.py` с
    реэкспортом — выглядела бы как нарушение правила для того, кто читает
    дерево, и прятала бы настоящее место объявления.
    """

    name = "modules.tariffs"
    label = "tariffs"
    verbose_name = "Тарифы"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")

    def ready(self):
        """Админка тоже лежит в `infrastructure/` — Django ищет её в
        `<приложение>.admin` и сам туда не заглянет."""
        import_module(f"{self.name}.infrastructure.admin")
