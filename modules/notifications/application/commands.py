"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Событий модуль не публикует вовсе:
Notifications — конечная точка (спецификация).
"""

from ..domain.channel import AddressAlreadyBound, Channel
from .ports import ChannelRegistry


def bind_channel(registry: ChannelRegistry, account_id: int, platform: str,
                 address: str) -> None:
    """Привязать адрес канала к учётной записи (вторая половина ADR-0017).

    Чужой адрес не перепривязывается молча (инвариант 2): чат, который уже
    доказал принадлежность другой записи, сначала отвязывают.
    """
    existing = registry.find_by_address(platform, address)
    if existing is not None and existing.account_id != account_id:
        raise AddressAlreadyBound(
            f"Адрес {platform}:{address} уже привязан к другой учётной записи.")
    registry.replace_for(Channel(account_id=account_id, platform=platform,
                                 address=address))


def unbind_channel(registry: ChannelRegistry, account_id: int,
                   platform: str) -> None:
    registry.unbind(account_id, platform)
