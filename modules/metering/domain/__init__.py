"""Доменный слой: правила и инварианты.

Не импортирует django, requests, allauth и прочие фреймворки — только stdlib.

Пока здесь один каталог видов ресурса. Правила учёта — база отсчёта и
монотонность показаний — живут в `billing/services/` и переезжают сюда шагом
**C2d**: шаг C2c переносит владение данными, а не правила, и совмещать
перенос с изменением поведения запрещает правило 7.4.
"""

from .catalogue import RESOURCES, UNITS, UnknownResource, ensure_known

__all__ = ["RESOURCES", "UNITS", "UnknownResource", "ensure_known"]
