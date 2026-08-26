"""Чтение: есть ли действующее согласие и вся его история."""

from .ports import ConsentRepository


def has_current_consent(repository: ConsentRepository, account_id: int,
                        policy_version: str) -> bool:
    return repository.load_journal(account_id).covers(policy_version)


def consent_history(repository: ConsentRepository, account_id: int) -> list:
    return repository.load_journal(account_id).entries
