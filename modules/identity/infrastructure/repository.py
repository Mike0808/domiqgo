"""Перевод между доменными объектами и строками таблиц."""

from datetime import datetime

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
