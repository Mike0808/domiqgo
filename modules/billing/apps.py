from importlib import import_module

from django.apps import AppConfig


class BillingConfig(AppConfig):
    """Django-приложение модуля Billing.

    Метка — «invoicing»: метку «billing» держит легаси-приложение до шага H4,
    а менять метку после — хирургия `django_migrations` и `django_content_type`
    ради косметики. Имя таблиц и без того говорит от лица владельца:
    `billing_*` — префикс модуля по правилу 5.1 (совпадает с именем каталога
    `modules/billing`, а не с меткой).
    """

    name = "modules.billing"
    label = "invoicing"
    verbose_name = "Счета"
    default_auto_field = "django.db.models.BigAutoField"

    def import_models(self):
        super().import_models()
        self.models_module = import_module(f"{self.name}.infrastructure.models")

    def ready(self):
        """Сверка слушает платёжные события сама (ADR-0015): подписка
        переехала из легаси-`billing/` при расформировании (шаг H3)."""
        from .application import subscriptions

        subscriptions.wire()
