"""Канал доставки: адрес получателя в платформе. Корень агрегата.

Канал отвязан от жильца и привязан к учётной записи: адрес доставки — не
свойство проживания. Здесь только stdlib.
"""

from dataclasses import dataclass

#: Куда слать, когда каналов несколько: мессенджер доходит быстрее письма.
#: Порядок — правило домена, а не случайность сортировки.
DELIVERY_PRIORITY = ("telegram", "max", "email")


def preferred(channels):
    """Канал для доставки — первый по предпочтению платформ."""
    ranked = sorted(channels, key=lambda c: (
        DELIVERY_PRIORITY.index(c.platform)
        if c.platform in DELIVERY_PRIORITY else len(DELIVERY_PRIORITY)))
    return ranked[0] if ranked else None


class AddressAlreadyBound(ValueError):
    """Один адрес не привязан к двум учётным записям (инвариант 2): чат — не
    общий почтовый ящик, и сообщение о счёте не должно уйти чужому."""


@dataclass(frozen=True)
class Channel:
    """Привязка учётной записи к адресу в платформе.

    У записи не более одного адреса на платформу (инвариант 1): повторная
    привязка замещает прежний адрес — так вёл себя и старый `link_chat`.
    Существование учётной записи не проверяется (инвариант 3): вызывающий
    только что получил идентификатор от Identity, погасив код (ADR-0017).
    """

    account_id: int
    platform: str
    address: str
