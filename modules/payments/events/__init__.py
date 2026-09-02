"""Контракты доменных событий модуля: имена и полезная нагрузка.

Контракт включается раньше кода — как на шаге B2: модуль Payments ещё не
наполнен, события публикует легаси-`billing/` (интерфейсный слой), и при
расформировании `billing/` публикация переедет в `application/` модуля, не
меняя ни имён, ни нагрузки. На этих событиях уже держится проекция признанных
оплат в Billing ([ADR-0015]) — потому имена типов в журнале шины обязаны быть
целевыми с первого дня.

[ADR-0015]: ../../../docs/architecture/adr/0015-settlement-projection-in-billing.md
"""

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal


@dataclass(frozen=True)
class PaymentSubmitted:
    """Жилец приложил чек: платёж заявлен и ждёт решения владельца.

    P1: Notifications (владельцу — «пришёл чек») — подписчик на этапе F.
    """

    payment_id: int
    statement_id: int
    source: str
    at: datetime


@dataclass(frozen=True)
class PaymentConfirmed:
    """Владелец признал платёж и назвал сумму.

    P1: Billing — сверка ([ADR-0015]); Notifications (жильцу) — этап F.
    Сумма в нагрузке обязательна: проекции признанных оплат хватает
    собственных данных, и спрашивать Payments не приходится никогда.
    """

    payment_id: int
    statement_id: int
    amount: Decimal
    at: datetime


@dataclass(frozen=True)
class PaymentRejected:
    """Владелец не признал заявленный платёж.

    P1: Notifications (жильцу — «чек не принят») — этап F. Billing не слушает:
    сумма отклонённого в сверке никогда не участвовала, пересчитывать нечего.
    """

    payment_id: int
    statement_id: int
    reason: str
    at: datetime


@dataclass(frozen=True)
class PaymentVoided:
    """Подтверждённый платёж отменён: сумма изымается из сверки.

    Не путать с отклонением: отклоняется незнакомец, отменяется признанный.
    P1: Billing (пересчёт сверки), Notifications. Публикуется с шага E5
    (`VoidPayment`); контракт объявлен здесь же, чтобы проекция подписалась
    на оба события сразу.
    """

    payment_id: int
    statement_id: int
    amount: Decimal
    reason: str
    at: datetime
