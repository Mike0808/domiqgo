"""Реэкспорт калькулятора (шаг H3): арифметика счёта — чистый домен модуля
Billing, `modules/billing/domain/calculation.py`. Старые импорты ведут туда."""

from modules.billing.domain.calculation import *  # noqa: F401,F403
from modules.billing.domain.calculation import (  # noqa: F401 — явные имена
    ApartmentConfig, MissingHeatNormError, MissingTariffError,
    compute_statement,
)
