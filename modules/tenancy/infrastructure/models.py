"""Хранение договоров. Единственное место модуля, знающее о базе.

Ссылки на объект и учётную запись — идентификаторами без констрейнтов
(правило 1.3): договор переживёт выделение любого из соседей в сервис.
Защиту `PROTECT`, которой прежде держалась связь жильца с квартирой, заменяет
инвариант Properties «объект с историей не удаляется».
"""

from decimal import Decimal

from django.db import models


class Tenancy(models.Model):
    """Один договор. Условия лежат в той же строке: они неизменны внутри
    договора (инвариант 3), и отдельной таблицы им не нужно."""

    property_id = models.PositiveIntegerField("Объект", db_index=True)
    account_id = models.PositiveIntegerField("Учётная запись", db_index=True)
    full_name = models.CharField("ФИО", max_length=200, blank=True)
    started_on = models.DateField("Заселение")
    ended_on = models.DateField("Выезд", null=True, blank=True)
    #: Ложь — дату проставила миграция из записи жильца, у которой дат не
    #: было; владелец подтверждает её в диалоге шага D2.
    start_confirmed = models.BooleanField("Дата заселения подтверждена", default=True)
    rent = models.DecimalField("Аренда", max_digits=10, decimal_places=2,
                               default=Decimal("0"))
    internet = models.DecimalField("Интернет", max_digits=10, decimal_places=2,
                                   default=Decimal("0"))
    other_fixed = models.DecimalField("Прочее", max_digits=10, decimal_places=2,
                                      default=Decimal("0"))

    class Meta:
        db_table = "tenancy_tenancy"
        verbose_name = "Договор"
        verbose_name_plural = "Договоры"
        ordering = ["property_id", "started_on", "id"]

    def __str__(self):
        until = f" — {self.ended_on:%d.%m.%Y}" if self.ended_on else ""
        return f"#{self.pk}: объект #{self.property_id}, {self.full_name or 'без ФИО'}, с {self.started_on:%d.%m.%Y}{until}"


class OutOfService(models.Model):
    """Объекты, выведенные из эксплуатации, — по событиям Properties.

    Строка есть, пока объект выведен; возврат в эксплуатацию её удаляет.
    Своя таблица, а не запрос в Properties: проверка работает и тогда, когда
    Properties недоступен (ADR-0009).
    """

    property_id = models.PositiveIntegerField("Объект", unique=True)

    class Meta:
        db_table = "tenancy_out_of_service"
        verbose_name = "Объект вне эксплуатации"
        verbose_name_plural = "Объекты вне эксплуатации"
