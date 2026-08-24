"""Хранение тарифных версий. Единственное место модуля, знающее о базе.

Модель — деталь хранения, а не предметная сущность: правила живут в
`domain/schedule.py`, сюда они не переезжают. Отсюда и отсутствие
`Meta.ordering`: в as-is порядок был способом выбрать версию
(`billing.Tariff.Meta.ordering`), а порядок — не инвариант. Выбор делает
`TariffSchedule.rate_on`.
"""

from django.core.exceptions import ValidationError
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
        # Ограничения не заменяют инвариант, а подпирают его. Правило живёт в
        # `domain/schedule.py` и проверяется без базы; здесь — последняя черта
        # на случай записи мимо модуля (миграция данных, правка руками, SQL).
        # Побочная польза: `ModelForm` проверяет ограничения модели сам, и
        # админка показывает владельцу внятную ошибку вместо отказа команды.
        constraints = [
            # Без `violation_error_message`: для ограничения по полям Django
            # его игнорирует и берёт `unique_error_message()` — см. ниже.
            models.UniqueConstraint(
                fields=["utility", "effective_from"],
                name="tariffs_one_version_per_utility_and_date",
            ),
            models.CheckConstraint(
                condition=models.Q(rate__gt=0),
                name="tariffs_rate_is_positive",
                violation_error_message="Ставка должна быть больше нуля.",
            ),
        ]

    def unique_error_message(self, model_class, unique_check):
        """Текст отказа для формы владельца.

        Django для `UniqueConstraint` с перечисленными полями берёт именно
        этот метод, а `violation_error_message` самого ограничения не читает —
        «для обратной совместимости» (`UniqueConstraint.validate`). Отсюда
        переопределение: иначе владелец увидел бы стандартное «запись с
        такими значениями полей уже существует», из которого не следует, что
        делать дальше.

        Правило по-прежнему в домене; здесь только его перевод на язык формы.
        """
        if set(unique_check) == {"utility", "effective_from"}:
            return ValidationError(
                "У этой услуги уже есть версия, действующая с указанной даты. "
                "Исправьте существующую версию, если это опечатка, или "
                "выберите другую дату начала действия, если цена изменилась.",
                code="unique_together")
        return super().unique_error_message(model_class, unique_check)

    def __str__(self):
        return f"{self.get_utility_display()} — {self.rate} (с {self.effective_from})"
