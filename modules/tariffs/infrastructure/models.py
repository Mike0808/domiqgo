"""Хранение тарифных версий. Единственное место модуля, знающее о базе.

Модель — деталь хранения, а не предметная сущность: правила живут в
`domain/schedule.py`, сюда они не переезжают. Отсюда и отсутствие
`Meta.ordering`: в as-is порядок был способом выбрать версию
(`billing.Tariff.Meta.ordering`), а порядок — не инвариант. Выбор делает
`TariffSchedule.rate_on`.
"""

from django.db import models

from ..domain.catalogue import UTILITIES


class TariffVersion(models.Model):
    utility = models.CharField("Услуга", max_length=32,
                               choices=list(UTILITIES.items()))
    rate = models.DecimalField("Ставка, ₽/ед.", max_digits=10, decimal_places=4)
    effective_from = models.DateField("Действует с")
    source_name = models.CharField("Источник", max_length=200, blank=True)
    source_url = models.URLField("Ссылка на источник", blank=True)

    class Meta:
        db_table = "tariffs_tariff_version"
        verbose_name = "Версия тарифа"
        verbose_name_plural = "Тарифы"

    def __str__(self):
        return f"{self.get_utility_display()} — {self.rate} (с {self.effective_from})"
