"""Доменный слой: правила и инварианты.

Не импортирует django и прочие фреймворки — только stdlib.

Канал доставки (инварианты 1–3) и исходящее сообщение (инварианты 4–6).
Общего инварианта между ними нет — потому и два корня.
"""

from .channel import DELIVERY_PRIORITY, AddressAlreadyBound, Channel, preferred
from .message import (
    CANCELLED, FAILED, MAX_ATTEMPTS, QUEUED, SENT,
    AlreadySent, NotFailed, NotQueued, OutgoingMessage,
)

__all__ = [
    "AddressAlreadyBound", "Channel", "DELIVERY_PRIORITY", "preferred",
    "OutgoingMessage", "AlreadySent", "NotFailed", "NotQueued",
    "MAX_ATTEMPTS", "QUEUED", "SENT", "FAILED", "CANCELLED",
]
