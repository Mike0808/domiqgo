"""Внутрипроцессная шина доменных событий — шаг B1 плана миграции.

Контракт доставки задан [картой](../docs/architecture/02-target-map.md) §5:
синхронно, внутри процесса, **после коммита транзакции**. Ни брокера, ни
Celery. Место пакета — [ADR-0027](../docs/architecture/adr/0027-event-bus-lives-outside-modules.md).

Шина не знает ни одного события по имени: `bus/` не импортирует ни `modules/`,
ни `billing/`, и контракт `bus-knows-no-domain` в `.importlinter` это
удерживает. Событие для шины — любой объект; ключ подписки — его тип.

    from bus import publish, subscribe

    subscribe(InvoiceIssued, notify_tenant)   # при старте приложения
    publish(InvoiceIssued(invoice_id=..., ...))   # из application/

Публикация разрешена **только из `application/`** (правило 4.4, проверяется
`tests/architecture/test_events_and_orm.py`): домен не знает, что у него есть
подписчики, а инфраструктура не знает, что произошло по существу.
"""

from .publisher import publish
from .registry import clear_subscribers, subscribe

__all__ = ["publish", "subscribe", "clear_subscribers"]
