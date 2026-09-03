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
        from modules.identity import api as identity
        from modules.notifications import api as notifications
        from modules.payments.events import PaymentConfirmed, PaymentVoided

        from .services import settlement

        subscribe(PaymentConfirmed, settlement.apply_confirmed)
        subscribe(PaymentVoided, settlement.apply_voided)
        # Уведомления подписываются здесь же (F3): резолвер владельцев —
        # Identity, а Notifications его вызывать не вправе (матрица §2);
        # сшивает тот, кому видны оба, — интерфейсный слой.
        notifications.subscribe_to_domain_events(identity.list_owner_accounts)
