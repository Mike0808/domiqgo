"""Модель платежа — деталь хранения модуля Payments (шаг H2).

Таблица `payments_payment` принята из легаси (`billing_payment`) парой
миграций по образцу Metering и Properties. Ссылка на счёт — идентификатор без
констрейнта (правило 1.3): каскада от удаления счёта больше нет, и домену это
впору — платёж не удаляется даже вслед за счётом (инв. 5). Правила переходов
живут в `domain/payment.py`; модель лишь хранит.
"""

from django.db import models

from ..domain import payment as rules


def receipt_upload_path(instance, filename):
    return f"receipts/statement_{instance.statement_id}/{filename}"


class Payment(models.Model):
    TELEGRAM = rules.TELEGRAM; MAX = rules.MAX; WEB = rules.WEB
    MANUAL = rules.MANUAL
    SOURCE_CHOICES = rules.SOURCE_CHOICES
    PENDING = rules.PENDING; CONFIRMED = rules.CONFIRMED
    REJECTED = rules.REJECTED; VOIDED = rules.VOIDED
    STATUS_CHOICES = rules.STATUS_CHOICES

    #: Счёт — идентификатором (правило 1.3): счётом владеет Billing.
    statement_id = models.PositiveIntegerField("Начисление", db_index=True)
    #: Чек необязателен (шаг E1): владелец отмечает наличную оплату вручную,
    #: не прося фотографию ради формальности.
    file = models.FileField("Чек", upload_to=receipt_upload_path, blank=True)
    #: Подтверждённая сумма. Есть только у подтверждённого платежа (инв. 2);
    #: у заявленного чека суммы ещё нет. Пусто у платежей, подтверждённых до
    #: шага E1, — их суммы никто не называл, и выдумать их нельзя.
    amount = models.DecimalField("Сумма", max_digits=12, decimal_places=2,
                                 null=True, blank=True)
    source = models.CharField("Источник", max_length=10, choices=SOURCE_CHOICES)
    status = models.CharField("Статус", max_length=10, choices=STATUS_CHOICES,
                              default=PENDING)
    note = models.CharField("Примечание", max_length=300, blank=True)
    submitted_at = models.DateTimeField("Получен", auto_now_add=True)

    class Meta:
        db_table = "payments_payment"
        verbose_name = "Платёж"
        verbose_name_plural = "Платежи"
        ordering = ["-submitted_at"]

    def __str__(self):
        return f"Платёж по счёту #{self.statement_id} ({self.get_status_display()})"
