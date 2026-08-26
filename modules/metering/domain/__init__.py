"""Доменный слой: правила и инварианты.

Не импортирует django, requests, allauth и прочие фреймворки — только stdlib.

- `catalogue.py` — виды ресурса и единицы измерения.
- `point.py` — точка учёта: база отсчёта и монотонность показаний. Приехали
  из `billing/services/` шагом **C2d**; шаг C2c до этого перенёс только
  владение данными.
"""

from .catalogue import RESOURCES, UNITS, UnknownResource, ensure_known
from .point import (
    BaselineMissing, Consumption, MeteringPoint, ReadingWentBackwards,
)

__all__ = [
    "RESOURCES", "UNITS", "UnknownResource", "ensure_known",
    "MeteringPoint", "Consumption", "BaselineMissing", "ReadingWentBackwards",
]
