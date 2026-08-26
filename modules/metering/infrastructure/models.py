"""Хранение приборов и показаний. Единственное место модуля, знающее о базе.

Таблицы переехали из `billing/` шагом C2c через `SeparateDatabaseAndState`:
данные остались на месте, сменились владелец и имена. Ссылка на квартиру —
идентификатором без констрейнта (правило 1.3); внешние ключи сняты шагами
C2a и C2b, до переезда, потому что перенести модель с живым ключом нельзя,
не ослабив архитектурную проверку.
"""

from django.db import models

from ..domain.catalogue import RESOURCES


class Meter(models.Model):
    """Физический прибор учёта: номер и показание, зафиксированные в акте
    при подписании договора. Начальное показание — база первого месяца."""

    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    resource = models.CharField("Вид ресурса", max_length=32,
                                choices=list(RESOURCES.items()))
    serial_number = models.CharField("Заводской номер", max_length=64, blank=True)
    initial_value = models.DecimalField("Начальное показание", max_digits=12,
                                        decimal_places=3)
    initial_date = models.DateField("Дата фиксации", null=True, blank=True,
                                    help_text="Дата акта / подписания договора.")

    class Meta:
        db_table = "metering_meter"
        verbose_name = "Счётчик"
        verbose_name_plural = "Счётчики"
        unique_together = [("apartment_id", "resource")]

    def __str__(self):
        number = f" № {self.serial_number}" if self.serial_number else ""
        return f"{self.get_resource_display()}{number}"


class MeterReading(models.Model):
    """Значение на табло прибора, зафиксированное на конец периода."""

    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    period = models.DateField("Период")
    resource = models.CharField("Вид ресурса", max_length=32,
                                choices=list(RESOURCES.items()))
    value = models.DecimalField("Показание", max_digits=12, decimal_places=3)
    entered_by_tenant = models.BooleanField("Внесено жильцом", default=False)

    class Meta:
        db_table = "metering_reading"
        verbose_name = "Показание"
        verbose_name_plural = "Показания"
        unique_together = [("apartment_id", "period", "resource")]
        ordering = ["-period", "resource"]

    def __str__(self):
        return f"кв. {self.apartment_id} {self.period:%Y-%m} {self.resource}={self.value}"


class PeriodLock(models.Model):
    """Период точки учёта, объявленный закрытым.

    Хранится строкой на закрытый период, а не флагом на показании: закрыт
    период целиком, включая приборы, по которым показаний ещё нет.
    """

    apartment_id = models.PositiveIntegerField("Квартира", db_index=True)
    period = models.DateField("Период")
    closed_at = models.DateTimeField("Закрыт", auto_now_add=True)

    class Meta:
        db_table = "metering_period_lock"
        verbose_name = "Закрытый период"
        verbose_name_plural = "Закрытые периоды"
        unique_together = [("apartment_id", "period")]
        ordering = ["-period"]

    def __str__(self):
        return f"кв. {self.apartment_id} {self.period:%Y-%m} закрыт"
