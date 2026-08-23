"""Контракты доменных событий Tariffs.

Импортируются другими модулями наравне с `api/` — это часть публичной
поверхности. Имена в прошедшем времени, payload только из примитивов
(правила 4.1 и 4.2); события — датаклассы, иначе шина не запишет нагрузку
в журнал ([ADR-0027](../../../docs/architecture/adr/0027-event-bus-lives-outside-modules.md)).

Подписчик на P1 есть только у одного из трёх — Billing на
`TariffVersionCorrected`. Два остальных публикуются с первого дня без
подписчиков сознательно: новая версия тарифа прошлое не меняет
([ADR-0004](../../../docs/architecture/adr/0004-tariff-version-period-resolution.md)),
пересчитывать нечего, — а Automation в P3 подключится, не трогая Tariffs.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TariffVersionPublished:
    """Регулятор поднял цену — исторический факт."""

    utility: str
    rate: Decimal
    effective_from: date
    source_name: str
    source_url: str


@dataclass(frozen=True)
class TariffVersionCorrected:
    """Опечатку в уже введённой версии исправили — признание ошибки оператора.

    Отрезок действия (`effective_from` … `effective_until`, не включая) входит
    в payload потому, что подписчик обязан найти затронутые счета **не
    обращаясь обратно в Tariffs** ([ADR-0005](../../../docs/architecture/adr/0005-retroactive-tariff-correction.md)).
    `effective_until is None` означает «версия последняя, действует и сейчас».

    Цена решения названа в спецификации прямо: отрезок в payload — де-факто
    контракт, и сузить его позже нельзя.
    """

    utility: str
    effective_from: date
    effective_until: date | None
    previous_rate: Decimal
    new_rate: Decimal


@dataclass(frozen=True)
class TariffVersionWithdrawn:
    """Версию, введённую по ошибке, убрали."""

    utility: str
    effective_from: date
    withdrawn_rate: Decimal


__all__ = [
    "TariffVersionPublished",
    "TariffVersionCorrected",
    "TariffVersionWithdrawn",
]
