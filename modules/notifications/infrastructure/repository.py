"""Перевод между каналами домена и строками таблицы."""

from ..domain.channel import Channel
from . import models


def _to_domain(row: models.Channel) -> Channel:
    return Channel(account_id=row.account_id, platform=row.platform,
                   address=row.address)


def find_by_address(platform: str, address: str) -> Channel | None:
    row = models.Channel.objects.filter(platform=platform,
                                        address=address).first()
    return _to_domain(row) if row is not None else None


def replace_for(channel: Channel) -> None:
    models.Channel.objects.update_or_create(
        account_id=channel.account_id, platform=channel.platform,
        defaults={"address": channel.address})


def unbind(account_id: int, platform: str) -> None:
    models.Channel.objects.filter(account_id=account_id,
                                  platform=platform).delete()


def list_for(account_id: int) -> list[Channel]:
    return [_to_domain(r) for r in
            models.Channel.objects.filter(account_id=account_id)
            .order_by("platform")]


# ---------------------------------------------------------------- очередь

def _message_to_domain(row: models.OutgoingMessage):
    from ..domain.message import OutgoingMessage as DomainMessage

    return DomainMessage(
        message_id=row.pk, account_id=row.account_id, platform=row.platform,
        address=row.address, text=row.text, state=row.state,
        attempts=row.attempts, last_error=row.last_error)


def add(message):
    row = models.OutgoingMessage.objects.create(
        account_id=message.account_id, platform=message.platform,
        address=message.address, text=message.text, state=message.state)
    return _message_to_domain(row)


def save(message):
    models.OutgoingMessage.objects.filter(pk=message.message_id).update(
        state=message.state, attempts=message.attempts,
        last_error=message.last_error)


def get(message_id: int):
    row = models.OutgoingMessage.objects.filter(pk=message_id).first()
    return _message_to_domain(row) if row is not None else None


def queued():
    return [_message_to_domain(r) for r in
            models.OutgoingMessage.objects.filter(state="queued")]


def messages_for(account_id: int):
    return [_message_to_domain(r) for r in
            models.OutgoingMessage.objects.filter(account_id=account_id)]


def record_run(sent: int, failed: int) -> None:
    models.DispatchRun.objects.create(sent=sent, failed=failed)
