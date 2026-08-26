"""Доменный слой: правила и инварианты.

Не импортирует django, requests, allauth и прочие фреймворки — только stdlib.

Здесь состояние эксплуатации объекта и инвариант «при подведённой ГВС норматив
обязателен и больше нуля» — он приехал шагом **C3c** из `Apartment.clean`, где
жил с исправления дефекта №29.
"""

from .property import Apartment, HeatNormMissing, ensure_heat_norm_is_set

__all__ = ["Apartment", "HeatNormMissing", "ensure_heat_norm_is_set"]
