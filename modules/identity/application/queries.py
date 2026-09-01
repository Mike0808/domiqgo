"""Чтение: учётная запись и её тип, согласие и его история, решение о
внешнем входе, привязанные провайдеры."""

from ..domain.account import Account
from ..domain.external_login import ExternalLoginDecision, admit_external_login
from .ports import AccountRegistry, ConsentRepository, LinkedProviders


def get_account(registry: AccountRegistry, account_id: int) -> Account:
    return registry.load_account(account_id)


def has_current_consent(repository: ConsentRepository, account_id: int,
                        policy_version: str) -> bool:
    return repository.load_journal(account_id).covers(policy_version)


def consent_history(repository: ConsentRepository, account_id: int) -> list:
    return repository.load_journal(account_id).entries


def external_login_decision(repository: ConsentRepository, identity_known: bool,
                            account_id: int | None,
                            policy_version: str) -> ExternalLoginDecision:
    """Решение домена о пришедшей внешней личности.

    Согласие читается только когда оно может повлиять на ответ: известная
    личность и отсутствие вошедшего решаются без обращения к журналу.
    """
    account_present = account_id is not None
    consent_covers = (
        account_present and not identity_known
        and repository.load_journal(account_id).covers(policy_version))
    return admit_external_login(identity_known, account_present, consent_covers)


def linked_providers(repository: LinkedProviders, account_id: int) -> list[str]:
    return repository.linked_providers(account_id)
