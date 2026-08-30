"""Одноразовый код привязки внешнего канала.

Код доказывает личность: жилец, показавший его боту, — тот, кому владелец
этот код выдал. Адрес доставки (платформа, чат) к личности отношения не имеет
и кодом не занимается — это Notifications (ADR-0017).

Здесь только stdlib. Ни Django, ни базы.
"""

import secrets
from dataclasses import dataclass


class InvalidLinkCode(Exception):
    """Предъявленный код пуст или никому не принадлежит."""


@dataclass(frozen=True)
class LinkCode:
    """Действующий код одной учётной записи.

    У записи не бывает двух действующих кодов: выпуск нового отменяет прежний.
    Иначе владелец, выдавший код повторно («первый потерялся»), оставил бы
    потерянный код действующим.
    """

    account_id: int
    code: str

    @classmethod
    def issue(cls, account_id: int) -> "LinkCode":
        return cls(account_id=account_id, code=secrets.token_urlsafe(8))


def presented(raw: str | None) -> str:
    """Код в том виде, в каком его предъявили: без пробелов по краям.

    Пустой код отклоняется здесь, а не поиском в хранилище: у учётной записи
    без кода «пустой код» не должен совпасть ни с чем — и не должен даже
    искаться.
    """
    code = (raw or "").strip()
    if not code:
        raise InvalidLinkCode("Неверный код.")
    return code
