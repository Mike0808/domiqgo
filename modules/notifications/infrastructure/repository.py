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
