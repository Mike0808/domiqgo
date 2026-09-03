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


def enqueue_message(registry: ChannelRegistry, outbox, account_id: int,
                    text: str):
    """Составить сообщение и поставить в очередь (шаг F2).

    Канал фиксируется здесь же, вместе с текстом: журнал доставки должен
    говорить, куда именно ушло. Получателю без единого канала сообщение не
    ставится — очередь не копит недоставимое; вернётся `None`.
    Отправкой занимается прогон, не постановка: слать в обработчике события
    значило бы держать транзакцию издателя на время разговора с Telegram.
    """
    from ..domain.message import OutgoingMessage

    channels = registry.list_for(account_id)
    if not channels:
        return None
    channel = channels[0]
    return outbox.add(OutgoingMessage(
        message_id=None, account_id=account_id, platform=channel.platform,
        address=channel.address, text=text))


def dispatch_pending(outbox, transport_for) -> tuple[int, int]:
    """Прогон отправки: попытаться доставить всё, что в очереди.

    Падение одной доставки не роняет прогон: попытка записывается, сообщение
    останется в очереди до исчерпания попыток (инварианты 4, 5).
    Возвращает (доставлено, недоставлено-навсегда).
    """
    sent = failed = 0
    for message in outbox.queued():
        try:
            transport_for(message.platform).send_message(message.address,
                                                         message.text)
        except Exception as exc:  # noqa: BLE001 — сетевая ошибка = попытка
            message = message.attempt_failed(f"{type(exc).__name__}: {exc}")
            if message.state == "failed":
                failed += 1
        else:
            message = message.delivered()
            sent += 1
        outbox.save(message)
    return sent, failed


def resend_message(outbox, message_id: int) -> None:
    message = outbox.get(message_id)
    if message is None:
        raise LookupError(f"Сообщение #{message_id} не найдено.")
    outbox.save(message.resend())


def cancel_pending(outbox, message_id: int) -> None:
    message = outbox.get(message_id)
    if message is None:
        raise LookupError(f"Сообщение #{message_id} не найдено.")
    outbox.save(message.cancel())
