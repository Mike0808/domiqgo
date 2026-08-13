"""Реестр подписчиков: тип события → обработчики, в порядке подписки."""

from collections.abc import Callable
from typing import Any

#: Тип события → обработчики. Ключ — **точный** тип, без обхода MRO:
#: подписчик на базовый класс в P1 никому не нужен (правило 7.2), а «слушать
#: все события» для журнала шага B2 решается внутри `publish`, а не подпиской
#: (ADR-0027).
_subscribers: dict[type, list[Callable[[Any], None]]] = {}


def subscribe(event_type: type, handler: Callable[[Any], None]) -> None:
    """Подписать `handler` на события типа `event_type`.

    Повторная подписка того же обработчика игнорируется: модуль, чей
    `AppConfig.ready` вызвался дважды (а при `runserver` с автоперезагрузкой это
    штатное явление), не должен получать событие дважды.
    """
    handlers = _subscribers.setdefault(event_type, [])
    if handler not in handlers:
        handlers.append(handler)


def subscribers_for(event: Any) -> list[Callable[[Any], None]]:
    """Обработчики события — копией, чтобы подписка во время доставки не
    меняла список под ногами итератора."""
    return list(_subscribers.get(type(event), ()))


def clear_subscribers() -> None:
    """Опустошить реестр. Нужно тестам: реестр — модульное состояние, и без
    очистки подписка одного теста доживает до следующего."""
    _subscribers.clear()
