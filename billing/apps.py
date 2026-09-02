from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'

    def ready(self):
        """Сверка слушает платёжные события (шаг E3, ADR-0015).

        Подписка легаси-приложения — временная: при расформировании
        `billing/` она переедет в `application/` модуля Billing.
        """
        from bus import subscribe
        from modules.payments.events import PaymentConfirmed, PaymentVoided

        from .services import settlement

        subscribe(PaymentConfirmed, settlement.apply_confirmed)
        subscribe(PaymentVoided, settlement.apply_voided)
