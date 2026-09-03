"""Порт реестра каналов доставки."""

from typing import Protocol

from ..domain.channel import Channel


class ChannelRegistry(Protocol):
    def find_by_address(self, platform: str, address: str) -> Channel | None: ...

    def replace_for(self, channel: Channel) -> None:
        """Сделать адрес единственным каналом записи в этой платформе."""

    def unbind(self, account_id: int, platform: str) -> None: ...

    def list_for(self, account_id: int) -> list[Channel]: ...
