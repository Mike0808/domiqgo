"""Интерфейсная оболочка расчёта начислений (шаг H3).

Расчёт переехал в `modules/billing`: арифметика — в `domain/calculation.py`,
оркестровка — в `application/generation.py`. Здесь — переводчики с языка
моделей на язык идентификаторов модуля и реэкспорт исключения.
"""

from modules.billing import api as billing
from modules.billing.api import MissingTenancyError  # noqa: F401 — реэкспорт

from ..models import MonthlyStatement


def generate_statement(apartment, period) -> MonthlyStatement:
    invoice_id = billing.generate_statement(apartment.pk, period)
    return MonthlyStatement.objects.get(pk=invoice_id)


def metered_resources(apartment) -> list[str]:
    return billing.metered_resources(apartment.pk)


def missing_meters(apartment) -> list[str]:
    return billing.missing_meters(apartment.pk)
