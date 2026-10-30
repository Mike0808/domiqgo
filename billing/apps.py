from django.apps import AppConfig


class BillingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'billing'

    def ready(self):
        """Сшивки интерфейсного слоя: то, чему нужны оба берега матрицы.

        Сверка с шага H3 подписывается сама (`modules/billing/apps.py`);
        здесь остались внедрения — провайдеры через границы, которые модулям
        пересекать нельзя.
        """
        from modules.billing import api as billing
        from modules.identity import api as identity
        from modules.notifications import api as notifications
        from modules.payments import api as payments

        # «На проверке» — знание Payments, а стрелка payments → billing не
        # разворачивается (ADR-0014/0015): провайдер заявленных платежей
        # внедряет интерфейсный слой — как резолвер владельцев в F3.
        billing.wire(has_pending_claim=payments.has_pending_claim)
        # Метаданные документов для выгрузок (ADR-0022): модуля Documents
        # нет, файлы пока висят на профиле жильца — сшивает интерфейсный
        # слой, которому видны обе стороны.
        from modules.reporting import api as reporting
        from modules.tenancy import api as tenancy_api

        def _documents_meta(tenancy_id):
            from .models import Document

            contract = tenancy_api.get_tenancy(tenancy_id)
            if contract is None:
                return []
            return [{"title": doc.title, "uploaded_at": doc.uploaded_at}
                    for doc in Document.objects.filter(
                        tenant__user_id=contract.account_id)]

        reporting.wire(_documents_meta)
        # Уведомления подписываются здесь же (F3): резолвер владельцев —
        # Identity, а Notifications его вызывать не вправе (матрица §2);
        # сшивает тот, кому видны оба, — интерфейсный слой.
        notifications.subscribe_to_domain_events(identity.list_owner_accounts)
