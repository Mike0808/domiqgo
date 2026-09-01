"""Доменный слой: правила и инварианты.

Не импортирует django, requests, allauth и прочие фреймворки — только stdlib.

Здесь тип учётной записи, журнал согласий (инвариант 6), код привязки
(инвариант 5) и правила входа через внешнего провайдера (инварианты 1 и 2).
Инварианты 3 и 4 — «одна внешняя личность у одной записи» и «последний
способ входа не отвязать» — пока держатся на allauth и появятся в домене
вместе с `UnlinkExternalIdentity`.
"""

from .account import Account, AccountType, type_from_staff_flag
from .consent import Consent, ConsentJournal
from .external_login import ExternalLoginDecision, admit_external_login
from .link_code import InvalidLinkCode, LinkCode, presented

__all__ = [
    "Account", "AccountType", "type_from_staff_flag",
    "Consent", "ConsentJournal",
    "ExternalLoginDecision", "admit_external_login",
    "InvalidLinkCode", "LinkCode", "presented",
]
