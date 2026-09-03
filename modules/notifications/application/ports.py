"""Порты: реестр каналов, очередь исходящих, транспорт."""

from typing import Protocol

from ..domain.channel import Channel
from ..domain.message import OutgoingMessage


class ChannelRegistry(Protocol):
    def find_by_address(self, platform: str, address: str) -> Channel | None: ...

    def replace_for(self, channel: Channel) -> None:
        """Сделать адрес единственным каналом записи в этой платформе."""

    def unbind(self, account_id: int, platform: str) -> None: ...

    def list_for(self, account_id: int) -> list[Channel]: ...


class Outbox(Protocol):
    def add(self, message: OutgoingMessage) -> OutgoingMessage: ...

    def save(self, message: OutgoingMessage) -> None: ...

    def get(self, message_id: int) -> OutgoingMessage | None: ...

    def queued(self) -> list[OutgoingMessage]:
        """Всё, что ждёт отправки, от старых к новым."""

    def messages_for(self, account_id: int) -> list[OutgoingMessage]: ...


class Transport(Protocol):
    def send_message(self, chat_id: str, text: str) -> None: ...
