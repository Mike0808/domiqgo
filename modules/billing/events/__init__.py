"""Контракты доменных событий модуля: имена и полезная нагрузка.

Контракт раньше кода — как у Payments на шаге E3: модуль Billing ещё не
наполнен, событие публикует легаси-`billing/` (интерфейсный слой), и при
расформировании публикация переедет в `application/` модуля, не меняя ни
имён, ни нагрузки. `InvoiceSettled` и `PaymentOverdue` объявятся вместе со
своими издателями (этап F — им нужен подписчик Notifications).
"""

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class InvoiceIssued:
    """Владелец предъявил счёт: сумма зафиксирована, срок оплаты назначен,
    период показаний закрыт (ADR-0012, ADR-0013).

    P1: Notifications (жильцу — «счёт выставлен») — подписчик на этапе F.
    """

    invoice_id: int
    tenancy_id: int
    property_id: int
    period: date
    total: Decimal
    due_date: date
    at: datetime


@dataclass(frozen=True)
class InvoiceSettled:
    """Признанная оплата достигла итога: счёт погашен.

    Публикует сверка (легаси-слой до расформирования `billing/`).
    P1: Notifications (жильцу) ✔ F3. P2+: Analytics (доходность).
    """

    invoice_id: int
    tenancy_id: int | None
    property_id: int
    period: date
    total: Decimal
    at: datetime
