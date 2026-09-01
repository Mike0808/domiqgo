"""Доменный слой: правила и инварианты.

Не импортирует django и прочие фреймворки — только stdlib.

Договор (`Tenancy`, `Terms`; инварианты 2 и 3) и история заселений объекта
(`PropertyHistory`; инварианты 1 и 5). Инвариант 4 — «учётная запись и объект
существуют» — проверяется прикладным слоем через API Identity и Properties.
"""

from .history import PeriodOverlap, PropertyHistory, PropertyOutOfService
from .tenancy import AlreadyEnded, EndBeforeStart, Tenancy, Terms

__all__ = [
    "AlreadyEnded", "EndBeforeStart", "Tenancy", "Terms",
    "PeriodOverlap", "PropertyHistory", "PropertyOutOfService",
]
