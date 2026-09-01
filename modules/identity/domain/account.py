"""Тип учётной записи: владелец или жилец.

После входа надо решить, куда вести человека, и решить это раньше, чем
кто-либо спросит про договоры. Поэтому тип хранит Identity, а не выводит из
Tenancy: обратный вызов замкнул бы цикл, а владелец без единого договора
перестал бы быть владельцем.

Здесь только stdlib. Ни Django, ни базы.
"""

from dataclasses import dataclass
from enum import Enum


class AccountType(Enum):
    OWNER = "owner"
    TENANT = "tenant"


@dataclass(frozen=True)
class Account:
    account_id: int
    type: AccountType

    @property
    def is_owner(self) -> bool:
        return self.type is AccountType.OWNER


def type_from_staff_flag(is_staff: bool) -> AccountType:
    """Мост от флага «персонал» Django к типу учётной записи.

    Пока учётные записи заводятся в стандартной админке Django, а не командой
    `CreateAccount`, у новой записи нет ничего, кроме этого флага. Правило одно
    и названо здесь, а не размазано по представлениям: персонал — владелец,
    остальные — жильцы. Запись реестра, если она есть, важнее флага.
    """
    return AccountType.OWNER if is_staff else AccountType.TENANT
