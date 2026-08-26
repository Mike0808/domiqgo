"""Оркестрация команд модуля.

Правил здесь нет — они в `domain/`. Здесь порядок действий и единственное
место модуля, откуда публикуются события (правило 4.4).
"""

from datetime import datetime

from bus import publish

from ..events import PrivacyConsentGranted
from .ports import ConsentRepository


def grant_privacy_consent(repository: ConsentRepository, account_id: int,
                          policy_version: str, at: datetime) -> None:
    """Зафиксировать согласие на текущую редакцию политики.

    Момент передаётся снаружи, а не берётся модулем: «сейчас» — понятие
    интерфейса, а перенос прежних согласий обязан сохранить их собственные
    даты, а не проставить дату переноса.
    """
    journal = repository.load_journal(account_id)
    consent = journal.grant(policy_version, at)
    repository.append(account_id, consent.policy_version, consent.given_at)
    publish(PrivacyConsentGranted(
        account_id=account_id, policy_version=consent.policy_version,
        given_at=consent.given_at))
