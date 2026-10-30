from django.conf import settings
from django.db import models

# Объект недвижимости принадлежит Properties (шаг C3b). Здесь он нужен только
# как цель последнего внешнего ключа — `Tenant.apartment`; читать его поля
# следует через `modules.properties.api`.
from modules.properties.infrastructure.models import Apartment

# Платёж принадлежит Payments (шаг H2). Таблица переименована в
# `payments_payment`, команды — `modules.payments.api`. Реэкспорт модели —
# для интерфейсного слоя (админка, тесты), как `Apartment` выше;
# `receipt_upload_path` — для исторических миграций, которые помнят её
# по этому адресу.
from modules.payments.infrastructure.models import (  # noqa: F401
    Payment, receipt_upload_path,
)

# Счёт, сверка и политика принадлежат Billing (шаг H3; метка приложения —
# «invoicing», таблицы остались `billing_*`). Команды — `modules.billing.api`;
# реэкспорт моделей — для интерфейсного слоя: админки, кабинета, тестов.
from modules.billing.infrastructure.models import (  # noqa: F401
    BillingPolicy, MonthlyStatement, Settlement,
)

# `Tariff` уехал в modules/tariffs/ шагом C1, `Meter` и `MeterReading` — в
# modules/metering/ шагом C2c: читать их следует через api модулей.

class Tenant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="tenant")
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="tenants")
    # ФИО уехало в договор (D1c, ADR-0010), согласие и код привязки — в
    # Identity (C4a, C4c), адрес мессенджера — в Notifications (F1): канал
    # доставки принадлежит учётной записи, а не проживанию. От профиля
    # остались связи; их разберёт расформирование `billing/`.

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    @property
    def display_name(self) -> str:
        """ФИО из действующего договора учётной записи, иначе имя входа.

        Спрашивается у Tenancy на сегодняшний день: «сегодня» — понятие
        интерфейса, и модуль его не читает сам.
        """
        from django.utils import timezone
        from modules.tenancy import api as tenancy

        contract = tenancy.active_tenancy_for_account(self.user_id, timezone.localdate())
        if contract is not None and contract.full_name:
            return contract.full_name
        return self.user.get_username()

    def __str__(self):
        return self.display_name


def document_upload_path(instance, filename):
    return f"documents/tenant_{instance.tenant_id}/{filename}"

class Document(models.Model):
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="documents")
    file = models.FileField("Файл", upload_to=document_upload_path)
    title = models.CharField("Название", max_length=200, default="Договор аренды")
    uploaded_at = models.DateTimeField("Загружен", auto_now_add=True)

    class Meta:
        verbose_name = "Документ"
        verbose_name_plural = "Документы"

    def __str__(self):
        return self.title
