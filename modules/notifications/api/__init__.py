"""Публичный API Notifications — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `BindChannel` | `bind_channel` |
| `UnbindChannel` | `unbind_channel` |
| `ResolveAccountByChannel` | `resolve_account_by_channel` |
| `ListChannels` | `list_channels` |

**Чего здесь пока нет.** Очередь исходящих (`DispatchPending`,
`ResendMessage`, `CancelPending`, `ListMessages`, `GetDeliveryState`) — шаг
**F2**; подписки на события и шаблоны — **F3**; почта — **F4**.

**Привязка не проверяет существования учётной записи** (инвариант 3):
вызывающий только что получил идентификатор от Identity, погасив одноразовый
код, — ещё одна проверка потребовала бы зависимости ради уже выполненной
работы (ADR-0017).
"""

from ..application import commands, queries
from ..domain.channel import AddressAlreadyBound, Channel


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
    "AddressAlreadyBound", "Channel",
    "resolve_account_by_channel", "list_channels",
    "bind_channel", "unbind_channel",
]
