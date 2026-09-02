"""Контракты доменных событий модуля: имена и полезная нагрузка.

Импортируются другими модулями наравне с `api/`. Публикуются только из
`application/` (правило 4.4).

Отдельного события «условия изменились» нет: продление публикует
`TenancyEnded` и `TenancyStarted`, и подписчику этого достаточно.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class TenancyStarted:
    """Договор заключён: жилец заселён на таких-то условиях.

    P1: слушает Billing (кому выставлять счёт). P2+: Analytics.
    """

    tenancy_id: int
    property_id: int
    account_id: int
    started_on: date
    rent: Decimal
    internet: Decimal
    other_fixed: Decimal


@dataclass(frozen=True)
class TenancyEnded:
    """Зафиксирован выезд.

    P1: Billing, Notifications. P2+: Analytics, Maintenance.
    """

    tenancy_id: int
    property_id: int
    ended_on: date


@dataclass(frozen=True)
class TenancyCorrected:
    """Сведения договора исправлены: записанное было неверно с самого начала.

    P1: Billing (пометить счета к пересмотру) — подписчик появится на этапе E.
    `changes` — перечень строк вида «поле: было -> стало»: подписчик должен
    понять, что именно изменилось, не обращаясь обратно в Tenancy.
    """

    tenancy_id: int
    property_id: int
    changes: tuple
