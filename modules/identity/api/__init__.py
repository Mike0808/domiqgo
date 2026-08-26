"""Публичный API Identity — единственная дверь для остальных модулей.

| Спецификация | Здесь |
|---|---|
| `GrantPrivacyConsent` | `grant_privacy_consent` |
| `HasCurrentConsent(account_id)` | `has_current_consent` |

**Чего здесь пока нет.** `CreateAccount`, `LinkExternalIdentity`,
`UnlinkExternalIdentity`, `ChangePassword`, `IssueLinkCode`, `RedeemLinkCode`,
`SuspendAccount` и запрос `GetAccount` появятся на шагах **C4c** (код
привязки), **C4d** (правила входа) и **C4e** (тип учётной записи). Шаг C4a
переносит согласие и ничего больше: перенос кода и изменение поведения не
совмещаются (правило 7.4), а согласие само по себе тянет за собой и то и
другое.

**Редакция политики приходит снаружи.** Модуль не знает, какая редакция
считается текущей, — это вопрос текста политики, а не учётных записей.
Вызывающий передаёт её явно, и потому история согласий читается одинаково
через год после смены текста.
"""

from datetime import datetime

from ..application import commands, queries
from ..domain.consent import Consent


def _repository():
    """Импорт внутри функции: `api/__init__` попадает в граф импортов раньше,
    чем Django готов отдать модели."""
    from ..infrastructure import repository

    return repository


# ------------------------------------------------------------------- запросы

def has_current_consent(account_id: int, policy_version: str) -> bool:
    """Дано ли согласие на эту редакцию политики.

    Спрашивает адаптер входа через провайдера: привязать новый способ входа
    можно только при действующем согласии.
    """
    return queries.has_current_consent(_repository(), account_id, policy_version)


def consent_history(account_id: int) -> list[Consent]:
    """Все согласия учётной записи в порядке появления — для аудита 152-ФЗ."""
    return queries.consent_history(_repository(), account_id)


# ------------------------------------------------------------------- команды

def grant_privacy_consent(account_id: int, policy_version: str,
                          at: datetime) -> None:
    """Зафиксировать согласие на обработку персональных данных.

    Прежние согласия не трогаются: каждое — отдельный факт, и журнал, умеющий
    менять прошлое, доказательством не является.
    """
    commands.grant_privacy_consent(_repository(), account_id, policy_version, at)


__all__ = [
    "Consent",
    "has_current_consent", "consent_history", "grant_privacy_consent",
]
