"""Перевод между доменными объектами и строками таблиц."""

from datetime import datetime

from ..domain.account import Account, AccountType, type_from_staff_flag
from ..domain.consent import Consent, ConsentJournal
from ..domain.link_code import LinkCode
from . import models


# ---------------------------------------------------------------- согласия

def load_journal(account_id: int) -> ConsentJournal:
    """Журнал целиком: инвариант «согласие не перезаписывается» охватывает всю
    историю, и проверить его на куске невозможно."""
    rows = models.Consent.objects.filter(account_id=account_id)
    return ConsentJournal(account_id, [
        Consent(policy_version=row.policy_version, given_at=row.given_at)
        for row in rows])


def append(account_id: int, policy_version: str, given_at: datetime) -> None:
    """Дописать согласие.

    Только добавление — ни `update`, ни `delete` у репозитория нет намеренно:
    журнал, который умеет менять прошлое, доказательством не является.
    """
    models.Consent.objects.create(account_id=account_id,
                                  policy_version=policy_version,
                                  given_at=given_at)


# ------------------------------------------------------------ коды привязки

def replace(link_code: LinkCode) -> None:
    models.LinkCode.objects.update_or_create(
        account_id=link_code.account_id, defaults={"code": link_code.code})


def find(code: str) -> LinkCode | None:
    row = models.LinkCode.objects.filter(code=code).first()
    return None if row is None else LinkCode(account_id=row.account_id, code=row.code)


def discard(link_code: LinkCode) -> None:
    models.LinkCode.objects.filter(
        account_id=link_code.account_id, code=link_code.code).delete()


# ------------------------------------------------------- внешние личности

def linked_providers(account_id: int) -> list[str]:
    """allauth — инфраструктура Identity: его таблица внешних личностей читается
    здесь, и только здесь. Остальным модулям и интерфейсу — через `api`."""
    from allauth.socialaccount.models import SocialAccount

    return list(SocialAccount.objects.filter(user_id=account_id)
                .order_by("provider").values_list("provider", flat=True))


# ---------------------------------------------------------- учётные записи

def load_account(account_id: int) -> Account:
    """Запись реестра важнее флага; флаг — мост для незарегистрированных.

    `auth.User` — таблица учётных записей самого Identity (модуль своей не
    заводит), так что чтение флага здесь — чтение своих данных, а не чужих.
    """
    row = models.Account.objects.filter(account_id=account_id).first()
    if row is not None:
        return Account(account_id=account_id, type=AccountType(row.type),
                       suspended=_is_suspended(account_id))
    from django.contrib.auth import get_user_model

    is_staff = (get_user_model().objects.filter(pk=account_id)
                .values_list("is_staff", flat=True).first())
    return Account(account_id=account_id, type=type_from_staff_flag(bool(is_staff)),
                   suspended=_is_suspended(account_id))


def _is_suspended(account_id: int) -> bool:
    from django.contrib.auth import get_user_model

    is_active = (get_user_model().objects.filter(pk=account_id)
                 .values_list("is_active", flat=True).first())
    return is_active is False   # незнакомая запись не считается приостановленной


def register(account_id: int, type: AccountType) -> None:
    models.Account.objects.update_or_create(
        account_id=account_id, defaults={"type": type.value})


def set_suspended(account_id: int, suspended: bool) -> None:
    """Статус — `auth.User.is_active`: вход перестаёт работать средствами
    самого Django, без второго флага с тем же смыслом. `auth.User` — таблица
    учётных записей самого Identity (модуль своей не заводит)."""
    from django.contrib.auth import get_user_model

    get_user_model().objects.filter(pk=account_id).update(is_active=not suspended)
