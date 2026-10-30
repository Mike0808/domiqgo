"""Подписка сверки на платёжные события (ADR-0015; в модуле с H3).

События Payments — контракты (`events/` виден наравне с `api/`), а реакция
на них — не синхронный вызов: стрелка зависимостей payments → billing не
разворачивается. `wire()` зовут `apps.ready()` модуля и тестовые обвязки —
`bus.subscribe` дедуплицирует, двойная подписка безвредна.
"""

from bus import subscribe
from modules.payments.events import PaymentConfirmed, PaymentVoided

from . import settlement


def wire() -> None:
    subscribe(PaymentConfirmed, settlement.apply_confirmed)
    subscribe(PaymentVoided, settlement.apply_voided)
