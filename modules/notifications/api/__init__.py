"""Публичный API Notifications — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `BindChannel` | `bind_channel` |
| `UnbindChannel` | `unbind_channel` |
| `ResolveAccountByChannel` | `resolve_account_by_channel` |
| `ListChannels` | `list_channels` |

| `EnqueueMessage` (внутренняя) | `enqueue_message` |
| `DispatchPending` | `dispatch_pending` |
| `ResendMessage` | `resend_message` |
| `CancelPending` | `cancel_pending` |
| `ListMessages` | `list_messages` |
| `GetDeliveryState` | `get_delivery_state` |

**Чего здесь пока нет.** Подписки на события и шаблоны — **F3**; почта —
**F4**.

**Постановка в очередь не отправляет.** Отправкой занимается прогон
(`dispatch_pending` — по расписанию, командой `dispatch_notifications`, или
из админки): слать в обработчике события значило бы держать транзакцию
издателя на время разговора с Telegram.

**Привязка не проверяет существования учётной записи** (инвариант 3):
вызывающий только что получил идентификатор от Identity, погасив одноразовый
код, — ещё одна проверка потребовала бы зависимости ради уже выполненной
работы (ADR-0017).
"""

from ..application import commands, queries
from ..domain.channel import AddressAlreadyBound, Channel
from ..domain.message import AlreadySent, NotFailed, NotQueued, OutgoingMessage


def _registry():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def resolve_account_by_channel(platform: str, address: str) -> int | None:
    """Какой учётной записи принадлежит этот адрес — так входящий бот узнаёт,
    с кем говорит."""
    return queries.resolve_account_by_channel(_registry(), platform, address)


def list_channels(account_id: int) -> list[Channel]:
    """Привязанные каналы получателя."""
    return queries.list_channels(_registry(), account_id)


# ------------------------------------------------------------------- команды

def bind_channel(account_id: int, platform: str, address: str) -> None:
    """Привязать адрес канала к учётной записи.

    Повторная привязка замещает прежний адрес записи в этой платформе;
    чужой адрес поднимает `AddressAlreadyBound`.
    """
    commands.bind_channel(_registry(), account_id, platform, address)


def unbind_channel(account_id: int, platform: str) -> None:
    commands.unbind_channel(_registry(), account_id, platform)


__all__ = [
    "AddressAlreadyBound", "Channel", "OutgoingMessage",
    "AlreadySent", "NotFailed", "NotQueued",
    "resolve_account_by_channel", "list_channels",
    "bind_channel", "unbind_channel",
    "enqueue_message", "dispatch_pending", "resend_message",
    "cancel_pending", "list_messages", "get_delivery_state",
]


# ------------------------------------------------------------- очередь (F2)

def subscribe_to_domain_events(owner_accounts) -> None:
    """Подписать модуль на события системы (шаг F3).

    `owner_accounts` — вызываемое, отдающее учётные записи владельцев для
    сообщений «пришёл чек»; его передаёт интерфейсный слой, у которого есть
    Identity, — сам модуль Identity не вызывает (матрица §2).
    """
    from ..application import subscriptions

    subscriptions.wire(owner_accounts)


def enqueue_message(account_id: int, text: str) -> int | None:
    """Составить сообщение и поставить в очередь; канал и текст фиксируются.

    Получателю без каналов сообщение не ставится — вернётся `None`.
    """
    message = commands.enqueue_message(_registry(), _registry(), account_id, text)
    return message.message_id if message is not None else None


def dispatch_pending() -> tuple[int, int]:
    """Прогон отправки; каждый прогон оставляет строку в журнале."""
    from ..infrastructure.transports import transport_for

    registry = _registry()
    sent, failed = commands.dispatch_pending(registry, transport_for)
    registry.record_run(sent, failed)
    return sent, failed


def resend_message(message_id: int) -> None:
    """Повторная отправка недоставленного — вручную, владельцем."""
    commands.resend_message(_registry(), message_id)


def cancel_pending(message_id: int) -> None:
    """Снять неотправленное сообщение с очереди."""
    commands.cancel_pending(_registry(), message_id)


def list_messages(account_id: int) -> list[OutgoingMessage]:
    """Журнал: что и когда отправлялось получателю."""
    return queries.list_messages(_registry(), account_id)


def get_delivery_state(message_id: int) -> str | None:
    return queries.delivery_state(_registry(), message_id)
