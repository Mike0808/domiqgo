from decimal import Decimal

from django.conf import settings
from django.db import models

# Объект недвижимости принадлежит Properties (шаг C3b). Здесь он нужен только
# как цель двух оставшихся внешних ключей; читать его поля следует через
# `modules.properties.api`.
from modules.properties.infrastructure.models import Apartment

# `Apartment` уехал в `modules/properties/` шагом C3b: домен, публичный API,
# события. Таблица переименована в `properties_apartment`. Читать объект
# отсюда следует через `modules.properties.api`; два внешних ключа на него
# пока остаются — `Tenant.apartment` ждёт Tenancy (этап D),
# `MonthlyStatement.apartment` — шага E2, где ключом счёта станет договор.

class Tenant(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
                                related_name="tenant")
    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="tenants")
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    # Plan 2 hooks:
    messenger_platform = models.CharField(max_length=10, blank=True)
    messenger_chat_id = models.CharField(max_length=64, blank=True)
    link_code = models.CharField(max_length=32, blank=True)
    # 152-ФЗ: consent must be on file, for the current policy version,
    # before a tenant may connect any OAuth provider (see billing/adapters.py).
    privacy_consent_at = models.DateTimeField(
        "Согласие на обработку ПДн дано", null=True, blank=True)
    privacy_consent_version = models.CharField(
        "Версия политики на момент согласия", max_length=32, blank=True)

    class Meta:
        verbose_name = "Жилец"
        verbose_name_plural = "Жильцы"

    def __str__(self):
        return self.full_name or self.user.get_username()

# `Tariff` уехал в modules/tariffs/ шагом C1: у него не было ни одного FK и на
# него не ссылалась ни одна модель, поэтому лист графа отделился без разрыва
# связей. Ставки читаются через `modules.tariffs.api.get_rates_on`.

# `METER_KIND_CHOICES`, `Meter` и `MeterReading` уехали в
# `modules/metering/` шагом C2c плана миграции. Таблицы переименованы в
# `metering_meter` и `metering_reading`; словарь стал каталогом видов ресурса
# `modules/metering/domain/catalogue.py`. Читать их отсюда следует только
# через `modules.metering.api`.

class MonthlyStatement(models.Model):
    UNPAID = "unpaid"; PENDING = "pending"; PAID = "paid"
    STATUS_CHOICES = [(UNPAID, "Не оплачено"), (PENDING, "На проверке"), (PAID, "Оплачено")]

    apartment = models.ForeignKey(Apartment, on_delete=models.PROTECT, related_name="statements")
    period = models.DateField("Период")
    lines = models.JSONField("Строки начисления", default=list)
    total = models.DecimalField("Итого", max_digits=12, decimal_places=2, default=Decimal("0"))
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=UNPAID)

    class Meta:
        verbose_name = "Начисление"
        verbose_name_plural = "Начисления"
        unique_together = [("apartment", "period")]
        ordering = ["-period"]

    def __str__(self):
        return f"{self.apartment} {self.period:%Y-%m} — {self.total} ₽"

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

def receipt_upload_path(instance, filename):
    return f"receipts/statement_{instance.statement_id}/{filename}"

class Payment(models.Model):
    TELEGRAM = "telegram"; MAX = "max"; WEB = "web"
    SOURCE_CHOICES = [(TELEGRAM, "Telegram"), (MAX, "MAX"), (WEB, "Веб")]
    PENDING = "pending"; CONFIRMED = "confirmed"; REJECTED = "rejected"
    STATUS_CHOICES = [
        (PENDING, "На проверке"), (CONFIRMED, "Подтверждён"), (REJECTED, "Отклонён"),
    ]

    statement = models.ForeignKey(MonthlyStatement, on_delete=models.CASCADE,
                                  related_name="payments")
    file = models.FileField("Чек", upload_to=receipt_upload_path)
    source = models.CharField("Источник", max_length=10, choices=SOURCE_CHOICES)
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES, default=PENDING)
    note = models.CharField("Примечание", max_length=300, blank=True)
    submitted_at = models.DateTimeField("Получен", auto_now_add=True)

    class Meta:
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Платёж {self.statement} ({self.get_status_display()})"
