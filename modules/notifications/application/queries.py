"""Чтение: чей это адрес и какие каналы у получателя."""

from .ports import ChannelRegistry


def resolve_account_by_channel(registry: ChannelRegistry, platform: str,
                               address: str) -> int | None:
    channel = registry.find_by_address(platform, address)
    return channel.account_id if channel is not None else None


def list_channels(registry: ChannelRegistry, account_id: int) -> list:
    return registry.list_for(account_id)


def list_messages(outbox, account_id: int) -> list:
    return outbox.messages_for(account_id)


def delivery_state(outbox, message_id: int) -> str | None:
    message = outbox.get(message_id)
    return message.state if message is not None else None
